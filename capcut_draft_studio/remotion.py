"""0.7.0 — đồ họa chữ chuyển động bằng Remotion (React → video).

Tool là Python; Remotion chạy bằng Node.js. Phần Node (assets/remotion-engine) được
chép vào thư mục DỮ LIỆU của tool (không bao giờ vào thư mục cài — chỉ đọc) rồi
`npm ci` một lần khi người dùng bấm "Cài Remotion". Sau đó mỗi lần dựng / render,
các đồ họa loại TERM, TIMELINE được vẽ thành clip ProRes 4444 có kênh alpha (CapCut
nhận nền trong suốt của định dạng này — người dùng đã thử 27/11/2026) và đặt lên
track chữ thay cho ảnh PNG.

Mọi lỗi (chưa cài Node, chưa cài Remotion, một clip vẽ hỏng…) KHÔNG làm hỏng việc
dựng: mục đó tự quay về bản vẽ Pillow như 0.6.4 và nhật ký ghi [WARN].

Clip được nhớ (cache) theo nội dung trong `<VIDEO>/_capcut_draft_studio/remotion/`,
dựng lại project không phải vẽ lại clip không đổi.

Giấy phép Remotion: miễn phí cho cá nhân và công ty tới 3 người (kể cả kiếm tiền);
từ 4 người trở lên cần Company License — https://www.remotion.dev/license
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

LogFn = Callable[[str], None]

#: loại đồ họa vẽ bằng Remotion khi bật
KINDS = ("TERM", "TIMELINE")
COMPOSITION = {"TERM": "Term", "TIMELINE": "Timeline"}
ENGINE_NAME = "remotion-engine"
STATE_FILE = "cds-state.json"
CACHE_DIR = "remotion"
#: không thấy tiến độ trong ngần này giây → coi như treo, dừng tiến trình Node
STALL_SEC = 240
#: clip trong cache lâu không dùng tới thì dọn
CACHE_KEEP_DAYS = 21
#: phông của tool chép vào engine (cùng phông với bản Pillow)
FONT_FILES = ("EBGaramond-SemiBold.ttf", "EBGaramond-Italic.ttf", "Montserrat-Bold.ttf",
              "Montserrat-ExtraBold.ttf", "NotoSerifHebrew.ttf")
NODE_MIN_MAJOR = 18
LICENSE_NOTE = ("Remotion miễn phí cho cá nhân và nhóm tới 3 người (kể cả kiếm tiền); "
                "từ 4 người trở lên cần mua Company License — remotion.dev/license")


def _no_window() -> dict:
    if os.name == "nt":
        return {"creationflags": 0x08000000}   # CREATE_NO_WINDOW
    return {}


# --------------------------------------------------------------------------- #
# vị trí
# --------------------------------------------------------------------------- #
def assets_dirs() -> list[Path]:
    here = Path(__file__).resolve().parent.parent
    dirs = [here / "assets"]
    base = getattr(sys, "_MEIPASS", None)
    if base:
        dirs.insert(0, Path(base) / "assets")
    if getattr(sys, "frozen", False):
        dirs.append(Path(sys.executable).resolve().parent / "assets")
        dirs.append(Path(sys.executable).resolve().parent / "_internal" / "assets")
    return dirs


def source_dir() -> Path | None:
    """assets/remotion-engine đi kèm tool (chỉ đọc)."""
    for d in assets_dirs():
        p = d / ENGINE_NAME
        if (p / "render.mjs").is_file() and (p / "package.json").is_file():
            return p
    return None


def fonts_dir() -> Path | None:
    for d in assets_dirs():
        p = d / "overlay-fonts"
        if p.is_dir():
            return p
    return None


def home(base: Path | None = None) -> Path:
    """Thư mục engine đã cài (trong thư mục DỮ LIỆU của tool, luôn ghi được)."""
    env = os.environ.get("CDS_REMOTION_HOME")
    if env:
        return Path(env)
    if base is None:
        try:
            from .ui.app import DATA_DIR
            base = Path(DATA_DIR)
        except Exception:
            base = Path(tempfile.gettempdir()) / "CapCutDraftStudio"
    return Path(base) / ENGINE_NAME


def _tree_hash(root: Path, rels: Iterable[str]) -> str:
    h = hashlib.sha1()
    for rel in rels:
        p = root / rel
        files = sorted(p.rglob("*")) if p.is_dir() else [p]
        for f in files:
            if f.is_file():
                h.update(f.relative_to(root).as_posix().encode("utf-8"))
                h.update(f.read_bytes())
    return h.hexdigest()[:16]


SRC_PARTS = ("render.mjs", "src", "public")


def source_hash(src: Path | None = None) -> str:
    """Đổi khi mã vẽ / phông của engine đổi → clip cũ trong cache hết hiệu lực."""
    src = src or source_dir()
    if not src:
        return "none"
    fd = fonts_dir()
    h = _tree_hash(src, SRC_PARTS)
    if fd:
        h2 = hashlib.sha1(h.encode())
        for n in FONT_FILES:
            f = fd / n
            if f.is_file():
                h2.update(n.encode())
                h2.update(str(f.stat().st_size).encode())
        h = h2.hexdigest()[:16]
    return h


def lock_hash(src: Path | None = None) -> str:
    src = src or source_dir()
    if not src:
        return "none"
    return _tree_hash(src, ("package.json", "package-lock.json"))


# --------------------------------------------------------------------------- #
# Node.js và trình duyệt
# --------------------------------------------------------------------------- #
def _candidates_node() -> list[str]:
    out: list[str] = []
    w = shutil.which("node")
    if w:
        out.append(w)
    if os.name == "nt":
        for env, sub in (("ProgramFiles", r"nodejs\node.exe"), ("ProgramFiles(x86)", r"nodejs\node.exe"),
                         ("LOCALAPPDATA", r"Programs\nodejs\node.exe"), ("NVM_SYMLINK", "node.exe"),
                         ("APPDATA", r"nvm\current\node.exe")):
            root = os.environ.get(env)
            if root:
                out.append(str(Path(root) / sub))
    else:
        out += ["/usr/local/bin/node", "/opt/homebrew/bin/node", "/usr/bin/node"]
        nvm = Path.home() / ".nvm" / "versions" / "node"
        if nvm.is_dir():
            out += [str(p / "bin" / "node") for p in sorted(nvm.iterdir(), reverse=True)]
    seen, res = set(), []
    for c in out:
        if c and c not in seen and Path(c).is_file():
            seen.add(c)
            res.append(c)
    return res


def node_version(node: str) -> tuple[int, str] | None:
    try:
        cp = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=20,
                            **_no_window())
        v = (cp.stdout or "").strip()
        major = int(v.lstrip("v").split(".")[0])
        return major, v
    except Exception:
        return None


def find_node() -> tuple[str, str] | None:
    """(đường dẫn node, phiên bản) đủ mới, hoặc None."""
    for c in _candidates_node():
        v = node_version(c)
        if v and v[0] >= NODE_MIN_MAJOR:
            return c, v[1]
    return None


def npm_command(node: str) -> list[str] | None:
    """Chạy npm qua chính node (tránh npm.cmd trên Windows)."""
    nd = Path(node).resolve().parent
    for p in (nd / "node_modules" / "npm" / "bin" / "npm-cli.js",
              nd.parent / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js",
              nd.parent / "libexec" / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js"):
        if p.is_file():
            return [node, str(p)]
    w = shutil.which("npm")
    return [w] if w else None


def system_browsers() -> list[str]:
    """Chrome / Edge có sẵn trên máy — dự phòng khi không tải được Chrome Headless Shell."""
    c: list[str] = []
    if os.name == "nt":
        for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            root = os.environ.get(env)
            if root:
                c += [str(Path(root) / r"Google\Chrome\Application\chrome.exe"),
                      str(Path(root) / r"Microsoft\Edge\Application\msedge.exe")]
    elif sys.platform == "darwin":
        c += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    else:
        for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                  "microsoft-edge"):
            w = shutil.which(n)
            if w:
                c.append(w)
    seen, out = set(), []
    for p in c:
        if p not in seen and Path(p).is_file():
            seen.add(p)
            out.append(p)
    return out


# --------------------------------------------------------------------------- #
# trạng thái
# --------------------------------------------------------------------------- #
@dataclass
class Status:
    node: str | None = None
    node_version: str = ""
    installed: bool = False        # node_modules có Remotion đúng phiên bản lock
    browser: str | None = None     # trình duyệt đã chọn lúc cài
    browser_kind: str = ""
    home: Path | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return bool(self.node and self.installed and not self.problems)

    def text(self) -> str:
        if self.ready:
            b = {"headless-shell": "Chrome Headless Shell", "system": "trình duyệt có sẵn trên máy",
                 "chosen": "trình duyệt đã chọn"}.get(self.browser_kind, "trình duyệt")
            return f"Sẵn sàng — Node {self.node_version}, {b}"
        return " · ".join(self.problems) or "Chưa cài"


def _read_state(h: Path) -> dict:
    try:
        return json.loads((h / STATE_FILE).read_text(encoding="utf-8"))
    except Exception:
        return {}


def status(base: Path | None = None) -> Status:
    st = Status(home=home(base))
    src = source_dir()
    if not src:
        st.problems.append("Bản tool này thiếu thư mục assets/remotion-engine")
        return st
    n = find_node()
    if n:
        st.node, st.node_version = n
    else:
        st.problems.append(f"Chưa có Node.js {NODE_MIN_MAJOR}+ (tải bản LTS ở nodejs.org rồi cài)")
    state = _read_state(st.home)
    has_mods = (st.home / "node_modules" / "remotion" / "package.json").is_file() and \
        (st.home / "node_modules" / "@remotion" / "renderer").is_dir()
    st.installed = bool(has_mods and state.get("lock") == lock_hash(src))
    st.browser = state.get("browser")
    st.browser_kind = state.get("browser_kind", "")
    if not st.installed:
        st.problems.append("Chưa cài Remotion (bấm 'Cài Remotion')" if not has_mods
                           else "Bản Remotion cũ — bấm 'Cài Remotion' để cập nhật")
    return st


# --------------------------------------------------------------------------- #
# cài đặt
# --------------------------------------------------------------------------- #
def sync_source(h: Path, src: Path | None = None) -> bool:
    """Chép mã vẽ + phông của engine sang thư mục cài khi khác (không đụng node_modules).
    Trả về True khi có chép."""
    src = src or source_dir()
    if not src:
        return False
    want = source_hash(src)
    state = _read_state(h)
    if state.get("src") == want and (h / "render.mjs").is_file():
        return False
    h.mkdir(parents=True, exist_ok=True)
    for rel in ("render.mjs", "package.json", "package-lock.json"):
        shutil.copy2(src / rel, h / rel)
    for rel in ("src", "public"):
        if (h / rel).exists():
            shutil.rmtree(h / rel, ignore_errors=True)
        shutil.copytree(src / rel, h / rel)
    fd = fonts_dir()
    if fd:
        for n in FONT_FILES:
            if (fd / n).is_file():
                shutil.copy2(fd / n, h / "public" / "fonts" / n)
    state["src"] = want
    _write_state(h, state)
    return True


def _write_state(h: Path, state: dict) -> None:
    h.mkdir(parents=True, exist_ok=True)
    (h / STATE_FILE).write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def _stream(args: list[str], cwd: Path, log: LogFn, cancel=None, err_file: Path | None = None,
            on_line: Callable[[str], None] | None = None, stall: float = STALL_SEC,
            env: dict | None = None) -> int:
    """Chạy tiến trình, đọc stdout từng dòng (stderr ghi ra file — tránh nghẽn ống)."""
    err_file = err_file or (cwd / "last-error.log")
    with open(err_file, "w", encoding="utf-8", errors="replace") as ef:
        proc = subprocess.Popen(args, cwd=str(cwd), stdout=subprocess.PIPE, stderr=ef,
                                stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                                errors="replace", env=env, **_no_window())
        last = [time.time()]
        stop = [False]

        def watch():
            while proc.poll() is None:
                if (cancel and cancel()) or time.time() - last[0] > stall:
                    stop[0] = True
                    try:
                        proc.kill()
                    except OSError:
                        pass
                    return
                time.sleep(0.5)
        threading.Thread(target=watch, daemon=True).start()
        assert proc.stdout is not None
        for line in proc.stdout:
            last[0] = time.time()
            line = line.rstrip("\r\n")
            if line and on_line:
                on_line(line)
        rc = proc.wait()
    if stop[0]:
        if cancel and cancel():
            from .media import Cancelled
            raise Cancelled()
        raise RuntimeError(f"Tiến trình Node không phản hồi quá {int(stall)} giây — đã dừng")
    return rc


def _tail(p: Path, n: int = 6) -> str:
    try:
        lines = [x for x in p.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()]
        return " | ".join(lines[-n:])
    except OSError:
        return ""


def install(base: Path | None = None, log: LogFn = print, cancel=None) -> Status:
    """Chép engine, `npm ci`, chuẩn bị trình duyệt. Chỉ cần làm một lần (và khi tool
    lên bản có Remotion mới). Ném RuntimeError với lời giải thích khi hỏng."""
    src = source_dir()
    if not src:
        raise RuntimeError("Bản tool này thiếu thư mục assets/remotion-engine")
    n = find_node()
    if not n:
        raise RuntimeError(f"Chưa có Node.js {NODE_MIN_MAJOR}+ trên máy. Tải bản LTS tại "
                           "https://nodejs.org, cài xong mở lại tool rồi bấm 'Cài Remotion'.")
    node, ver = n
    npm = npm_command(node)
    if not npm:
        raise RuntimeError("Không thấy npm đi kèm Node.js — cài lại Node.js bản LTS từ nodejs.org")
    h = home(base)
    log(f"[REMOTION] Node {ver}: {node}")
    log(f"[REMOTION] Thư mục cài: {h}")
    state = _read_state(h)
    sync_source(h, src)
    state = _read_state(h)
    want_lock = lock_hash(src)
    has_mods = (h / "node_modules" / "remotion" / "package.json").is_file()
    if not has_mods or state.get("lock") != want_lock:
        log("[REMOTION] Đang tải các gói Remotion (npm ci, khoảng 200 MB — vài phút)…")
        env = dict(os.environ)
        env.setdefault("npm_config_update_notifier", "false")
        # node.exe phải nằm trong PATH để các script cài gói gọi được
        env["PATH"] = str(Path(node).resolve().parent) + os.pathsep + env.get("PATH", "")
        rc = _stream(npm + ["ci", "--omit=dev", "--no-audit", "--no-fund", "--loglevel=error"],
                     h, log, cancel, err_file=h / "npm-error.log",
                     on_line=lambda s: log(f"[REMOTION] {s}") if s.strip() else None,
                     stall=900, env=env)
        if rc != 0:
            raise RuntimeError("npm ci thất bại: " + (_tail(h / "npm-error.log") or f"mã {rc}")
                               + f" — chi tiết: {h / 'npm-error.log'}")
        state["lock"] = want_lock
        _write_state(h, state)
        log("[REMOTION] Đã cài xong các gói")
    else:
        log("[REMOTION] Các gói đã có sẵn, bỏ qua bước tải")
    # trình duyệt: Chrome Headless Shell của Remotion (tự tải ~90 MB), không được thì Chrome/Edge
    args = [node, "render.mjs", "ensure"]
    for b in system_browsers():
        args += ["--fallback", b]
    got: dict = {}
    last_pct = [-10]

    def on_line(s: str):
        try:
            ev = json.loads(s)
        except ValueError:
            return
        e = ev.get("event")
        if e == "download":
            pct = int(100 * float(ev.get("p") or 0))
            if pct >= last_pct[0] + 10:
                last_pct[0] = pct
                log(f"[REMOTION] Đang tải Chrome Headless Shell… {pct}%")
        elif e == "warn":
            log("[WARN] " + str(ev.get("text")))
        elif e == "browser":
            got.update(ev)
        elif e == "error":
            got["error"] = ev.get("error")

    rc = _stream(args, h, log, cancel, err_file=h / "browser-error.log", on_line=on_line, stall=900)
    if rc != 0 or not got.get("kind"):
        raise RuntimeError("Không chuẩn bị được trình duyệt cho Remotion: "
                           + str(got.get("error") or _tail(h / "browser-error.log") or f"mã {rc}"))
    state = _read_state(h)
    state["browser"] = got.get("path")
    state["browser_kind"] = got.get("kind")
    _write_state(h, state)
    kind = {"headless-shell": "Chrome Headless Shell", "system": "trình duyệt có sẵn"}.get(
        got.get("kind"), got.get("kind"))
    log(f"[REMOTION] Trình duyệt: {kind} — {got.get('path')}")
    st = status(base)
    if st.ready:
        log("[SUCCESS] Remotion đã sẵn sàng. Tích ô 'Vẽ thẻ từ gốc (TERM) và dòng thời gian "
            "(TIMELINE) bằng Remotion' (Cài đặt → Phụ đề) để dùng.")
    return st


# --------------------------------------------------------------------------- #
# vẽ clip
# --------------------------------------------------------------------------- #
@dataclass
class Job:
    kind: str
    scene: int
    props: dict
    out: Path

    @property
    def comp(self) -> str:
        return COMPOSITION[self.kind]


def frames_for(length: float, fps: int) -> int:
    """Số khung của clip: phủ hết `length` + 1 khung dư (trong suốt) để CapCut không
    báo 'vượt quá độ dài tư liệu' khi làm tròn micro giây."""
    return max(2, int(math.ceil(length * fps - 1e-6)) + 1)


def make_props(item, st, size: tuple[int, int], fps: int, length: float) -> dict:
    """Dữ liệu một đồ họa cho Remotion (cùng cách tách chữ với bản Pillow)."""
    from .overlay_draw import BASE_SIZE, _split_term, is_hebrew, timeline_points
    w, h = size
    k = min(w, h) / 1080.0 * st.scale * BASE_SIZE
    base = {"width": int(w), "height": int(h), "fps": int(fps), "frames": frames_for(length, fps),
            "lengthSec": round(float(length), 4),
            "style": {"accent": st.accent, "boxAlpha": round(st.box_alpha, 3), "k": round(k, 4)}}
    if item.kind == "TERM":
        term, orig = _split_term(item.text)
        return {**base, "term": term, "orig": orig, "hebrew": bool(is_hebrew(orig)),
                "label": item.label or "", "sub": item.sub or ""}
    if item.kind == "TIMELINE":
        pts = [{"label": lab, "cur": bool(cur)} for lab, cur in timeline_points(item.text)]
        return {**base, "points": pts, "label": item.label or "", "subsOn": bool(st.subs_on)}
    raise ValueError(item.kind)


def clip_name(kind: str, props: dict, src_hash: str) -> str:
    raw = json.dumps({"k": kind, "p": props, "e": src_hash}, sort_keys=True, ensure_ascii=False)
    return f"rm_{kind.lower()}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:14]}.mov"


def prune_cache(cache: Path, keep: set[Path], days: int = CACHE_KEEP_DAYS) -> int:
    """Xoá clip lâu không dùng (clip vừa dùng được 'chạm' mtime nên không bị xoá)."""
    n = 0
    limit = time.time() - days * 86400
    for f in cache.glob("rm_*.mov*"):
        try:
            if f.resolve() in keep:
                continue
            if f.name.endswith(".part.mov") or f.stat().st_mtime < limit:
                f.unlink()
                n += 1
        except OSError:
            pass
    return n


def render_jobs(jobs: list[Job], base: Path | None = None, log: LogFn = print,
                cancel=None) -> dict[Path, bool]:
    """Vẽ các clip còn thiếu. Trả về {đường dẫn clip: có dùng được không}."""
    result: dict[Path, bool] = {}
    todo: list[Job] = []
    seen: set[Path] = set()
    for j in jobs:
        if j.out in seen:
            continue
        seen.add(j.out)
        if j.out.is_file() and j.out.stat().st_size > 0:
            result[j.out] = True
            try:
                os.utime(j.out, None)
            except OSError:
                pass
        else:
            todo.append(j)
    if not todo:
        return result
    st = status(base)
    if not st.ready:
        log("[WARN] Remotion chưa sẵn sàng (" + st.text() + ") → vẽ bằng Pillow như cũ")
        for j in todo:
            result[j.out] = False
        return result
    h = st.home
    sync_source(h)
    todo[0].out.parent.mkdir(parents=True, exist_ok=True)
    spec = {"browser": st.browser if st.browser_kind != "headless-shell" else None,
            "fallbacks": system_browsers(),
            "jobs": [{"comp": j.comp, "props": j.props, "out": str(j.out)} for j in todo]}
    fd, tmp = tempfile.mkstemp(prefix="cds-remotion-", suffix=".json")
    os.close(fd)
    Path(tmp).write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    t0 = time.time()
    log(f"[BUILD] Remotion: vẽ {len(todo)} clip đồ họa chuyển động "
        f"(khoảng {max(1, round(sum(j.props['frames'] for j in todo) / 5.5 / 60))} phút trên máy 2 nhân)…")
    errors: list[str] = []
    done_n = [0]

    def on_line(s: str):
        try:
            ev = json.loads(s)
        except ValueError:
            return
        e = ev.get("event")
        if e == "done":
            done_n[0] += 1
            j = todo[int(ev["i"])]
            result[j.out] = j.out.is_file()
            log(f"[BUILD] Remotion {done_n[0]}/{len(todo)}: {j.kind} cảnh {j.scene} "
                f"({float(ev.get('sec', 0)):.0f} s)")
        elif e == "fail":
            j = todo[int(ev["i"])]
            result[j.out] = False
            errors.append(f"{j.kind} cảnh {j.scene}: {ev.get('error')}")
        elif e == "warn":
            log("[WARN] Remotion: " + str(ev.get("text")))
        elif e == "error":
            errors.append(str(ev.get("error")))

    try:
        rc = _stream([st.node, "render.mjs", "render", tmp], h, log, cancel,
                     err_file=h / "render-error.log", on_line=on_line)
        if rc != 0 and not errors:
            errors.append(_tail(h / "render-error.log") or f"Node thoát với mã {rc}")
    except RuntimeError as e:
        errors.append(str(e))
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    for j in todo:
        result.setdefault(j.out, False)
    for e in errors[:6]:
        log(f"[WARN] Remotion: {e}")
    bad = sum(1 for j in todo if not result.get(j.out))
    if bad:
        log(f"[WARN] Remotion: {bad} clip không vẽ được → các mục đó dùng bản Pillow như cũ "
            f"(chi tiết: {h / 'render-error.log'})")
    log(f"[BUILD] Remotion xong {len(todo) - bad}/{len(todo)} clip sau {time.time() - t0:.0f} s")
    return result
