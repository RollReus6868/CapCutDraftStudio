"""Xuất video bằng chính CapCut (điều khiển giao diện CapCut trên Windows).

Cách này cho ra file GIỐNG HỆT khi bạn tự bấm Export trong CapCut, nhưng đổi lại:

* chỉ chạy trên Windows (dựa vào UI Automation của Windows);
* CapCut phải đang mở ở màn hình danh sách project;
* không được đụng chuột/bàn phím trong lúc chạy;
* CapCut chỉ cho tự động hoá tốt ở bản 6 trở xuống — bản mới hơn có thể đổi
  giao diện và làm hỏng thao tác tự động;
* tài khoản phải có quyền export (không dùng chức năng VIP hoặc đã mua VIP).

Vì vậy engine mặc định của tool vẫn là ffmpeg (`render.py`), phần này chỉ dùng
khi bạn cần bản xuất đúng y CapCut.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from .models import LogFn

RES_MAP = {"2160": "RES_4K", "1440": "RES_2K", "1080": "RES_1080P",
           "720": "RES_720P", "480": "RES_480P"}
FPS_MAP = {24: "FR_24", 25: "FR_25", 30: "FR_30", 50: "FR_50", 60: "FR_60"}


class CapCutExportError(RuntimeError):
    """Lỗi cần hiện nguyên văn cho người dùng."""


def available() -> tuple[bool, str]:
    """(dùng được không, lý do nếu không)."""
    if os.name != "nt":
        return False, ("Xuất qua CapCut chỉ chạy trên Windows. Trên macOS hãy dùng "
                       "engine ffmpeg, hoặc mở CapCut và bấm Export thủ công.")
    try:
        import uiautomation  # noqa: F401
    except Exception:
        return False, ("Thiếu thư viện uiautomation. Chạy lệnh:\n"
                       "    pip install uiautomation\n"
                       "rồi mở lại tool. Bản cài đặt chính thức đã kèm sẵn thư viện này.")
    try:
        import pycapcut.jianying_controller  # noqa: F401
    except Exception as e:
        return False, f"Không nạp được bộ điều khiển CapCut của pycapcut: {e}"
    return True, ""


def export(draft_name: str, out_path: Path, *, res: str = "", fps: int = 0,
           timeout: float = 3600, log: LogFn = print) -> Path:
    """Bảo CapCut export draft `draft_name` ra `out_path`."""
    ok, why = available()
    if not ok:
        raise CapCutExportError(why)
    from pycapcut import jianying_controller as jc

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    resolution = getattr(jc.ExportResolution, RES_MAP[res], None) if res in RES_MAP else None
    framerate = getattr(jc.ExportFramerate, FPS_MAP[int(fps)], None) if int(fps or 0) in FPS_MAP else None

    log("[EXPORT] Đang tìm cửa sổ CapCut… (đừng dùng chuột/bàn phím tới khi xong)")
    started = time.time()
    try:
        controller = jc.JianyingController()
    except Exception as e:
        raise CapCutExportError(
            "Không tìm thấy cửa sổ CapCut.\n\n"
            "Hãy mở CapCut, quay về màn hình danh sách project rồi bấm lại.\n\n"
            f"Chi tiết: {e}") from e
    try:
        controller.export_draft(draft_name, str(out_path), resolution=resolution,
                                framerate=framerate, timeout=timeout)
    except Exception as e:
        raise CapCutExportError(
            f"CapCut không export được draft '{draft_name}'.\n\n"
            "Thường gặp nhất: CapCut bản mới đổi giao diện, draft chưa xuất hiện trong "
            "danh sách, hoặc project có chức năng cần VIP.\n\n"
            f"Chi tiết: {e}") from e
    if not out_path.is_file():
        raise CapCutExportError(
            f"CapCut báo xong nhưng không thấy file:\n{out_path}\n\n"
            "Có thể CapCut đã lưu vào thư mục mặc định của nó.")
    log(f"[SUCCESS] CapCut đã xuất xong sau {int(time.time() - started)}s: {out_path}")
    return out_path
