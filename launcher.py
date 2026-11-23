"""Điểm vào khi đóng gói .exe.

Bọc thêm bẫy lỗi để nếu app crash lúc khởi động, người dùng vẫn thấy thông báo
thay vì cửa sổ đóng im lặng (bản .exe chạy ở chế độ windowed, không có console).
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _crash_log_candidates() -> list[Path]:
    """Nơi ghi crash.log, ưu tiên chỗ chắc chắn ghi được.

    Thư mục cài đặt (vd C:\\Program Files) thường CHỈ ĐỌC nên phải có phương án
    dự phòng, nếu không người dùng chẳng có gì để gửi đi khi báo lỗi.
    """
    import os
    import tempfile
    out = [Path(sys.executable).resolve().parent]
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            out.append(Path(base) / "CapCutDraftStudio")
    elif sys.platform == "darwin":
        out.append(Path.home() / "Library" / "Application Support" / "CapCutDraftStudio")
    else:
        out.append(Path.home() / ".local" / "share" / "CapCutDraftStudio")
    out.append(Path(tempfile.gettempdir()) / "CapCutDraftStudio")
    return [p / "crash.log" for p in out]


def _report(exc_text: str) -> None:
    log = None
    for candidate in _crash_log_candidates():
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text(exc_text, encoding="utf-8")
            log = candidate
            break
        except OSError:
            continue
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


def _cli(argv: list[str]) -> int:
    """`CapCut Draft Studio.exe --cli build --input …` — chạy không giao diện.

    Bản .exe không có cửa sổ console nên mọi dòng in ra được ghi kèm vào
    cli-last.log (cùng chỗ với crash.log) để xem lại."""
    import io

    class Tee(io.TextIOBase):
        def __init__(self, *streams):
            self.streams = [s for s in streams if s is not None]

        def write(self, text):
            for st in self.streams:
                try:
                    st.write(text)
                    st.flush()
                except Exception:  # noqa: BLE001
                    pass
            return len(text)

    logf = None
    for candidate in _crash_log_candidates():
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            logf = (candidate.parent / "cli-last.log").open("w", encoding="utf-8")
            break
        except OSError:
            continue
    sys.stdout = Tee(sys.__stdout__, logf)
    sys.stderr = Tee(sys.__stderr__, logf)
    try:
        from capcut_draft_studio.cli import main as cli_main
        return cli_main(argv)
    except SystemExit as e:
        return int(e.code or 0) if not isinstance(e.code, str) else (print(e.code) or 2)
    except Exception:  # noqa: BLE001
        print(traceback.format_exc())
        return 1
    finally:
        if logf:
            logf.close()


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        return _cli(sys.argv[2:])
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
