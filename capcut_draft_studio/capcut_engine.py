from __future__ import annotations
import json, math, os, random, shutil, time
from dataclasses import replace
from pathlib import Path
from . import animations
from .models import Settings, Assets, ScenePlan, LogFn
from .media import BuildError, media_duration_sec, natural_key, _check, _noop_progress
from .subtitles import build_srt
from .styles import inject_subtitle_style, merge_shadow

def _cc():
    try:
        import pycapcut as cc
        return cc
    except Exception as e:
        raise BuildError("Thiếu pycapcut 0.0.3. Chạy install.bat hoặc: pip install -r requirements.txt") from e

def _sec(v: float) -> str: return f"{max(0.0,float(v)):.6f}s"

def apply_anim_key(seg, key: str, duration: float, zoom: float=1.0) -> str:
    """Gắn keyframe của MỘT hiệu ứng cụ thể vào segment. Trả về key đã dùng.

    `zoom` (vd 1.02) nhân vào keyframe phóng to; keyframe `uniform_scale` đè lên
    clip_settings nên phải nhân ở đây, nếu không ảnh có hiệu ứng mất phần phóng to.
    """
    cc=_cc()
    if key==animations.MODE_OFF or duration<=0: return animations.MODE_OFF
    specs=animations.keyframes_for(key)
    if not specs: return animations.MODE_OFF
    end=_sec(duration)
    for prop_name,start_val,end_val in specs:
        prop=getattr(cc.KeyframeProperty,prop_name)
        mul=zoom if prop_name=="uniform_scale" else 1.0
        seg.add_keyframe(prop,"0s",float(start_val)*mul)
        seg.add_keyframe(prop,end,float(end_val)*mul)
    return key

def apply_image_anim(seg, mode: str, duration: float, idx: int=0, picker=None, zoom: float=1.0) -> str:
    """Gắn hiệu ứng Ken Burns cho ảnh tĩnh.

    `picker` giữ trạng thái giữa các cảnh (cần cho chế độ ngẫu nhiên không lặp
    liền kề). Nếu không truyền, hàm tự tạo picker mới theo `mode` — giữ tương
    thích ngược với cách gọi cũ.
    """
    if picker is None: picker=animations.AnimPicker(mode)
    return apply_anim_key(seg,picker.pick(idx),duration,zoom)

_AUDIO_MATERIALS: dict[str, object] = {}

def _audio_material(cc, path: Path):
    """AudioMaterial có cache — một bài nhạc nền được dùng lại nhiều lần."""
    st=Path(path).stat()
    key=(str(path),st.st_size,st.st_mtime_ns)
    mat=_AUDIO_MATERIALS.get(key)
    if mat is None:
        mat=cc.AudioMaterial(str(path)); _AUDIO_MATERIALS[key]=mat
    return mat

def audio_len(path: Path) -> float:
    """Độ dài dùng được của file âm thanh trên timeline CapCut.

    pycapcut đo theo LUỒNG ÂM THANH, còn media_duration_sec đọc độ dài cả file
    (General) — với mp3 có ảnh bìa / khung trống hai số lệch nhau vài giây
    (180s vs 178.67s) và pycapcut báo "超出了素材时长". Lấy số nhỏ hơn.
    """
    dur=media_duration_sec(path)
    try:
        mdur=getattr(_audio_material(_cc(),path),"duration",None)
        if isinstance(mdur,(int,float)) and mdur>0: dur=min(dur,mdur/1e6)
    except Exception:
        pass
    return dur

_VIDEO_MATERIALS: dict[tuple, object] = {}

def video_len(path: Path) -> float:
    """Như audio_len nhưng cho video: pycapcut đo theo LUỒNG HÌNH, file có tiếng dài
    hơn hình vài ms (vd VIdeo_QC.mp4: 26.053s vs 26.050s) làm VideoSegment báo
    "超出了素材时长" — đó là lỗi chèn video intro của 0.5.6."""
    dur=media_duration_sec(path)
    try:
        st=Path(path).stat(); key=(str(path),st.st_size,st.st_mtime_ns)
        mat=_VIDEO_MATERIALS.get(key)
        if mat is None:
            mat=_cc().VideoMaterial(str(path)); _VIDEO_MATERIALS[key]=mat
        mdur=getattr(mat,"duration",None)
        if isinstance(mdur,(int,float)) and mdur>0: dur=min(dur,mdur/1e6)
    except Exception:
        pass
    return max(0.0,dur-1e-6)

def list_audio_files(folder) -> list[Path]:
    from .models import AUDIO_EXTS
    p=Path(folder) if folder else None
    if not p or not p.is_dir():return []
    return sorted([f for f in p.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXTS],
                  key=lambda f:natural_key(f.name))

def pick_cid(s: Settings, rng=None) -> Path | None:
    """Bài nhạc CID: chọn NGẪU NHIÊN 1 bài trong folder đã chọn (mỗi lần dựng)."""
    if not getattr(s,"enable_cid",False):return None
    files=list_audio_files(getattr(s,"cid_dir",None))
    if not files:raise BuildError("Đã bật nhạc CID nhưng folder nhạc CID không có file âm thanh nào.")
    return (rng or random.Random()).choice(files)

def cid_window(total: float, off: float, length: float) -> tuple[float,float]:
    """(bắt đầu, độ dài) của nhạc CID: kết thúc đúng lúc cảnh cuối kết thúc;
    bài dài hơn phần nội dung thì bắt đầu ngay cảnh đầu và bị cắt."""
    avail=max(0.0,total-off)
    ln=min(length,avail)
    return total-ln, ln

def add_audio(script, track: str, path: Path, start: float, want_len: float, volume: float=1.0, fade_in: float=0, fade_out: float=0):
    cc=_cc(); dur=audio_len(path)
    try:mat=_audio_material(cc,path)
    except Exception:mat=str(path)
    seg_len=max(0.02,min(want_len,dur)-1e-6)
    seg=cc.AudioSegment(mat,cc.trange(_sec(start),_sec(seg_len)),volume=float(volume))
    if fade_in or fade_out: seg.add_fade(_sec(min(fade_in,seg_len/2)),_sec(min(fade_out,seg_len/2)))
    script.add_segment(seg,track); return seg

def _resolve_transition(cc,name: str):
    try:return getattr(cc.TransitionType,name)
    except Exception:
        try:return cc.TransitionType.叠化
        except Exception:return None

BGM_LAYER=1   # relative_index của các track nhạc nền (xem chú thích ở build())

def resolve_music_roles(s: Settings, files: list[Path], rng=None):
    """[(file, là intro?, là nhạc nền?, hệ số âm lượng)] theo thứ tự sẽ chèn.

    `s.bgm_order`: "number" = theo số trong tên file (1, 2 … 10, 11 — không phải
    1, 10, 11, 2 như sắp xếp chữ); "random" = xáo trộn (truyền `rng` để cố định).
    """
    files=sorted(files,key=lambda f:natural_key(f.name)); out=[]
    if s.music_roles:
        for f in files:
            r=s.music_roles.get(f.name)
            if r is None:continue
            out.append((f,bool(r.get("intro")),bool(r.get("bg",True)),float(r.get("volume",r.get("volume_db",1.0)))))
    if not out:
        out=[(f,False,True,1.0) for f in files]
        if str(getattr(s,"bgm_order","number"))=="random":
            (rng or random.Random()).shuffle(out)
        # mặc định bài ĐẦU TIÊN (sau khi sắp/xáo) làm intro như các bản trước
        if out:out[0]=(out[0][0],True,True,1.0)
        return out
    if str(getattr(s,"bgm_order","number"))=="random":
        (rng or random.Random()).shuffle(out)
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

def clip_len(path: Path, label: str) -> float:
    """Độ dài (giây) của file intro/outro; báo lỗi dễ hiểu nếu không đọc được."""
    try:
        d=float(video_len(Path(path)))
    except Exception as e:
        raise BuildError(f"Không đọc được độ dài file {label}: {Path(path).name} ({e})") from e
    if d<=0.05:raise BuildError(f"File {label} quá ngắn hoặc hỏng: {Path(path).name}")
    return d

def build(s: Settings, a: Assets, plan: list[ScenePlan], log: LogFn=print, srt_out_dir: Path|None=None,
          progress=None, cancel=None) -> Path:
    progress = progress or _noop_progress
    if not plan:raise BuildError("Plan rỗng")
    # Intro: đẩy toàn bộ timeline lùi lại đúng bằng độ dài intro. Outro: nối sau cảnh cuối.
    intro,outro=s.intro_file(),s.outro_file()
    off=clip_len(intro,"intro") if intro else 0.0
    outro_len=clip_len(outro,"outro") if outro else 0.0
    if off>0:
        plan=[replace(p,start=p.start+off) for p in plan]
        log(f"[BUILD] Intro: {intro.name} ({off:.2f}s) — các cảnh lùi lại {off:.2f}s")
    if not s.capcut_drafts.is_dir():raise BuildError(f"Không thấy CapCut drafts folder: {s.capcut_drafts}")
    cc=_cc(); log(f"[BUILD] Tạo draft '{s.draft_name}' ({s.width}x{s.height} @{s.fps}fps)...")
    anim_picker=animations.AnimPicker(s.image_anim); anim_used: dict[str,int]={}
    if any(p.mode=="IMAGE" for p in plan):
        log(f"[BUILD] Hiệu ứng ảnh: {anim_picker.describe()}")
    folder=cc.DraftFolder(str(s.capcut_drafts)); script=folder.create_draft(s.draft_name,s.width,s.height,s.fps,allow_replace=True)
    script.add_track(cc.TrackType.video,"main",relative_index=0)
    # Thứ tự hàng audio trong timeline CapCut: track có render_index NHỎ hơn nằm
    # TRÊN (sát video). 0.5.5 làm ngược nên nhạc nền nằm trên giọng đọc. Nay:
    # giọng đọc (0) → SFX (0) → nhạc nền (1) → kho SFX tắt tiếng (2).
    if s.enable_voice:script.add_track(cc.TrackType.audio,"voice",relative_index=0)
    placed=[it for it in a.sfx_items if s.sfx_roles.get(it["name"])=="placed"]
    muted=[it for it in a.sfx_items if s.sfx_roles.get(it["name"])=="muted"]
    if placed:script.add_track(cc.TrackType.audio,"sfx",relative_index=0)
    if s.enable_bgm and a.bgm_files:
        script.add_track(cc.TrackType.audio,"bgm_a",relative_index=BGM_LAYER)
        script.add_track(cc.TrackType.audio,"bgm_b",relative_index=BGM_LAYER)
    if muted:script.add_track(cc.TrackType.audio,"sfx_kho",mute=True,relative_index=BGM_LAYER+1)
    zoom=max(0.5,min(2.0,float(getattr(s,"visual_zoom",100.0) or 100.0)/100.0))
    zoom_cs=(lambda:cc.ClipSettings(scale_x=zoom,scale_y=zoom)) if abs(zoom-1.0)>1e-6 else (lambda:None)
    if abs(zoom-1.0)>1e-6:log(f"[BUILD] Phóng to hình/video: {zoom*100:.0f}%")
    total=plan[-1].end; trans=_resolve_transition(cc,s.transition_type)
    if intro:
        script.add_segment(cc.VideoSegment(str(intro),cc.trange("0s",_sec(off))),"main")
    # visuals + voice
    for idx,p in enumerate(plan):
        _check(cancel); progress("build", idx, len(plan))
        if s.enable_voice:add_audio(script,"voice",p.audio_path,p.start,p.audio_duration,s.voice_vol)
        # HÌNH dài bằng giọng đọc + khoảng nghỉ, tiếng nói vẫn đúng độ dài gốc.
        slot=p.slot_duration
        vvol=float(getattr(s,"video_vol",1.0))
        zkw={"clip_settings":zoom_cs()} if abs(zoom-1.0)>1e-6 else {}
        if p.mode=="IMAGE":
            seg=cc.VideoSegment(str(p.visual_path),cc.trange(_sec(p.start),_sec(slot)),**zkw)
            used=apply_image_anim(seg,s.image_anim,slot,idx,anim_picker,zoom=zoom)
            anim_used[used]=anim_used.get(used,0)+1
        elif p.mode=="CUT":
            vl=video_len(p.visual_path)
            if vl+1e-6<slot:
                # file "dài" hơn luồng hình vài ms → chậm lại cực nhẹ cho vừa ô cảnh,
                # thay vì để pycapcut báo vượt độ dài tư liệu
                seg=cc.VideoSegment(str(p.visual_path),cc.trange(_sec(p.start),_sec(slot)),source_timerange=cc.trange("0s",_sec(vl)),volume=vvol,**zkw)
            else:
                seg=cc.VideoSegment(str(p.visual_path),cc.trange(_sec(p.start),_sec(slot)),source_timerange=cc.trange("0s",_sec(slot)),speed=1.0,volume=vvol,**zkw)
        else:
            src_len=min(float(p.video_duration or slot),slot*p.speed,video_len(p.visual_path))
            # src_len hụt so với slot*speed (luồng hình ngắn hơn số đọc được) → để
            # pycapcut tự tính tốc độ cho đoạn vẫn dài đúng bằng ô cảnh
            sp=float(p.speed) if src_len>=slot*p.speed-1e-4 else None
            seg=cc.VideoSegment(str(p.visual_path),cc.trange(_sec(p.start),_sec(slot)),source_timerange=cc.trange("0s",_sec(src_len)),speed=sp,volume=vvol,**zkw)
        if s.enable_transition and trans is not None and idx<len(plan)-1:
            try:seg.add_transition(trans,duration=cc.tim(_sec(min(s.trans_dur,slot/3))))
            except Exception as e:log(f"[WARN] Transition scene {p.number}: {e}")
        script.add_segment(seg,"main")
        if (idx+1)%50==0:log(f"[BUILD] ... {idx+1}/{len(plan)}")
    progress("build", len(plan), len(plan))
    if outro:
        script.add_segment(cc.VideoSegment(str(outro),cc.trange(_sec(total),_sec(outro_len))),"main")
        log(f"[BUILD] Outro: {outro.name} ({outro_len:.2f}s)")
    if anim_used:
        detail=", ".join(f"{animations.BY_KEY[k].label if k in animations.BY_KEY else k} {n}"
                         for k,n in sorted(anim_used.items(),key=lambda kv:-kv[1]))
        log(f"[BUILD] Phân bổ hiệu ứng ảnh: {detail}")
    # claim overlay
    if a.claim and s.enable_claim:
        script.add_track(cc.TrackType.video,"claim",relative_index=2)
        dur=min(s.claim_dur,total-off); script.add_segment(cc.VideoSegment(str(a.claim),cc.trange(_sec(off),_sec(dur))),"claim")
    # logo overlay
    if a.logo and s.enable_logo:
        script.add_track(cc.TrackType.video,"logo",relative_index=3)
        cs=cc.ClipSettings(transform_x=s.logo_x,transform_y=s.logo_y,scale_x=s.logo_scale,scale_y=s.logo_scale)
        script.add_segment(cc.VideoSegment(str(a.logo),cc.trange(_sec(off),_sec(total-off)),clip_settings=cs),"logo")
        log("[BUILD] Logo watermark OK")
    # Nhạc CID (0.5.8): 1 bài ngẫu nhiên trong folder CID, đặt SAU điểm kết thúc
    # video (sau cảnh cuối và outro), nguyên bài. Nhạc nền trong video giữ nguyên.
    bgm_total=total
    cid=pick_cid(s)
    if cid:
        cid_start=total+outro_len; cid_ln=audio_len(cid)
        script.add_track(cc.TrackType.audio,"cid",relative_index=BGM_LAYER)
        add_audio(script,"cid",cid,cid_start,cid_ln,float(getattr(s,"cid_vol",1.0)))
        log(f"[BUILD] Nhạc CID: {cid.name} ({cid_ln:.1f}s, âm lượng {float(getattr(s,'cid_vol',1.0)):.2f}) "
            f"đặt sau video, từ {cid_start:.1f}s")
    # Mã QR (0.5.8): góc dưới phải, dài bằng video intro (không có intro → qr_dur giây)
    qr=s.qr_file() if hasattr(s,"qr_file") else None
    if qr:
        qlen=off if off>0 else max(0.5,float(getattr(s,"qr_dur",5.0)))
        script.add_track(cc.TrackType.video,"qr",relative_index=4)
        qcs=cc.ClipSettings(transform_x=float(s.qr_x),transform_y=float(s.qr_y),
                            scale_x=float(s.qr_scale),scale_y=float(s.qr_scale))
        script.add_segment(cc.VideoSegment(str(qr),cc.trange("0s",_sec(qlen)),clip_settings=qcs),"qr")
        log(f"[BUILD] Mã QR: {qr.name} ({qlen:.1f}s)")
    # BGM: first intro track then round-robin background with crossfades
    if s.enable_bgm and a.bgm_files:
        total_all,total=total,bgm_total   # trong khối nhạc nền: "total" = điểm dừng nhạc nền
        roles=resolve_music_roles(s,a.bgm_files); intros=[x for x in roles if x[1]]; bgs=[x for x in roles if x[2]]
        log(f"[BUILD] Âm lượng: giọng đọc {float(s.voice_vol):.2f} · nhạc nền {float(s.bgm_body_vol):.2f}"
            + (f" · bài intro {intros[0][0].name} {float(s.bgm_intro_vol_high):.2f}→{float(s.bgm_intro_vol_low):.2f}"
               if intros else ""))
        bg_start=off      # nhạc nền bắt đầu cùng cảnh đầu tiên (sau video intro)
        # Mỗi track nhạc ghi nhớ thời điểm đoạn cuối của nó kết thúc. Nhạc intro
        # kéo dài tới bgm_intro_max_dur (59s) trong khi nhạc thân bài vào từ giây
        # bgm_intro_high_dur (12s) — hai đoạn CHỒNG nhau, nên không được nằm cùng
        # một track (pycapcut báo SegmentOverlap). Luôn đặt đoạn mới vào track đã
        # trống tại thời điểm đó, thiếu thì mở thêm track.
        track_end={"bgm_a":off,"bgm_b":off}
        def pick_track(at: float) -> str:
            for name,end in sorted(track_end.items(),key=lambda kv:kv[1]):
                if end<=at+1e-6:return name
            name=f"bgm_{chr(ord('a')+len(track_end))}"
            script.add_track(cc.TrackType.audio,name,relative_index=BGM_LAYER); track_end[name]=off
            return name
        if intros:
            f,_,_,mul=intros[0]; dur=min(audio_len(f),s.bgm_intro_max_dur,total-off)
            seg=add_audio(script,"bgm_a",f,off,dur,s.bgm_intro_vol_high*mul,0,min(1.0,dur/3)); bg_start=off+min(s.bgm_intro_high_dur,dur)
            # Bài intro: to (Intro to) trong "Intro giữ to" giây đầu, rồi hạ về
            # "Intro nhỏ" trong 1 giây. Trước 0.5.6 mức nhỏ không được dùng nên
            # bài intro phát to suốt tới 59s, đè cả giọng đọc lẫn nhạc thân bài.
            hi,lo,hold=float(s.bgm_intro_vol_high)*mul,float(s.bgm_intro_vol_low)*mul,float(s.bgm_intro_high_dur)
            if dur>hold+0.5 and abs(hi-lo)>1e-6:
                try:
                    ramp=min(1.0,dur-hold)
                    seg.add_keyframe(0,hi); seg.add_keyframe(int(hold*1e6),hi)
                    seg.add_keyframe(int((hold+ramp)*1e6),lo)
                except Exception as e:log(f"[WARN] Không đặt được âm lượng nhạc intro: {e}")
            track_end["bgm_a"]=off+dur
        if bgs and bg_start<total:
            cursor=bg_start; guard=0
            while cursor<total-0.02 and guard<2000:
                # Dưới 1 giây còn lại: đoạn trước đang mờ dần tới gần cuối rồi, thêm
                # một mẩu nhạc vụn chỉ sinh ra hàng loạt đoạn 0.1s chồng nhau.
                if guard>0 and total-cursor<1.0:break
                f,_,_,mul=bgs[guard%len(bgs)]; fd=audio_len(f); want=min(fd,total-cursor); xf=min(s.crossfade_sec,want/3)
                track=pick_track(cursor); add_audio(script,track,f,cursor,want,s.bgm_body_vol*mul,xf if cursor>bg_start else 0,xf)
                track_end[track]=cursor+want
                cursor += max(0.05,want-xf); guard+=1
        total=total_all
    # SFX placed at scene starts, muted library preloaded after timeline
    for i,it in enumerate(placed):
        t=plan[i%len(plan)].start; d=min(2.0,audio_len(Path(it["path"])),max(0.1,total-t))
        add_audio(script,"sfx",Path(it["path"]),t,d,1.0)
    shelf_cursor=total+outro_len+(audio_len(cid) if cid else 0.0)+1.0
    for it in muted:
        try:d=min(2.0,audio_len(Path(it["path"]))); add_audio(script,"sfx_kho",Path(it["path"]),shelf_cursor,d,1.0); shelf_cursor+=d+0.2
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
