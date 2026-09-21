from __future__ import annotations
import json, re, shutil, subprocess, sys, wave, os
from pathlib import Path
from .models import AUDIO_EXTS, VIDEO_EXTS, IMAGE_EXTS, SFX_EXTS, Assets, Settings, ScenePlan, LogFn

class BuildError(RuntimeError): pass

class Cancelled(RuntimeError):
    """Người dùng bấm Dừng giữa chừng."""

def _noop_progress(phase: str, done: int, total: int) -> None:  # pragma: no cover
    pass

def _check(cancel) -> None:
    """Ném Cancelled nếu callback cancel() trả True."""
    if cancel and cancel():
        raise Cancelled("Đã dừng theo yêu cầu")

class ScenePlanList(list):
    """list[ScenePlan] có thêm .errors — dùng cho chế độ preview."""
    errors: list[str] = []

def scan_numbered(folder: Path, exts: set[str], log: LogFn = print) -> dict[int, Path]:
    out: dict[int, Path] = {}
    if not folder.is_dir(): return out
    priority = {ext: i for i, ext in enumerate(sorted(exts))}
    buckets: dict[int, list[Path]] = {}
    for f in folder.iterdir():
        if f.is_file() and f.suffix.lower() in exts and re.fullmatch(r"\d+", f.stem):
            buckets.setdefault(int(f.stem), []).append(f)
    for n, files in buckets.items():
        files.sort(key=lambda p: (priority.get(p.suffix.lower(), 999), p.name.lower()))
        out[n] = files[0]
        if len(files) > 1:
            log(f"[WARN] Số {n:04d} trùng {len(files)} file trong {folder.name}/ → dùng {files[0].name}")
    return out

def audio_dir(input_dir: Path, log: LogFn = print) -> Path:
    candidates = [p for p in input_dir.iterdir() if p.is_dir() and p.name.lower() in {"audio", "voice", "voices"}]
    if not candidates: return input_dir / "Audio"
    candidates.sort(key=lambda p: (p.name.lower() != "audio", p.name.lower()))
    if len(candidates) > 1: log(f"[WARN] Có nhiều folder audio → dùng '{candidates[0].name}'")
    return candidates[0]

def find_named(folder: Path, stems: tuple[str, ...], exts=IMAGE_EXTS) -> Path | None:
    if not folder.is_dir(): return None
    ss={s.lower() for s in stems}
    for f in sorted(folder.iterdir()):
        if f.is_file() and f.stem.lower() in ss and f.suffix.lower() in exts: return f
    return None

def list_bgm_files(folder: Path) -> list[Path]:
    if not folder.is_dir(): return []
    return sorted([f for f in folder.rglob("*") if f.is_file() and f.suffix.lower() in AUDIO_EXTS and f.stem.lower() != "impact"], key=lambda p:p.name.lower())

def list_sfx_items(sfx_library: Path, channel_dir: Path) -> list[dict]:
    items=[]; seen=set()
    for root, source in [(sfx_library, "library"), (channel_dir/"SFX", "channel")]:
        if not root.is_dir(): continue
        for f in sorted(root.rglob("*")):
            if not f.is_file() or f.suffix.lower() not in SFX_EXTS: continue
            key=str(f.resolve()).lower()
            if key in seen: continue
            seen.add(key)
            category = f.parent.name if source == "library" else "channel"
            items.append({"name": f.name, "path": f, "category": category, "source": source})
    return items

def _override_file(path: Path | None, fallback: Path | None, label: str, log: LogFn) -> Path | None:
    if path:
        p=Path(path)
        if p.is_file(): return p
        log(f"[WARN] {label} override không tồn tại → dùng asset của kênh: {p}")
    return fallback

def scan_assets(s: Settings, log: LogFn = print) -> Assets:
    if not s.input_dir.is_dir(): raise BuildError(f"Không thấy folder INPUT: {s.input_dir}")
    if not s.channel_dir.is_dir(): raise BuildError(f"Không thấy folder KÊNH: {s.channel_dir}")
    adir=audio_dir(s.input_dir,log)
    a=Assets(
        audios=scan_numbered(adir,AUDIO_EXTS,log),
        videos=scan_numbered(s.input_dir/"Videos",VIDEO_EXTS,log),
        images=scan_numbered(s.input_dir/"Images",IMAGE_EXTS,log),
        texts=scan_numbered(s.input_dir/"Texts",{".txt"},log),
    )
    if not a.audios: raise BuildError(f"Không tìm thấy audio đánh số trong {adir}")
    a.logo=_override_file(s.logo_path, find_named(s.channel_dir/"Logo",("logo",)) or find_named(s.channel_dir,("logo",)), "Logo", log) if s.enable_logo else None
    a.claim=_override_file(s.claim_path, find_named(s.channel_dir/"Text Claim",("text claim","claim")) or find_named(s.channel_dir,("text claim","claim")), "Claim", log) if s.enable_claim else None
    bgm_src=Path(s.bgm_dir) if s.bgm_dir and Path(s.bgm_dir).is_dir() else s.channel_dir/"BGM"
    a.bgm_files=list_bgm_files(bgm_src) if s.enable_bgm else []
    a.impact=find_named(bgm_src,("impact",),AUDIO_EXTS) if s.enable_impact else None
    a.sfx_items=list_sfx_items(s.sfx_library_dir,s.channel_dir)
    log(f"[SCAN] Audio {len(a.audios)} | Video {len(a.videos)} | Image {len(a.images)} | Text {len(a.texts)}")
    log(f"[SCAN] BGM {len(a.bgm_files)} | SFX {len(a.sfx_items)} | Logo {'có' if a.logo else 'không'} | Claim {'có' if a.claim else 'không'}")
    return a

def media_duration_sec(path: Path) -> float:
    # 1) pymediainfo
    try:
        from pymediainfo import MediaInfo
        info=MediaInfo.parse(str(path))
        for t in info.tracks:
            if t.track_type in ("General","Video","Audio") and t.duration:
                v=float(t.duration)/1000.0
                if v>0: return v
    except Exception: pass
    # 2) ffprobe if present
    ffprobe=shutil.which("ffprobe")
    if ffprobe:
        try:
            cp=subprocess.run([ffprobe,"-v","error","-show_entries","format=duration","-of","json",str(path)],capture_output=True,text=True,timeout=20)
            v=float(json.loads(cp.stdout)["format"]["duration"])
            if v>0:return v
        except Exception: pass
    # 3) WAV stdlib
    if path.suffix.lower()==".wav":
        with wave.open(str(path),"rb") as w:
            return w.getnframes()/float(w.getframerate())
    raise BuildError(f"Không đọc được duration: {path}")

def validate(s: Settings, a: Assets, log: LogFn = print, progress=None, cancel=None,
             collect_errors: bool = False) -> list[ScenePlan]:
    """Lập kế hoạch dựng cho từng scene.

    progress(phase, done, total) được gọi sau mỗi scene.
    cancel() trả True -> ném Cancelled.
    collect_errors=True -> không ném BuildError mà gắn lỗi vào thuộc tính
    .errors của list trả về (dùng cho bảng preview trong GUI).
    """
    progress = progress or _noop_progress
    if any(ch in s.draft_name for ch in '<>:"/\\|?*'):
        raise BuildError(f"Tên project chứa ký tự cấm: {s.draft_name}")
    plan=[]; cursor=0.0; errors=[]
    nums=sorted(a.audios)
    gap=max(0.0,float(getattr(s,"scene_gap",0.0) or 0.0))
    log(f"[VALIDATE] Kiểm tra {len(nums)} audio...")
    if gap>0:
        log(f"[VALIDATE] Khoảng nghỉ giữa các cảnh: {gap:.2f}s (hình cảnh trước được kéo dài để lấp)")
    for i,n in enumerate(nums,1):
        _check(cancel)
        progress("validate", i-1, len(nums))
        ap=a.audios[n]
        try: ad=media_duration_sec(ap)
        except Exception as e:
            errors.append(f"{n:04d}: audio lỗi ({e})"); continue
        # Cảnh cuối không cần khoảng nghỉ — video sẽ kết thúc ngay sau giọng đọc.
        g=0.0 if i==len(nums) else gap
        slot=ad+g            # độ dài HÌNH của cảnh này
        gap_note=f" + nghỉ {g:.2f}s" if g>0 else ""
        visual_num=int(s.hook_overrides.get(str(n), n))
        vp=a.videos.get(visual_num); ip=a.images.get(visual_num)
        mode=None; vdur=None; speed=1.0; visual=None
        if vp:
            try:
                vdur=media_duration_sec(vp)
                if vdur >= slot:
                    if s.enable_cut:
                        mode="CUT"; speed=1.0
                    else:
                        mode="SPEEDUP"; speed=max(1.0,vdur/slot)
                    visual=vp
                else:
                    required=max(0.01,vdur/slot)
                    if s.enable_slow and required >= s.min_speed:
                        mode="SLOW"; speed=required; visual=vp
                    elif ip:
                        mode="IMAGE"; visual=ip
                    else:
                        errors.append(
                            f"{n:04d}: video ngắn ({vdur:.2f}s) so với audio ({ad:.2f}s{gap_note}), "
                            "không đủ slow và không có ảnh fallback")
                        continue
            except Exception as e:
                if ip:
                    log(f"[WARN] Cảnh {n}: video lỗi → dùng ảnh fallback {ip.name}")
                    mode="IMAGE"; visual=ip
                else:
                    errors.append(f"{n:04d}: video lỗi ({e}) và không có ảnh fallback"); continue
        elif ip:
            mode="IMAGE"; visual=ip
        else:
            errors.append(f"{n:04d}: thiếu cả video lẫn ảnh"); continue
        plan.append(ScenePlan(n,ap,ad,mode,visual,vdur,speed,cursor,g))
        cursor += slot
        if i%20==0: log(f"[VALIDATE] ... {i}/{len(nums)}")
    progress("validate", len(nums), len(nums))
    if errors and not collect_errors:
        for e in errors: log("[FAIL] "+e)
        raise BuildError(f"{len(errors)} scene thiếu/lỗi asset")
    counts={m:sum(p.mode==m for p in plan) for m in ("CUT","SLOW","SPEEDUP","IMAGE")}
    log(f"[VALIDATE] OK — CUT {counts['CUT']} | SLOW {counts['SLOW']} | SPEEDUP {counts['SPEEDUP']} | IMAGE {counts['IMAGE']}")
    log(f"[PLAN] Tổng thời lượng: {cursor/60:.1f} phút ({cursor:.1f}s)")
    if collect_errors:
        for e in errors: log("[FAIL] "+e)
        plan = ScenePlanList(plan); plan.errors = errors
    return plan

def harvest_sfx_from_capcut(sfx_library: Path, capcut_drafts: Path, log: LogFn=print) -> int:
    """Copy named local audio resources from existing drafts into library/harvested."""
    dest=Path(sfx_library)/"harvested"; dest.mkdir(parents=True,exist_ok=True)
    if not Path(capcut_drafts).is_dir():
        log(f"[WARN] Không thấy CapCut drafts: {capcut_drafts}"); return 0
    copied=0; found=0
    for dc in Path(capcut_drafts).glob("*/draft_content.json"):
        try:data=json.loads(dc.read_text(encoding="utf-8"))
        except Exception:continue
        for m in (data.get("materials") or {}).get("audios",[]):
            ty=str(m.get("type","")).strip().lower(); nm=str(m.get("name","")).strip(); src=Path(str(m.get("path","")).strip())
            if ty not in {"sound","music"} or not nm or not src.is_file():continue
            if re.fullmatch(r"\d+",src.stem):continue
            found+=1; safe=re.sub(r'[<>:"/\\|?*]+','_',nm).strip(' .')[:60] or 'sfx'; dst=dest/(safe+src.suffix.lower())
            if dst.exists():continue
            try:shutil.copy2(src,dst);copied+=1;log(f"  + harvested/{dst.name}")
            except OSError as e:log(f"[WARN] Không copy được {src.name}: {e}")
    log(f"[HARVEST] Nhập {copied} SFX mới từ CapCut (tổng tìm thấy {found} có tên).")
    return copied

def capcut_running() -> bool:
    """CapCut / CapCut (Jianying) có đang mở không — hỗ trợ cả Windows và macOS."""
    if os.name=="nt":
        try:
            cp=subprocess.run(["tasklist"],capture_output=True,text=True,timeout=8)
            out=cp.stdout.lower()
            return any(name in out for name in ("capcut.exe","jianyingpro.exe"))
        except Exception:return False
    if sys.platform=="darwin":
        for args in (["pgrep","-x","CapCut"],["pgrep","-f","CapCut.app"]):
            try:
                if subprocess.run(args,capture_output=True,text=True,timeout=5).returncode==0:
                    return True
            except Exception:pass
        return False
    return False
