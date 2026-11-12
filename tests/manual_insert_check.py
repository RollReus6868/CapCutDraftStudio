"""Kiểm tra thủ công 0.5.9: ảnh intro + quảng cáo giữa video, render ffmpeg thật.

Tự tạo project giả: mỗi cảnh một MÀU riêng và một "giọng" là âm thuần tần số
riêng; quảng cáo là màu khác hẳn với âm 1500 Hz. Sau khi render, đo màu khung
hình và tần số tiếng ở giữa từng đoạn — hình và tiếng phải cùng một cảnh.

Không nằm trong pytest vì cần ffmpeg và mất khoảng nửa phút.
Chạy:  /usr/bin/python3.12 tests/manual_insert_check.py [thư-mục-tạm]
"""
from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capcut_draft_studio import render  # noqa: E402
from capcut_draft_studio.capcut_engine import clip_len  # noqa: E402
from capcut_draft_studio.media import scan_assets, validate  # noqa: E402
from capcut_draft_studio.models import Settings  # noqa: E402

COLORS = {1: (220, 30, 30), 2: (30, 200, 30), 3: (30, 30, 220), 4: (220, 220, 30)}
FREQ = {1: 300, 2: 500, 3: 700, 4: 900}
AD_COLOR, AD_FREQ = (200, 30, 200), 1500
INTRO_COLOR = (240, 240, 240)
SCENE_SEC, AD_SEC, INTRO_SEC = 3.0, 2.5, 2.0


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


def make_project(root: Path) -> Path:
    (root / "Audio").mkdir(parents=True)
    (root / "Images").mkdir()
    (root / "CH").mkdir()
    for n, (r, g, b) in COLORS.items():
        ff("-f", "lavfi", "-i", f"color=c=0x{r:02x}{g:02x}{b:02x}:s=320x180:d=1",
           "-frames:v", "1", str(root / "Images" / f"{n}.png"))
        ff("-f", "lavfi", "-i", f"sine=f={FREQ[n]}:d={SCENE_SEC}:sample_rate=48000",
           str(root / "Audio" / f"{n}.wav"))
    r, g, b = INTRO_COLOR
    ff("-f", "lavfi", "-i", f"color=c=0x{r:02x}{g:02x}{b:02x}:s=320x180:d=1",
       "-frames:v", "1", str(root / "intro.png"))
    r, g, b = AD_COLOR
    ff("-f", "lavfi", "-i", f"color=c=0x{r:02x}{g:02x}{b:02x}:s=320x180:r=30:d={AD_SEC}",
       "-f", "lavfi", "-i", f"sine=f={AD_FREQ}:d={AD_SEC}:sample_rate=48000",
       "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
       str(root / "ad.mp4"))
    return root


def color_at(path: Path, t: float) -> tuple[int, int, int]:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(path),
                          "-frames:v", "1", "-vf", "crop=iw/4:ih/4,scale=1:1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return tuple(raw[:3])


def freq_at(path: Path, t: float, win: float = 0.25) -> float:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.3f}", "-t", f"{win}",
                          "-i", str(path), "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    vals = struct.unpack(f"<{len(raw) // 2}h", raw)
    if max((abs(v) for v in vals), default=0) < 300:
        return 0.0
    crossings = sum(1 for a, b in zip(vals, vals[1:]) if (a < 0) != (b < 0))
    return crossings / 2 / (len(vals) / 48000)


def near(c, ref, tol=45) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(c, ref))


def main() -> int:
    if not shutil.which("ffmpeg"):
        print("Cần ffmpeg")
        return 2
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="ins-"))
    if root.exists():
        shutil.rmtree(root)
    make_project(root)
    s = Settings(input_dir=root, channel_dir=root / "CH", draft_name="ins",
                 capcut_drafts=root, scene_gap=0.4, gap_mode="fixed",
                 enable_subtitles=False, enable_bgm=False, enable_logo=False,
                 enable_claim=False, trans_dur=0.47, image_anim="off",
                 enable_intro=True, intro_path=root / "intro.png", intro_img_dur=INTRO_SEC,
                 enable_ad=True, ad_path=root / "ad.mp4", ad_after="2",
                 render_res="480", render_crf=28, render_preset="veryfast", render_hw="cpu",
                 render_out_dir=root / "_render")
    log = print
    assets = scan_assets(s, log)
    plan = validate(s, assets, log)
    ad_len = clip_len(root / "ad.mp4", "quảng cáo")
    job = render.RenderJob(name="ins", settings=s, assets=assets, plan=list(plan),
                           out_path=render.default_out_path(s, "ins"))
    out = render.Renderer(job, log=log).run()

    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "csv=p=0", str(out)],
                               capture_output=True, text=True).stdout)
    expect_total = INTRO_SEC + plan[-1].end + ad_len
    ok = abs(dur - expect_total) < 0.12
    print(f"\nTổng thời lượng {dur:.3f}s, kỳ vọng {expect_total:.3f}s → {'OK' if ok else 'SAI'}")

    ad_at = INTRO_SEC + plan[1].end
    checks = [("intro", INTRO_SEC / 2, INTRO_COLOR, 0.0)]
    for p in plan:
        tl = INTRO_SEC + p.start + (ad_len if p.number > 2 else 0.0)
        checks.append((f"cảnh {p.number}", tl + p.audio_duration / 2, COLORS[p.number],
                       FREQ[p.number]))
    checks.append(("quảng cáo", ad_at + ad_len / 2, AD_COLOR, AD_FREQ))
    # sát mép quảng cáo: phải là hình sạch, không hoà cảnh
    checks.append(("ngay trước QC", ad_at - 0.1, COLORS[2], None))
    # tiếng đo từ t-0.12 → cửa sổ bắt đầu 0.05s sau khi quảng cáo kết thúc
    checks.append(("ngay sau QC", ad_at + ad_len + 0.17, COLORS[3], FREQ[3]))
    for name, t, col, fq in sorted(checks, key=lambda c: c[1]):
        c = color_at(out, t)
        f = freq_at(out, t - 0.12) if fq is not None else None
        good = near(c, col) and (fq is None or (abs(f - fq) < 25 if fq else f == 0.0))
        ok &= good
        ftxt = "" if f is None else f" tiếng {f:6.0f} Hz (cần {fq})"
        print(f"  {name:14s} t={t:6.2f}s màu {c} (cần {col}){ftxt} → {'OK' if good else 'SAI'}")
    print("\nKẾT QUẢ:", "ĐẠT" if ok else "KHÔNG ĐẠT")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
