"""Kiểm tra thủ công cả chuỗi: giao diện → hàng đợi → render ra file thật.

Chạy chuỗi đúng như khi bấm nút, nhưng gọi thẳng trên luồng chính để thấy lỗi
ngay thay vì nuốt vào queue.

    Xvfb :99 -screen 0 1440x920x24 &
    DISPLAY=:99 /usr/bin/python3.12 tests/manual_queue_check.py <thư-mục-project>
"""
from __future__ import annotations

import json
import subprocess
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capcut_draft_studio.ui import pages
from capcut_draft_studio.ui.app import App


def main() -> int:
    root_dir = Path(sys.argv[1]).resolve()
    root = tk.Tk()
    app = App(root)

    app.vars["input_dir"].set(str(root_dir))
    app.vars["channel_dir"].set(str(root_dir / "CH"))
    app.vars["capcut_drafts"].set(str(root_dir / "drafts"))
    (root_dir / "drafts").mkdir(exist_ok=True)
    app.vars["draft_name"].set("queue-test")
    app.vars["scene_gap"].set("0.3")
    app.vars["video_vol"].set("0.4")
    app.vars["render_res"].set("480")
    app.vars["render_crf"].set("30")
    app.vars["render_preset"].set("veryfast")
    app.vars["render_out_dir"].set(str(root_dir / "_queue"))
    app.refresh_all_lists()
    root.update()

    pages.add_current_to_queue(app)
    assert len(app.render_queue) == 1, "không thêm được vào hàng đợi"
    item = app.render_queue[0]
    print("hàng đợi:", item["name"], "| số nhạc nền:", len(item["values"]["_music_roles"]))

    seen: list[tuple[float, float]] = []
    out = app._render_one(item, "ffmpeg", log=lambda m: print("   ", m),
                          cancel=lambda: False,
                          on_prog=lambda pct, eta: seen.append((pct, eta)))
    root.destroy()

    info = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(out)],
        capture_output=True, text=True).stdout)
    dur = float(info["format"]["duration"])
    vs = next(s for s in info["streams"] if s["codec_type"] == "video")
    expect = item["duration"]
    print(f"\nfile      : {out}")
    print(f"thời lượng: {dur:.2f}s (mong đợi {expect:.2f}s)")
    print(f"hình      : {vs['width']}x{vs['height']}")
    print(f"số mốc %  : {len(seen)}, cuối cùng {seen[-1] if seen else None}")
    ok = abs(dur - expect) < 0.6 and vs["height"] == 480 and len(seen) > 5
    print("[OK] Chuỗi hàng đợi chạy đúng." if ok else "[FAIL] Kết quả sai.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
