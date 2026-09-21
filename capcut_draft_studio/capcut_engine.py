from __future__ import annotations
import json, math, os, shutil, time
from pathlib import Path
from . import animations
from .models import Settings, Assets, ScenePlan, LogFn
from .media import BuildError, media_duration_sec, _check, _noop_progress
from .subtitles import build_srt
from .styles import inject_subtitle_style, merge_shadow

def _cc():
    try:
        import pycapcut as cc
        return cc
    except Exception as e:
        raise BuildError("Thiếu pycapcut 0.0.3. Chạy install.bat hoặc: pip install -r requirements.txt") from e

def _sec(v: float) -> str: return f"{max(0.0,float(v)):.6f}s"

def apply_anim_key(seg, key: str, duration: float) -> str:
    """Gắn keyframe của MỘT hiệu ứng cụ thể vào segment. Trả về key đã dùng."""
    cc=_cc()
    if key==animations.MODE_OFF or duration<=0: return animations.MODE_OFF
    specs=animations.keyframes_for(key)
    if not specs: return animations.MODE_OFF
    end=_sec(duration)
    for prop_name,start_val,end_val in specs:
        prop=getattr(cc.KeyframeProperty,prop_name)
        seg.add_keyframe(prop,"0s",float(start_val))
        seg.add_keyframe(prop,end,float(end_val))
    return key

def apply_image_anim(seg, mode: str, duration: float, idx: int=0, picker=None) -> str:
    """Gắn hiệu ứng Ken Burns cho ảnh tĩnh.

    `picker` giữ trạng thái giữa các cảnh (cần cho chế độ ngẫu nhiên không lặp
    liền kề). Nếu không truyền, hàm tự tạo picker mới theo `mode` — giữ tương
    thích ngược với cách gọi cũ.
    """
    if picker is None: picker=animations.AnimPicker(mode)
    return apply_anim_key(seg,picker.pick(idx),duration)

def add_audio(script, track: str, path: Path, start: float, want_len: float, volume: float=1.0, fade_in: float=0, fade_out: float=0):
    cc=_cc(); dur=media_duration_sec(path); seg_len=max(0.02,min(want_len,dur))
    seg=cc.AudioSegment(str(path),cc.trange(_sec(start),_sec(seg_len)),volume=float(volume))
    if fade_in or fade_out: seg.add_fade(_sec(min(fade_in,seg_len/2)),_sec(min(fade_out,seg_len/2)))
    script.add_segment(seg,track); return seg

def _resolve_transition(cc,name: str):
    try:return getattr(cc.TransitionType,name)
    except Exception:
        try:return cc.TransitionType.叠化
        except Exception:return None

def resolve_music_roles(s: Settings, files: list[Path]):
    by_name={f.name:f for f in files}; out=[]
    if s.music_roles:
        for name,r in s.music_roles.items():
            f=by_name.get(name)
            if not f:continue
            out.append((f,bool(r.get("intro")),bool(r.get("bg",True)),float(r.get("volume",r.get("volume_db",1.0)))))
    if not out:
        for i,f in enumerate(files): out.append((f,i==0,True,1.0))
    return out

def register_root_meta(draft_path: Path, log: LogFn=print) -> None:
    meta_path=draft_path/"draft_meta_info.json"; root=draft_path.parent/"root_meta_info.json"
    if not meta_path.is_file() or not root.is_file():return
    try:
        meta=json.loads(meta_path.read_text(encoding="utf-8")); data=json.loads(root.read_text(encoding="utf-8")); store=data.setdefault("all_draft_store",[])
        # CapCut stores paths with forward slashes in some versions
        meta["draft_json_file"]=str((draft_path/"draft_content.json").resolve()).replace("\\","/")
        meta["streaming_edit_draft_ready"]=True
        did=meta.get("draft_id")
        idx=next((i for i,x in enumerate(store) if x.get("draft_id")==did),None)
        if idx is None:store.append(meta)
        else:store[idx]=meta
        backup=root.with_suffix(".json.bak-capcut-draft-studio")
        if not backup.exists():shutil.copy2(root,backup)
        root.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        log("[BUILD] Đã đăng ký project vào root_meta_info.json (có backup).")
    except Exception as e:log(f"[WARN] Không đăng ký được root_meta_info.json: {e}")

def build(s: Settings, a: Assets, plan: list[ScenePlan], log: LogFn=print, srt_out_dir: Path|None=None,
          progress=None, cancel=None) -> Path:
    progress = progress or _noop_progress
    if not plan:raise BuildError("Plan rỗng")
    if not s.capcut_drafts.is_dir():raise BuildError(f"Không thấy CapCut drafts folder: {s.capcut_drafts}")
    cc=_cc(); log(f"[BUILD] Tạo draft '{s.draft_name}' ({s.width}x{s.height} @{s.fps}fps)...")
    anim_picker=animations.AnimPicker(s.image_anim); anim_used: dict[str,int]={}
    if any(p.mode=="IMAGE" for p in plan):
        log(f"[BUILD] Hiệu ứng ảnh: {anim_picker.describe()}")
    folder=cc.DraftFolder(str(s.capcut_drafts)); script=folder.create_draft(s.draft_name,s.width,s.height,s.fps,allow_replace=True)
    script.add_track(cc.TrackType.video,"main",relative_index=0)
    if s.enable_voice:script.add_track(cc.TrackType.audio,"voice")
    if s.enable_bgm and a.bgm_files:
        script.add_track(cc.TrackType.audio,"bgm_a"); script.add_track(cc.TrackType.audio,"bgm_b")
    placed=[it for it in a.sfx_items if s.sfx_roles.get(it["name"])=="placed"]
    muted=[it for it in a.sfx_items if s.sfx_roles.get(it["name"])=="muted"]
    if placed:script.add_track(cc.TrackType.audio,"sfx")
    if muted:script.add_track(cc.TrackType.audio,"sfx_kho",mute=True)
    total=plan[-1].end; trans=_resolve_transition(cc,s.transition_type)
    # visuals + voice
    for idx,p in enumerate(plan):
        _check(cancel); progress("build", idx, len(plan))
        if s.enable_voice:add_audio(script,"voice",p.audio_path,p.start,p.audio_duration,s.voice_vol)
        # HÌNH dài bằng giọng đọc + khoảng nghỉ, tiếng nói vẫn đúng độ dài gốc.
        slot=p.slot_duration
        vvol=float(getattr(s,"video_vol",1.0))
        if p.mode=="IMAGE":
            seg=cc.VideoSegment(str(p.visual_path),cc.trange(_sec(p.start),_sec(slot)))
            used=apply_image_anim(seg,s.image_anim,slot,idx,anim_picker)
            anim_used[used]=anim_used.get(used,0)+1
        elif p.mode=="CUT":
            seg=cc.VideoSegment(str(p.visual_path),cc.trange(_sec(p.start),_sec(slot)),source_timerange=cc.trange("0s",_sec(slot)),speed=1.0,volume=vvol)
        else:
            src_len=min(float(p.video_duration or slot),slot*p.speed)
            seg=cc.VideoSegment(str(p.visual_path),cc.trange(_sec(p.start),_sec(slot)),source_timerange=cc.trange("0s",_sec(src_len)),speed=float(p.speed),volume=vvol)
        if s.enable_transition and trans is not None and idx<len(plan)-1:
            try:seg.add_transition(trans,duration=cc.tim(_sec(min(s.trans_dur,slot/3))))
            except Exception as e:log(f"[WARN] Transition scene {p.number}: {e}")
        script.add_segment(seg,"main")
        if (idx+1)%50==0:log(f"[BUILD] ... {idx+1}/{len(plan)}")
    progress("build", len(plan), len(plan))
    if anim_used:
        detail=", ".join(f"{animations.BY_KEY[k].label if k in animations.BY_KEY else k} {n}"
                         for k,n in sorted(anim_used.items(),key=lambda kv:-kv[1]))
        log(f"[BUILD] Phân bổ hiệu ứng ảnh: {detail}")
    # claim overlay
    if a.claim and s.enable_claim:
        script.add_track(cc.TrackType.video,"claim",relative_index=2)
        dur=min(s.claim_dur,total); script.add_segment(cc.VideoSegment(str(a.claim),cc.trange("0s",_sec(dur))),"claim")
    # logo overlay
    if a.logo and s.enable_logo:
        script.add_track(cc.TrackType.video,"logo",relative_index=3)
        cs=cc.ClipSettings(transform_x=s.logo_x,transform_y=s.logo_y,scale_x=s.logo_scale,scale_y=s.logo_scale)
        script.add_segment(cc.VideoSegment(str(a.logo),cc.trange("0s",_sec(total)),clip_settings=cs),"logo")
        log("[BUILD] Logo watermark OK")
    # BGM: first intro track then round-robin background with crossfades
    if s.enable_bgm and a.bgm_files:
        roles=resolve_music_roles(s,a.bgm_files); intros=[x for x in roles if x[1]]; bgs=[x for x in roles if x[2]]
        bg_start=0.0
        if intros:
            f,_,_,mul=intros[0]; dur=min(media_duration_sec(f),s.bgm_intro_max_dur,total)
            add_audio(script,"bgm_a",f,0,dur,s.bgm_intro_vol_high*mul,0,min(1.0,dur/3)); bg_start=min(s.bgm_intro_high_dur,dur)
        if bgs and bg_start<total:
            cursor=bg_start; toggle=0; guard=0
            while cursor<total-0.02 and guard<2000:
                f,_,_,mul=bgs[guard%len(bgs)]; fd=media_duration_sec(f); want=min(fd,total-cursor); xf=min(s.crossfade_sec,want/3)
                track="bgm_a" if toggle%2==0 else "bgm_b"; add_audio(script,track,f,cursor,want,s.bgm_body_vol*mul,xf if cursor>bg_start else 0,xf)
                cursor += max(0.05,want-xf); toggle+=1; guard+=1
    # SFX placed at scene starts, muted library preloaded after timeline
    for i,it in enumerate(placed):
        t=plan[i%len(plan)].start; d=min(2.0,media_duration_sec(Path(it["path"])),max(0.1,total-t))
        add_audio(script,"sfx",Path(it["path"]),t,d,1.0)
    shelf_cursor=total+1.0
    for it in muted:
        try:d=min(2.0,media_duration_sec(Path(it["path"]))); add_audio(script,"sfx_kho",Path(it["path"]),shelf_cursor,d,1.0); shelf_cursor+=d+0.2
        except Exception:pass
    # subtitles
    _check(cancel); progress("subtitles", 0, 1)
    srt_path=None
    if s.enable_subtitles and s.subtitle_source!="off":
        out=srt_out_dir or (s.input_dir/"_capcut_draft_studio"); srt_path=Path(out)/"subtitles.srt"
        if build_srt(s,plan,srt_path,log):
            script.import_srt(str(srt_path),track_name="subtitles",clip_settings=cc.ClipSettings(transform_y=-0.8))
    _check(cancel); progress("save", 0, 1); log("[BUILD] Đang ghi draft xuống đĩa…")
    script.save(); draft_path=s.capcut_drafts/s.draft_name
    progress("save", 1, 1)
    if srt_path:
        harvested=None
        if s.subtitle_style:
            style_path=s.sub_styles_dir/(s.subtitle_style if s.subtitle_style.endswith(".json") else s.subtitle_style+".json")
            if style_path.is_file():
                try:harvested=json.loads(style_path.read_text(encoding="utf-8"))
                except Exception as e:log(f"[WARN] Không đọc được style '{s.subtitle_style}': {e}")
            else:
                log(f"[WARN] Không thấy file style: {style_path.name}")
        # Không chọn style nào thì vẫn áp bóng đổ mặc định (độ mờ 90%).
        final_style=merge_shadow(harvested,s)
        if final_style:
            try:inject_subtitle_style(draft_path,final_style,log)
            except Exception as e:log(f"[WARN] Inject subtitle style lỗi: {e}")
    if s.register_root_meta:register_root_meta(draft_path,log)
    log(f"[SUCCESS] Draft '{s.draft_name}' đã ghi: {draft_path}")
    return draft_path
