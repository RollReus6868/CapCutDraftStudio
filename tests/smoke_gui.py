"""Smoke test giao diện: dựng App thật, mở mọi trang và mọi tab con, chụp ảnh.

Chạy headless:
    Xvfb :99 -screen 0 1440x920x24 &
    DISPLAY=:99 /usr/bin/python3.12 tests/smoke_gui.py <thư-mục-ảnh>
"""
from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capcut_draft_studio.ui import pages
from capcut_draft_studio.ui.app import App, NAV


def shot(root: tk.Tk, path: Path) -> None:
    root.update_idletasks()
    root.update()
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["import", "-window", "root", str(path)], check=True)


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "shots")
    root = tk.Tk()
    app = App(root)
    root.update()

    # vài dòng log giả để xem màu
    for line in ("[SCAN] Audio 42 | Video 40 | Image 12 | Text 42",
                 "[VALIDATE] Khoảng nghỉ giữa các cảnh: 0.40s",
                 "[OK] Kiểm tra đạt — 42 cảnh sẵn sàng",
                 "[WARN] Cảnh 7: video lỗi → dùng ảnh fallback 7.jpg",
                 "[RENDER] test: 1920x1080 @30fps, 42 cảnh, 12.4 phút",
                 "[ERROR] 2 scene thiếu/lỗi asset"):
        app.log(line)

    # bảng cảnh quay giả để nhìn được màu của từng chế độ dựng
    from pathlib import Path as _P

    from capcut_draft_studio.models import ScenePlan
    demo = []
    cursor = 0.0
    for i, (mode, dur, speed) in enumerate([
            ("CUT", 4.2, 1.0), ("IMAGE", 3.1, 1.0), ("SLOW", 5.0, 0.82),
            ("CUT", 2.8, 1.0), ("SPEEDUP", 3.6, 1.35), ("IMAGE", 4.4, 1.0),
            ("CUT", 3.3, 1.0), ("SLOW", 2.9, 0.77)], start=1):
        demo.append(ScenePlan(i, _P(f"{i}.mp3"), dur, mode, _P(f"{i}.mp4"),
                              video_duration=dur * speed, speed=speed,
                              start=cursor, gap=0.4))
        cursor += dur + 0.4
    pages.fill_scene_table(app, demo, ["0009: thiếu cả video lẫn ảnh",
                                       "0010: video lỗi và không có ảnh fallback"])
    pages.update_plan_stats(app, demo, ["x", "y"])
    for key, value in (("audio", 42), ("visual", 40), ("bgm", 3)):
        app.tiles[key].set(value)

    # hàng đợi render giả
    app.render_queue.extend([
        {"name": "tap-01", "values": {}, "status": "done", "percent": 100.0,
         "eta": 0.0, "duration": 754.0, "out": "D:/Videos/_render/tap-01.mp4"},
        {"name": "tap-02", "values": {}, "status": "running", "percent": 38.0,
         "eta": 412.0, "duration": 690.0, "out": ""},
        {"name": "tap-03", "values": {}, "status": "pending", "percent": 0.0,
         "eta": 0.0, "duration": 0.0, "out": ""},
        {"name": "tap-04", "values": {}, "status": "error", "percent": 0.0,
         "eta": 0.0, "duration": 0.0, "out": "thiếu folder Audio"},
    ])
    pages.refresh_queue(app)
    pages.update_render_progress(app, "tap-02", 38.0, 412.0)

    failures: list[str] = []
    for theme in ("dark", "light"):
        app.theme.apply(theme)
        app.show(app.current)
        for key, label in NAV:
            try:
                app.show(key)
                if key == "settings":
                    for sub, sublabel in pages.SETTING_TABS:
                        pages.show_setting_tab(app, sub)
                        shot(root, out / f"{theme}-settings-{sub}.png")
                    continue
                shot(root, out / f"{theme}-{key}.png")
            except Exception as e:  # noqa: BLE001
                failures.append(f"{theme}/{key}: {e}")

    root.destroy()
    if failures:
        print("[FAIL] " + "; ".join(failures))
        return 1
    files = sorted(out.glob("*.png"))
    print(f"[OK] Dựng được toàn bộ {len(NAV)} trang ở 2 theme, {len(files)} ảnh.")
    for f in files:
        print("   ", f.name, f.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
