"""Điểm vào khi đóng gói .exe.

Bọc thêm bẫy lỗi để nếu app crash lúc khởi động, người dùng vẫn thấy thông báo
thay vì cửa sổ đóng im lặng (bản .exe chạy ở chế độ windowed, không có console).
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _report(exc_text: str) -> None:
    try:
        log = Path(sys.executable).resolve().parent / "crash.log"
        log.write_text(exc_text, encoding="utf-8")
    except OSError:
        log = None
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror(
            "CapCut Draft Studio — lỗi khởi động",
            (exc_text[-1500:] + (f"\n\nĐã ghi chi tiết vào:\n{log}" if log else "")))
        r.destroy()
    except Exception:  # noqa: BLE001
        sys.stderr.write(exc_text)


def main() -> int:
    try:
        from capcut_draft_studio.ui.app import main as run
    except Exception:  # noqa: BLE001
        _report("Không nạp được ứng dụng:\n\n" + traceback.format_exc())
        return 1
    try:
        run()
    except Exception:  # noqa: BLE001
        _report("Ứng dụng dừng bất thường:\n\n" + traceback.format_exc())
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
