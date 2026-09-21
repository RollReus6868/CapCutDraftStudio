"""Kiểm tra thủ công: dựng plan + render thật bằng ffmpeg rồi đo lại kết quả.

Không nằm trong bộ pytest vì cần ffmpeg và mất vài chục giây.
Chạy:  /usr/bin/python3.12 tests/manual_render_check.py <thư-mục-project>
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capcut_draft_studio import render
from capcut_draft_studio.media import scan_assets, validate
from capcut_draft_studio.models import Settings
from capcut_draft_studio.subtitles import build_srt


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True).stdout
    return json.loads(out)


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    gap = float(sys.argv[2]) if len(sys.argv) > 2 else 0.4
    s = Settings(
        input_dir=root, channel_dir=root / "CH", draft_name="test",
        capcut_drafts=root / "drafts",
        width=1920, height=1080, fps=30,
        scene_gap=gap, video_vol=0.5,
        render_res="720", render_crf=28, render_preset="veryfast",
        render_out_dir=root / "_render",
    )
    log = lambda m: print(m)
    assets = scan_assets(s, log)
    plan = validate(s, assets, log)
    print("\n--- PLAN ---")
    for p in plan:
        print(f"  {p.number:02d} {p.mode:7s} start={p.start:6.2f} audio={p.audio_duration:5.2f} "
              f"gap={p.gap:4.2f} slot={p.slot_duration:5.2f} speed={p.speed:.3f} end={p.end:6.2f}")
    expect = plan[-1].end
    print(f"  tổng = {expect:.2f}s")

    srt = root / "_render" / "subs.srt"
    build_srt(s, plan, srt, log)
    print("\n--- SRT (6 dòng đầu) ---")
    print("\n".join(srt.read_text(encoding="utf-8").splitlines()[:8]))

    job = render.RenderJob(name="test", settings=s, assets=assets, plan=list(plan),
                           out_path=render.default_out_path(s, "test"), srt_path=srt)
    seen = []
    r = render.Renderer(job, log=log,
                        progress=lambda ph, pct, eta: seen.append((ph, round(pct, 1), round(eta))))
    out = r.run()

    info = probe(out)
    dur = float(info["format"]["duration"])
    vs = [st for st in info["streams"] if st["codec_type"] == "video"][0]
    aus = [st for st in info["streams"] if st["codec_type"] == "audio"]
    print("\n--- KẾT QUẢ ---")
    print(f"  file      : {out} ({int(info['format']['size']) / 1e6:.2f} MB)")
    print(f"  thời lượng: {dur:.2f}s (mong đợi {expect:.2f}s, lệch {abs(dur - expect):.2f}s)")
    print(f"  hình      : {vs['width']}x{vs['height']} @ {vs.get('r_frame_rate')}")
    print(f"  tiếng     : {len(aus)} stream {[a['codec_name'] for a in aus]}")
    print(f"  mốc % ghi nhận: {len(seen)} — cuối: {seen[-3:]}")
    ok = abs(dur - expect) < 0.6 and vs["height"] == 720 and len(aus) == 1
    print("\n" + ("[OK] Render đạt." if ok else "[FAIL] Kết quả không như mong đợi."))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
