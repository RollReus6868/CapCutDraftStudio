"""Xuất video bằng chính CapCut — tự mở CapCut và bấm Export hộ (Windows).

Vì sao phải tự viết thay vì dùng thẳng `pycapcut.jianying_controller`
------------------------------------------------------------------
Bộ điều khiển của pycapcut nhận diện cửa sổ bằng cách so tiêu đề đúng bằng
chuỗi tiếng Trung `"CapCut专业版"`. Bản CapCut quốc tế mà người Việt dùng có
tiêu đề là `"CapCut"`, nên nó **không bao giờ tìm thấy cửa sổ** và dừng ngay ở
bước đầu — đúng hiện tượng "tool không tự mở CapCut và không tự render".
Nó cũng tìm cửa sổ xuất bằng tên `"导出"`, và vòng chờ xuất xong của nó có thể
quay vô hạn mà không bao giờ hết giờ.

Bản này nhận diện cửa sổ theo **tên lớp cửa sổ + tên tiến trình** nên không phụ
thuộc ngôn ngữ, tự tìm và mở CapCut, có thời gian chờ thật ở mọi bước, và ghi
nhật ký từng bước để khi hỏng còn biết hỏng ở đâu.

Các chuỗi như `HomePageDraftTitle`, `MainWindowTitleBarExportBtn`, `ExportPath`,
`ExportOkBtn`, `ExportSucceedCloseBtn` là tên nội bộ của control trong CapCut,
giống nhau ở mọi ngôn ngữ nên dùng được.

Giới hạn: chỉ chạy trên Windows, cần gói `uiautomation`, và CapCut phải cho
xuất (không dùng chức năng VIP). Trong lúc chạy KHÔNG được đụng chuột/bàn phím.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .models import LogFn

#: tên tiến trình được coi là CapCut
PROCESS_NAMES = {"capcut.exe", "capcutpro.exe", "jianyingpro.exe"}

#: cửa sổ chính của CapCut có tên lớp chứa một trong các chuỗi này
HOME_CLASS = "homepage"
EDIT_CLASS = "mainwindow"

RES_MAP = {"2160": "RES_4K", "1440": "RES_2K", "1080": "RES_1080P",
           "720": "RES_720P", "480": "RES_480P"}
FPS_MAP = {24: "FR_24", 25: "FR_25", 30: "FR_30", 50: "FR_50", 60: "FR_60"}


class CapCutExportError(RuntimeError):
    """Lỗi cần hiện nguyên văn cho người dùng."""


# --------------------------------------------------------------------------- #
# nạp uiautomation
# --------------------------------------------------------------------------- #


def _load_uia():
    """Nạp uiautomation, vá sẵn cái bẫy comtypes khi chạy từ bản đóng gói."""
    if getattr(sys, "frozen", False):
        try:
            import comtypes.client
            # comtypes muốn sinh code vào thư mục gen bên trong gói (chỉ đọc)
            comtypes.client.gen_dir = None
        except Exception:
            pass
    import uiautomation as uia
    return uia


def available() -> tuple[bool, str]:
    """(dùng được không, lý do nếu không)."""
    if os.name != "nt":
        return False, ("Xuất qua CapCut chỉ chạy trên Windows. Trên macOS hãy dùng "
                       "engine ffmpeg, hoặc mở CapCut và bấm Export thủ công.")
    try:
        _load_uia()
    except Exception as e:
        return False, ("Thiếu thư viện uiautomation nên tool không điều khiển được "
                       f"CapCut.\n\nChi tiết: {e}\n\n"
                       "Cách sửa: mở Command Prompt và chạy\n"
                       "    pip install uiautomation\n"
                       "rồi mở lại tool. Bản cài đặt chính thức đã kèm sẵn thư viện này.")
    return True, ""


# --------------------------------------------------------------------------- #
# tìm / mở / tắt CapCut
# --------------------------------------------------------------------------- #


def _no_window() -> dict:
    return {"creationflags": 0x08000000} if os.name == "nt" else {}


def find_capcut_exe() -> Path | None:
    """Tìm CapCut.exe: các vị trí cài phổ biến trước, rồi tới registry."""
    candidates: list[Path] = []
    for env in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "APPDATA"):
        base = os.environ.get(env)
        if not base:
            continue
        for sub in (("CapCut", "CapCut.exe"),
                    ("Programs", "CapCut", "CapCut.exe"),
                    ("CapCut", "Apps", "CapCut.exe"),
                    ("JianyingPro", "JianyingPro.exe")):
            candidates.append(Path(base).joinpath(*sub))
    for p in candidates:
        try:
            if p.is_file():
                return p
        except OSError:
            continue
    return _find_in_registry()


def _find_in_registry() -> Path | None:
    if os.name != "nt":
        return None
    try:
        import winreg
    except ImportError:
        return None
    roots = [(winreg.HKEY_LOCAL_MACHINE,
              r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_CURRENT_USER,
              r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")]
    for hive, path in roots:
        try:
            key = winreg.OpenKey(hive, path)
        except OSError:
            continue
        try:
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    sub = winreg.OpenKey(key, winreg.EnumKey(key, i))
                    name = str(winreg.QueryValueEx(sub, "DisplayName")[0])
                    if "capcut" not in name.lower() and "jianying" not in name.lower():
                        continue
                    for value in ("DisplayIcon", "InstallLocation"):
                        try:
                            raw = str(winreg.QueryValueEx(sub, value)[0]).strip('" ')
                        except OSError:
                            continue
                        p = Path(raw.split(",")[0])
                        if p.is_file() and p.suffix.lower() == ".exe":
                            return p
                        if p.is_dir():
                            for exe in ("CapCut.exe", "JianyingPro.exe"):
                                if (p / exe).is_file():
                                    return p / exe
                except OSError:
                    continue
        finally:
            key.Close()
    return None


def _process_name(pid: int) -> str:
    """Tên file exe của một tiến trình — để chắc chắn đúng cửa sổ CapCut."""
    if os.name != "nt" or not pid:
        return ""
    import ctypes
    from ctypes import wintypes
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(
                handle, 0, buf, ctypes.byref(size)):
            return Path(buf.value).name
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)
    return ""


def running_pids() -> list[int]:
    if os.name != "nt":
        return []
    try:
        cp = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True,
                            text=True, timeout=15, **_no_window())
    except Exception:
        return []
    pids = []
    for line in (cp.stdout or "").splitlines():
        parts = [p.strip('" ') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() in PROCESS_NAMES:
            try:
                pids.append(int(parts[1]))
            except ValueError:
                pass
    return pids


def close_capcut(log: LogFn = print, timeout: float = 25) -> bool:
    """Đóng CapCut (nhẹ trước, ép sau). True nếu đã tắt hẳn."""
    pids = running_pids()
    if not pids:
        return True
    log(f"[EXPORT] CapCut đang mở ({len(pids)} tiến trình) → đóng lại để nạp draft mới…")
    for force in (False, True):
        args = ["taskkill", "/IM", "CapCut.exe", "/IM", "JianyingPro.exe"]
        if force:
            args.append("/F")
        try:
            subprocess.run(args, capture_output=True, text=True, timeout=20, **_no_window())
        except Exception:
            pass
        deadline = time.time() + (timeout / 2)
        while time.time() < deadline:
            if not running_pids():
                log("[EXPORT] Đã đóng CapCut.")
                return True
            time.sleep(0.6)
    return not running_pids()


def launch_capcut(exe: Path, log: LogFn = print) -> None:
    log(f"[EXPORT] Mở CapCut: {exe}")
    try:
        subprocess.Popen([str(exe)], cwd=str(exe.parent), **_no_window())
    except OSError as e:
        raise CapCutExportError(f"Không mở được CapCut:\n{exe}\n\nChi tiết: {e}") from e


# --------------------------------------------------------------------------- #
# tìm cửa sổ (không phụ thuộc ngôn ngữ)
# --------------------------------------------------------------------------- #


def _window_state(control) -> str:
    """'home' | 'edit' | '' — dựa vào tên lớp cửa sổ, không dựa vào tiêu đề."""
    cls = (getattr(control, "ClassName", "") or "").lower()
    if HOME_CLASS in cls:
        return "home"
    if EDIT_CLASS in cls:
        return "edit"
    return ""


def _is_capcut_window(control) -> bool:
    if not _window_state(control):
        return False
    exe = _process_name(getattr(control, "ProcessId", 0)).lower()
    # không đọc được tên tiến trình thì vẫn chấp nhận, miễn là đúng tên lớp
    return (exe in PROCESS_NAMES) if exe else True


def find_window(uia, timeout: float = 0.0):
    """Trả về (control, 'home'|'edit') hoặc (None, '')."""
    deadline = time.time() + max(0.0, timeout)
    while True:
        for win in uia.GetRootControl().GetChildren():
            try:
                if _is_capcut_window(win):
                    return win, _window_state(win)
            except Exception:
                continue
        if time.time() >= deadline:
            return None, ""
        time.sleep(1.0)


def diagnose() -> str:
    """Liệt kê cửa sổ đang mở — gửi kết quả này đi khi tự động hoá không chạy."""
    lines = [f"Hệ điều hành: {sys.platform} / os.name={os.name}"]
    exe = find_capcut_exe()
    lines.append(f"CapCut.exe: {exe or 'KHÔNG TÌM THẤY'}")
    lines.append(f"Tiến trình CapCut đang chạy: {running_pids() or 'không có'}")
    ok, why = available()
    lines.append(f"uiautomation: {'có' if ok else 'KHÔNG — ' + why.splitlines()[0]}")
    if not ok:
        return "\n".join(lines)
    try:
        uia = _load_uia()
        lines.append("")
        lines.append("Cửa sổ cấp cao nhất đang mở:")
        for win in uia.GetRootControl().GetChildren():
            try:
                name = (win.Name or "").strip()
                cls = win.ClassName or ""
                pid = getattr(win, "ProcessId", 0)
                proc = _process_name(pid)
                if not name and not cls:
                    continue
                mark = "  <-- CapCut" if _is_capcut_window(win) else ""
                lines.append(f"  [{proc or '?'}] name={name!r} class={cls!r}{mark}")
            except Exception:
                continue
    except Exception as e:
        lines.append(f"Không liệt kê được cửa sổ: {e}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# xuất video
# --------------------------------------------------------------------------- #


def _desc(control_finder, text: str, depth: int = 2, exact: bool = False):
    return control_finder.desc_matcher(text, depth=depth, exact=exact)


def _wait(fn, timeout: float, step: float = 0.7, cancel=None):
    """Chờ `fn()` trả về giá trị đúng; None nếu hết giờ."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cancel and cancel():
            raise CapCutExportError("Đã dừng theo yêu cầu.")
        try:
            value = fn()
        except Exception:
            value = None
        if value:
            return value
        time.sleep(step)
    return None


def export(draft_name: str, out_path: Path, *, res: str = "", fps: int = 0,
           timeout: float = 3600, log: LogFn = print, cancel=None,
           restart_capcut: bool = True) -> Path:
    """Bảo CapCut mở draft `draft_name` và xuất ra `out_path`."""
    ok, why = available()
    if not ok:
        raise CapCutExportError(why)
    uia = _load_uia()
    from pycapcut.jianying_controller import ControlFinder

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    exe = find_capcut_exe()
    if exe is None and not running_pids():
        raise CapCutExportError(
            "Không tìm thấy CapCut trên máy.\n\n"
            "Hãy mở CapCut lên một lần rồi bấm lại, hoặc dùng engine ffmpeg "
            "(không cần CapCut).")

    # 1) CapCut phải được mở LẠI thì danh sách project mới có draft vừa tạo
    if restart_capcut:
        close_capcut(log)
    if not running_pids():
        if exe is None:
            raise CapCutExportError("Không tìm thấy file CapCut.exe để mở.")
        launch_capcut(exe, log)

    log("[EXPORT] Chờ cửa sổ CapCut… (đừng dùng chuột/bàn phím tới khi xong)")
    window, state = find_window(uia, timeout=90)
    if window is None:
        raise CapCutExportError(
            "Mở CapCut rồi nhưng không thấy cửa sổ sau 90 giây.\n\n"
            "Bấm nút “Chẩn đoán CapCut” ở trang Render rồi gửi kết quả đi để "
            "sửa đúng chỗ.")
    window.SetActive()
    window.SetTopmost(True)
    started = time.time()

    try:
        # 2) tìm draft trong danh sách
        log(f"[EXPORT] Tìm project '{draft_name}' trong danh sách CapCut…")
        title = _wait(lambda: _exists(window.TextControl(
            searchDepth=2,
            Compare=_desc(ControlFinder, f"HomePageDraftTitle:{draft_name}", exact=True))),
            timeout=60, cancel=cancel)
        if title is None:
            raise CapCutExportError(
                f"Không thấy project '{draft_name}' trong danh sách của CapCut.\n\n"
                "Thường là do CapCut chưa nạp lại danh sách. Hãy đóng hẳn CapCut "
                "rồi bấm render lại, hoặc kiểm tra tên project có đúng không.")
        parent = title.GetParentControl()
        (parent or title).Click(simulateMove=False)

        # 3) chờ vào màn hình dựng rồi bấm Export
        log("[EXPORT] Đã mở project, chờ CapCut nạp timeline…")
        edit = _wait(lambda: _state_is(uia, "edit"), timeout=120, cancel=cancel)
        if edit is None:
            raise CapCutExportError("CapCut không mở được màn hình dựng sau 2 phút.")
        edit.SetActive()
        btn = _wait(lambda: _exists(edit.TextControl(
            searchDepth=2, Compare=_desc(ControlFinder, "MainWindowTitleBarExportBtn"))),
            timeout=60, cancel=cancel)
        if btn is None:
            raise CapCutExportError(
                "Không tìm thấy nút Export trên thanh tiêu đề của CapCut.\n\n"
                "Có thể bản CapCut này đã đổi giao diện. Bấm “Chẩn đoán CapCut” "
                "và gửi kết quả đi.")
        log("[EXPORT] Bấm Export…")
        btn.Click(simulateMove=False)

        # 4) cửa sổ xuất — tìm theo control bên trong, không theo tên cửa sổ
        panel = _wait(lambda: _export_panel(uia, ControlFinder), timeout=90, cancel=cancel)
        if panel is None:
            raise CapCutExportError("Không thấy cửa sổ xuất video của CapCut sau 90 giây.")
        panel.SetActive()
        export_path = _read_export_path(panel, ControlFinder)
        if export_path:
            log(f"[EXPORT] CapCut sẽ ghi tạm ra: {export_path}")

        _apply_choice(panel, ControlFinder, "ExportSharpnessInput", RES_MAP.get(res), log)
        _apply_choice(panel, ControlFinder, "FrameRateInput", FPS_MAP.get(int(fps or 0)), log)

        ok_btn = _wait(lambda: _exists(panel.TextControl(
            searchDepth=2, Compare=_desc(ControlFinder, "ExportOkBtn", exact=True))),
            timeout=30, cancel=cancel)
        if ok_btn is None:
            raise CapCutExportError("Không tìm thấy nút xác nhận xuất trong cửa sổ xuất.")
        ok_btn.Click(simulateMove=False)
        log("[EXPORT] CapCut đang render… có thể mất khá lâu, cứ để yên máy.")

        # 5) chờ xuất xong — CÓ hạn giờ thật
        deadline = time.time() + timeout
        close_btn = None
        while time.time() < deadline:
            if cancel and cancel():
                raise CapCutExportError("Đã dừng theo yêu cầu.")
            panel_now = _export_panel(uia, ControlFinder) or panel
            close_btn = _exists(panel_now.TextControl(
                searchDepth=2, Compare=_desc(ControlFinder, "ExportSucceedCloseBtn")))
            if close_btn:
                break
            time.sleep(1.5)
        if not close_btn:
            raise CapCutExportError(
                f"CapCut xuất quá {int(timeout / 60)} phút mà chưa xong nên tool dừng chờ.\n\n"
                "Video có thể vẫn đang được CapCut xuất — kiểm tra trong CapCut.")
        close_btn.Click(simulateMove=False)
        log(f"[EXPORT] CapCut báo xuất xong sau {int(time.time() - started)} giây.")

        # 6) chuyển file về đúng chỗ
        if export_path and Path(export_path).is_file():
            if Path(export_path) != out_path:
                shutil.move(str(export_path), str(out_path))
        if not out_path.is_file():
            raise CapCutExportError(
                f"CapCut báo xong nhưng không thấy file:\n{out_path}\n\n"
                f"Có thể CapCut đã lưu vào thư mục mặc định của nó"
                + (f":\n{export_path}" if export_path else "."))
        log(f"[SUCCESS] Đã xuất qua CapCut: {out_path}")
        return out_path
    finally:
        try:
            window.SetTopmost(False)
        except Exception:
            pass


def _exists(control):
    try:
        return control if control.Exists(0) else None
    except Exception:
        return None


def _state_is(uia, want: str):
    win, state = find_window(uia, timeout=0)
    return win if (win is not None and state == want) else None


def _export_panel(uia, control_finder):
    """Cửa sổ xuất: nhận ra bằng ô đường dẫn bên trong, không bằng tên cửa sổ."""
    win, _ = find_window(uia, timeout=0)
    if win is None:
        return None
    for child in list(win.GetChildren()) + [win]:
        try:
            probe = child.TextControl(
                searchDepth=2, Compare=_desc(control_finder, "ExportPath"))
            if probe.Exists(0):
                return child
        except Exception:
            continue
    return None


def _read_export_path(panel, control_finder) -> str:
    try:
        anchor = panel.TextControl(searchDepth=2,
                                   Compare=_desc(control_finder, "ExportPath"))
        if not anchor.Exists(0):
            return ""
        sibling = anchor.GetSiblingControl(lambda ctrl: True)
        return sibling.GetPropertyValue(30159) if sibling else ""
    except Exception:
        return ""


def _apply_choice(panel, control_finder, field: str, value: str | None,
                  log: LogFn = print) -> None:
    """Đổi độ phân giải / fps trong cửa sổ xuất. Không đổi được thì bỏ qua."""
    if not value:
        return
    try:
        from pycapcut.jianying_controller import ExportFramerate, ExportResolution
        wanted = getattr(ExportResolution, value, None) or getattr(ExportFramerate, value, None)
        label = wanted.value if wanted else value
        opener = panel.TextControl(searchDepth=2, Compare=_desc(control_finder, field))
        if not opener.Exists(0.5):
            log(f"[WARN] Không thấy ô {field} trong cửa sổ xuất — giữ nguyên cài đặt CapCut.")
            return
        opener.Click(simulateMove=False)
        time.sleep(0.6)
        item = panel.TextControl(searchDepth=2, Compare=_desc(control_finder, label))
        if not item.Exists(0.8):
            log(f"[WARN] Không thấy lựa chọn '{label}' — giữ nguyên cài đặt CapCut.")
            return
        item.Click(simulateMove=False)
        time.sleep(0.4)
    except Exception as e:
        log(f"[WARN] Không đổi được {field}: {e}")
