"""Render video trực tiếp bằng ffmpeg từ chính kế hoạch cảnh của tool.

Tool KHÔNG gọi được lệnh render của CapCut (CapCut không mở API), nên bản render
này dựng lại video từ đầu bằng ffmpeg theo đúng `ScenePlan` đã lập:

    1. từng cảnh  → segments/seg_NNNN.mp4   (chỉ hình, đã scale/speed/Ken Burns)
    2. ghép cảnh  → video.mp4               (xfade nếu bật chuyển cảnh)
    3. các đường tiếng → voice / srcaudio / bgm / sfx
    4. trộn lại   → file .mp4 cuối, chèn claim + logo, ghi phụ đề lên hình

Hình không bao giờ giống CapCut 100% (CapCut có hiệu ứng riêng), nhưng thời
lượng, thứ tự cảnh, khoảng nghỉ, âm lượng và phụ đề thì khớp với draft.

Mọi hàm dựng câu lệnh đều thuần (không chạy ffmpeg) để test được độc lập.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import animations
from .media import Cancelled
from .models import Assets, ScenePlan, Settings, LogFn

# --------------------------------------------------------------------------- #
# lỗi & tiện ích
# --------------------------------------------------------------------------- #


class RenderError(RuntimeError):
    """Lỗi người dùng cần biết — hiện nguyên văn lên giao diện."""


FFMPEG_HINT = (
    "Không tìm thấy ffmpeg — đây là công cụ ghép video mà tool dùng để render.\n\n"
    "Cách sửa:\n"
    "• Windows: tải bản 'ffmpeg-release-essentials' ở https://www.gyan.dev/ffmpeg/builds/ "
    "rồi copy ffmpeg.exe và ffprobe.exe vào thư mục 'bin' cạnh file tool.\n"
    "• macOS: mở Terminal và chạy: brew install ffmpeg\n\n"
    "Bản cài đặt chính thức của tool đã kèm sẵn ffmpeg, nên lỗi này chỉ gặp khi "
    "bạn chạy từ mã nguồn."
)

RES_CHOICES: tuple[tuple[str, str], ...] = (
    ("source", "Giữ như project"),
    ("2160", "4K — 2160p"),
    ("1440", "2K — 1440p"),
    ("1080", "Full HD — 1080p"),
    ("720", "HD — 720p"),
    ("480", "SD — 480p"),
)

PRESET_CHOICES: tuple[tuple[str, str], ...] = (
    ("veryfast", "Rất nhanh (file to hơn)"),
    ("faster", "Nhanh"),
    ("medium", "Cân bằng (khuyến nghị)"),
    ("slow", "Chậm (file nhỏ, nét hơn)"),
)

CODEC_CHOICES: tuple[tuple[str, str], ...] = (
    ("h264", "H.264 — tương thích mọi nơi"),
    ("h265", "H.265 — file nhẹ hơn ~30%"),
)

QUALITY_CHOICES: tuple[tuple[str, str], ...] = (
    ("16", "Rất cao (file to)"),
    ("20", "Cao (khuyến nghị)"),
    ("23", "Trung bình"),
    ("26", "Nhẹ (file nhỏ)"),
)

HW_ENCODERS = {
    "h264": ("h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox"),
    "h265": ("hevc_nvenc", "hevc_qsv", "hevc_amf", "hevc_videotoolbox"),
}
SW_ENCODERS = {"h264": "libx264", "h265": "libx265"}


def _exe(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def find_tool(name: str) -> str | None:
    """Tìm ffmpeg/ffprobe: bản đi kèm tool trước, rồi tới PATH của hệ thống."""
    candidates = [
        _app_dir() / "bin" / _exe(name),
        _app_dir() / _exe(name),
    ]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.insert(0, Path(meipass) / "bin" / _exe(name))
    if sys.platform == "darwin":
        candidates += [Path("/opt/homebrew/bin") / name, Path("/usr/local/bin") / name]
    for c in candidates:
        try:
            if c.is_file():
                return str(c)
        except OSError:
            continue
    return shutil.which(name)


def require_tools() -> tuple[str, str]:
    ff = find_tool("ffmpeg")
    fp = find_tool("ffprobe") or ff
    if not ff:
        raise RenderError(FFMPEG_HINT)
    return ff, fp


def ffmpeg_ready() -> bool:
    return find_tool("ffmpeg") is not None


def _run_text(args: list[str], timeout: int = 20) -> str:
    try:
        cp = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                            **_no_window())
        return (cp.stdout or "") + (cp.stderr or "")
    except Exception:
        return ""


def _no_window() -> dict:
    """Không bật cửa sổ console đen khi .exe chạy ở chế độ windowed."""
    if os.name == "nt":
        return {"creationflags": 0x08000000}   # CREATE_NO_WINDOW
    return {}


def available_encoders(ffmpeg: str) -> set[str]:
    out = _run_text([ffmpeg, "-hide_banner", "-encoders"])
    return set(re.findall(r"^\s*[A-Z.]{6}\s+(\S+)", out, re.M))


_ENCODER_CACHE: dict[tuple[str, str], bool] = {}


def encoder_works(ffmpeg: str, encoder: str) -> bool:
    """Thử encode 1 khung hình thật.

    Danh sách `-encoders` của ffmpeg liệt kê cả encoder đã biên dịch nhưng máy
    không chạy được (không có driver NVIDIA/Intel). Phải thử thật, nếu không
    toàn bộ render sẽ đổ ngay ở cảnh đầu.
    """
    key = (ffmpeg, encoder)
    if key in _ENCODER_CACHE:
        return _ENCODER_CACHE[key]
    probe = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
             "-f", "lavfi", "-i", "color=c=black:s=256x256:r=25:d=0.2",
             "-frames:v", "2", "-c:v", encoder, "-f", "null", "-"]
    try:
        ok = subprocess.run(probe, capture_output=True, text=True, timeout=25,
                            **_no_window()).returncode == 0
    except Exception:
        ok = False
    _ENCODER_CACHE[key] = ok
    return ok


def pick_encoder(ffmpeg: str, codec: str, hw: str = "auto") -> str:
    """Chọn encoder: ưu tiên card đồ hoạ CHẠY ĐƯỢC, không thì dùng CPU."""
    codec = "h265" if str(codec).lower() in ("h265", "hevc") else "h264"
    if str(hw).lower() == "cpu":
        return SW_ENCODERS[codec]
    have = available_encoders(ffmpeg)
    for enc in HW_ENCODERS[codec]:
        if enc in have and encoder_works(ffmpeg, enc):
            return enc
    return SW_ENCODERS[codec]


def quality_args(encoder: str, crf: int, preset: str) -> list[str]:
    """Tham số chất lượng — encoder phần cứng không hiểu crf/preset của x264."""
    crf = int(crf)
    if encoder.endswith("nvenc"):
        return ["-rc", "vbr", "-cq", str(crf), "-preset", "p5", "-b:v", "0"]
    if encoder.endswith("qsv"):
        return ["-global_quality", str(crf), "-preset", "medium"]
    if encoder.endswith("amf"):
        return ["-rc", "cqp", "-qp_i", str(crf), "-qp_p", str(crf), "-quality", "balanced"]
    if encoder.endswith("videotoolbox"):
        # videotoolbox không có crf, quy đổi sang thang chất lượng 0..100
        q = max(20, min(95, int(round(100 - crf * 2.6))))
        return ["-q:v", str(q)]
    return ["-crf", str(crf), "-preset", str(preset or "medium")]


def probe_has_audio(ffprobe: str, path: Path) -> bool:
    out = _run_text([ffprobe, "-v", "error", "-select_streams", "a:0",
                     "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)])
    return "audio" in out


def probe_size(ffprobe: str, path: Path) -> tuple[int, int] | None:
    out = _run_text([ffprobe, "-v", "error", "-select_streams", "v:0",
                     "-show_entries", "stream=width,height", "-of", "json", str(path)])
    try:
        st = json.loads(out)["streams"][0]
        return int(st["width"]), int(st["height"])
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# kích thước & bộ lọc
# --------------------------------------------------------------------------- #


def _even(v: float) -> int:
    return max(2, int(round(v / 2.0)) * 2)


def target_size(s: Settings) -> tuple[int, int]:
    """Khung hình đầu ra: 'Giữ như project' hoặc quy về chiều ngắn đã chọn."""
    w, h = int(s.width), int(s.height)
    raw = str(getattr(s, "render_res", "source") or "source").lower()
    if raw in ("", "source", "goc", "gốc"):
        return _even(w), _even(h)
    try:
        short = int(raw)
    except ValueError:
        return _even(w), _even(h)
    if w >= h:
        return _even(short * w / h), _even(short)
    return _even(short), _even(short * h / w)


def target_fps(s: Settings) -> int:
    fps = int(getattr(s, "render_fps", 0) or 0)
    return fps if fps > 0 else max(1, int(s.fps))


def atempo_chain(speed: float) -> str | None:
    """atempo chỉ nhận 0.5–100; tốc độ ngoài khoảng đó phải xếp tầng nhiều lớp."""
    speed = float(speed)
    if abs(speed - 1.0) < 1e-6:
        return None
    if speed <= 0:
        return None
    parts: list[str] = []
    remain = speed
    guard = 0
    while remain < 0.5 and guard < 8:
        parts.append("atempo=0.5")
        remain /= 0.5
        guard += 1
    while remain > 100.0 and guard < 16:
        parts.append("atempo=100")
        remain /= 100.0
        guard += 1
    if abs(remain - 1.0) > 1e-6:
        parts.append(f"atempo={remain:.6f}")
    return ",".join(parts) if parts else None


def kenburns_filter(anim_key: str, duration: float, fps: int, w: int, h: int,
                    supersample: int = 4) -> str:
    """Chuỗi filter ffmpeg mô phỏng hiệu ứng Ken Burns của tool.

    Hệ toạ độ của tool: `position_x/y` tính theo NỬA khung hình, y dương là
    LÊN. zoompan làm việc trên ảnh đã phóng `supersample` lần, nên 1 pixel đầu
    ra tương ứng `supersample/zoom` pixel đầu vào.
    """
    fill = (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1")
    specs = {name: (a, b) for name, a, b in animations.keyframes_for(anim_key)}
    if not specs:
        return fill
    z0, z1 = specs.get("uniform_scale", (1.0, 1.0))
    x0, x1 = specs.get("position_x", (0.0, 0.0))
    y0, y1 = specs.get("position_y", (0.0, 0.0))
    frames = max(2, int(round(max(0.04, duration) * fps)))
    p = f"(on/{frames - 1})"
    z = f"({z0:.6f}+({z1 - z0:.6f})*{p})"
    px = f"({x0:.6f}+({x1 - x0:.6f})*{p})"
    py = f"({y0:.6f}+({y1 - y0:.6f})*{p})"
    k = supersample / 2.0
    big = f"scale={w * supersample}:{h * supersample}"
    zp = (f"zoompan=z='{z}'"
          f":x='(iw-iw/zoom)/2-{k:.1f}*{w}*{px}/zoom'"
          f":y='(ih-ih/zoom)/2+{k:.1f}*{h}*{py}/zoom'"
          f":d=1:s={w}x{h}:fps={fps}")
    return f"{fill},{big},{zp},setsar=1"


def video_scene_filter(speed: float, fps: int, w: int, h: int) -> str:
    parts: list[str] = []
    if abs(float(speed) - 1.0) > 1e-6:
        parts.append(f"setpts=PTS/{float(speed):.6f}")
    parts += [f"scale={w}:{h}:force_original_aspect_ratio=increase",
              f"crop={w}:{h}", "setsar=1", f"fps={fps}"]
    return ",".join(parts)


def ass_escape(path: Path) -> str:
    """Đường dẫn cho filter subtitles: dấu \\ và : phải được escape."""
    raw = str(path).replace("\\", "/")
    raw = raw.replace(":", "\\:").replace("'", "\\'").replace("[", "\\[").replace("]", "\\]")
    return raw


def subtitle_force_style(s: Settings, h: int) -> str:
    """force_style của libass, mang theo bóng đổ đúng độ mờ người dùng chọn."""
    margin = max(8, int(round(0.10 * h)))
    font_size = max(14, int(round(h * 0.045)))
    items = [f"FontSize={font_size}", "Alignment=2", f"MarginV={margin}",
             "PrimaryColour=&H00FFFFFF", "Outline=1", "BorderStyle=1"]
    if getattr(s, "sub_shadow", False):
        alpha = max(0.0, min(1.0, float(getattr(s, "sub_shadow_alpha", 0.9))))
        # ASS dùng &HAABBGGRR, AA là độ TRONG SUỐT (0 = đặc)
        aa = max(0, min(255, int(round((1.0 - alpha) * 255))))
        depth = max(1, int(round(float(getattr(s, "sub_shadow_distance", 5.0)) / 2.5)))
        items += [f"Shadow={depth}", f"BackColour=&H{aa:02X}000000"]
    else:
        items.append("Shadow=0")
    return ",".join(items)


def overlay_position(x: float, y: float, w: int, h: int) -> tuple[str, str]:
    """Đổi toạ độ CapCut (-1..1, y dương = lên) sang toạ độ overlay của ffmpeg."""
    cx = w * (1.0 + float(x)) / 2.0
    cy = h * (1.0 - float(y)) / 2.0
    return f"{cx:.2f}-overlay_w/2", f"{cy:.2f}-overlay_h/2"


# --------------------------------------------------------------------------- #
# mô tả một lần render
# --------------------------------------------------------------------------- #


@dataclass
class RenderJob:
    """Một video cần render."""

    name: str
    settings: Settings
    assets: Assets
    plan: list[ScenePlan]
    out_path: Path
    srt_path: Path | None = None
    status: str = "pending"        # pending | running | done | error | cancelled
    message: str = ""
    percent: float = 0.0
    eta_sec: float = 0.0
    elapsed_sec: float = 0.0

    @property
    def duration(self) -> float:
        return self.plan[-1].end if self.plan else 0.0


def default_out_path(s: Settings, name: str) -> Path:
    base = Path(s.render_out_dir) if getattr(s, "render_out_dir", None) else \
        Path(s.input_dir) / "_render"
    safe = re.sub(r'[<>:"/\\|?*]+', "_", name).strip(" .") or "video"
    return base / f"{safe}.mp4"


# --------------------------------------------------------------------------- #
# bộ render
# --------------------------------------------------------------------------- #

PHASE_WEIGHT = {"scenes": 0.55, "audio": 0.10, "concat": 0.15, "final": 0.20}


class Renderer:
    """Chạy ffmpeg theo từng bước, báo % và thời gian còn lại."""

    def __init__(self, job: RenderJob, log: LogFn = print, progress=None, cancel=None):
        self.job = job
        self.s = job.settings
        self.log = log
        self._progress = progress
        self._cancel = cancel
        self.ffmpeg, self.ffprobe = require_tools()
        self.w, self.h = target_size(self.s)
        self.fps = target_fps(self.s)
        self.encoder = pick_encoder(self.ffmpeg, getattr(self.s, "render_codec", "h264"),
                                    getattr(self.s, "render_hw", "auto"))
        self.trans = (float(self.s.trans_dur)
                      if self.s.enable_transition and len(job.plan) > 1 else 0.0)
        self.work = job.out_path.parent / f".{job.out_path.stem}-tmp"
        self._t0 = 0.0
        self._done_weight = 0.0
        self._proc: subprocess.Popen | None = None

    # -- tiến trình ------------------------------------------------------- #
    def _check(self) -> None:
        if self._cancel and self._cancel():
            raise Cancelled()

    def _emit(self, phase_fraction: float, phase: str) -> None:
        total = self._done_weight + PHASE_WEIGHT.get(phase, 0.0) * max(0.0, min(1.0, phase_fraction))
        total = max(0.0, min(1.0, total))
        elapsed = time.time() - self._t0
        eta = (elapsed / total - elapsed) if total > 0.02 else 0.0
        self.job.percent = total * 100.0
        self.job.eta_sec = max(0.0, eta)
        self.job.elapsed_sec = elapsed
        if self._progress:
            self._progress(phase, total * 100.0, max(0.0, eta))

    def _finish_phase(self, phase: str) -> None:
        self._done_weight = min(1.0, self._done_weight + PHASE_WEIGHT.get(phase, 0.0))
        self._emit(0.0, phase)

    # -- chạy ffmpeg ------------------------------------------------------ #
    def _ffmpeg(self, args: list[str], expect_sec: float, phase: str,
                base_fraction: float = 0.0, span: float = 1.0) -> None:
        """Chạy một lệnh ffmpeg, đọc -progress để cập nhật %."""
        self._check()
        cmd = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
               "-progress", "pipe:1", "-nostats"] + args
        # stderr ra FILE chứ không ra pipe: nếu ffmpeg in nhiều cảnh báo mà mình
        # chỉ đọc stdout thì pipe stderr đầy và cả hai bên treo nhau.
        self.work.mkdir(parents=True, exist_ok=True)
        err_path = self.work / "ffmpeg-last.log"
        tail: list[str] = []
        with err_path.open("w", encoding="utf-8", errors="replace") as errf:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf,
                                          text=True, bufsize=1, **_no_window())
            try:
                for line in self._proc.stdout or []:
                    if self._cancel and self._cancel():
                        self._kill()
                        raise Cancelled()
                    if line.startswith("out_time_ms=") and expect_sec > 0:
                        try:
                            done = int(line.split("=", 1)[1].strip()) / 1_000_000.0
                        except ValueError:
                            continue
                        self._emit(base_fraction + span * min(1.0, done / expect_sec), phase)
                self._proc.wait(timeout=60)
            finally:
                proc, self._proc = self._proc, None
        try:
            tail = [l for l in err_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    if l.strip()][-6:]
        except OSError:
            tail = []
        if proc.returncode != 0:
            raise RenderError("ffmpeg lỗi:\n" + ("\n".join(tail) or f"mã lỗi {proc.returncode}"))
        self._emit(base_fraction + span, phase)

    def _kill(self) -> None:
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass

    # -- bước 1: từng cảnh ------------------------------------------------ #
    def _scene_len(self, i: int, p: ScenePlan) -> float:
        """Độ dài clip trung gian: thêm phần đuôi để chuyển cảnh có chỗ hoà."""
        extra = self.trans if i < len(self.job.plan) - 1 else 0.0
        return p.slot_duration + extra

    def scene_args(self, i: int, p: ScenePlan, out: Path) -> list[str]:
        length = self._scene_len(i, p)
        vf: list[str] = []
        args: list[str] = []
        if p.mode == "IMAGE":
            args += ["-loop", "1", "-framerate", str(self.fps), "-t", f"{length:.4f}",
                     "-i", str(p.visual_path)]
            picker = animations.AnimPicker(self.s.image_anim)
            key = picker.pick(i) if self.s.image_anim else animations.MODE_OFF
            vf.append(kenburns_filter(key, length, self.fps, self.w, self.h))
        else:
            args += ["-i", str(p.visual_path)]
            vf.append(video_scene_filter(p.speed, self.fps, self.w, self.h))
            if self.trans and i < len(self.job.plan) - 1:
                vf.append(f"tpad=stop_mode=clone:stop_duration={self.trans:.4f}")
        return args + ["-an", "-vf", ",".join(vf), "-t", f"{length:.4f}",
                       "-c:v", self.encoder,
                       *quality_args(self.encoder, self.s.render_crf, self.s.render_preset),
                       "-pix_fmt", "yuv420p", str(out)]

    def _render_scenes(self) -> list[Path]:
        seg_dir = self.work / "segments"
        seg_dir.mkdir(parents=True, exist_ok=True)
        plan = self.job.plan
        total = sum(self._scene_len(i, p) for i, p in enumerate(plan)) or 1.0
        outs: list[Path] = []
        acc = 0.0
        for i, p in enumerate(plan):
            self._check()
            out = seg_dir / f"seg_{i:04d}.mp4"
            length = self._scene_len(i, p)
            self._ffmpeg(self.scene_args(i, p, out), length, "scenes",
                         base_fraction=acc / total, span=length / total)
            acc += length
            outs.append(out)
            if (i + 1) % 20 == 0:
                self.log(f"[RENDER] Đã dựng {i + 1}/{len(plan)} cảnh")
        self._finish_phase("scenes")
        return outs

    # -- bước 2: ghép cảnh ------------------------------------------------ #
    def concat_args(self, segs: list[Path], out: Path) -> list[str]:
        args: list[str] = []
        for seg in segs:
            args += ["-i", str(seg)]
        n = len(segs)
        if n == 1:
            chain = "[0:v]copy[vout]"
        elif self.trans <= 0:
            chain = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vout]"
        else:
            # xfade tiêu thụ đúng phần đuôi đã thêm ở bước 1 nên tổng thời lượng
            # vẫn bằng tổng slot -> tiếng và hình không bị lệch.
            links = []
            offset = 0.0
            prev = "[0:v]"
            for i in range(1, n):
                offset += self.job.plan[i - 1].slot_duration
                label = "[vout]" if i == n - 1 else f"[x{i}]"
                links.append(f"{prev}[{i}:v]xfade=transition=fade"
                             f":duration={self.trans:.4f}:offset={offset:.4f}{label}")
                prev = label
            chain = ";".join(links)
        return args + ["-filter_complex", chain, "-map", "[vout]",
                       "-c:v", self.encoder,
                       *quality_args(self.encoder, self.s.render_crf, self.s.render_preset),
                       "-pix_fmt", "yuv420p", "-an", str(out)]

    def _concat(self, segs: list[Path]) -> Path:
        out = self.work / "video.mp4"
        self._ffmpeg(self.concat_args(segs, out), self.job.duration, "concat")
        self._finish_phase("concat")
        return out

    # -- bước 3: các đường tiếng ------------------------------------------ #
    def _wav(self, args: list[str], out: Path) -> None:
        self._ffmpeg(args + ["-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(out)],
                     0.0, "audio")

    def _concat_wavs(self, pieces: list[Path], out: Path, kbps: int) -> Path | None:
        if not pieces:
            return None
        listing = out.with_suffix(".txt")
        listing.write_text(
            "\n".join("file '" + str(p).replace("\\", "/").replace("'", "'\\''") + "'"
                      for p in pieces), encoding="utf-8")
        self._ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing),
                      "-c:a", "aac", "-b:a", f"{kbps}k", str(out)], 0.0, "audio")
        return out

    def _silence(self, seconds: float, out: Path) -> Path:
        self._wav(["-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo",
                   "-t", f"{max(0.02, seconds):.4f}"], out)
        return out

    def _build_voice(self) -> Path | None:
        if not self.s.enable_voice:
            return None
        pdir = self.work / "voice"
        pdir.mkdir(parents=True, exist_ok=True)
        pieces: list[Path] = []
        for i, p in enumerate(self.job.plan):
            self._check()
            piece = pdir / f"v_{i:04d}.wav"
            # apad cho đủ trọn ô thời gian của cảnh (giọng đọc + khoảng nghỉ)
            self._wav(["-i", str(p.audio_path), "-vn",
                       "-af", f"volume={float(self.s.voice_vol):.4f},apad",
                       "-t", f"{p.slot_duration:.4f}"], piece)
            pieces.append(piece)
        return self._concat_wavs(pieces, self.work / "voice.m4a", self.s.render_audio_kbps)

    def _build_source_audio(self) -> Path | None:
        vol = float(getattr(self.s, "video_vol", 1.0))
        if vol <= 0:
            return None
        plan = self.job.plan
        if not any(p.mode != "IMAGE" for p in plan):
            return None
        pdir = self.work / "srcaudio"
        pdir.mkdir(parents=True, exist_ok=True)
        pieces: list[Path] = []
        used = False
        for i, p in enumerate(plan):
            self._check()
            piece = pdir / f"s_{i:04d}.wav"
            has = p.mode != "IMAGE" and probe_has_audio(self.ffprobe, p.visual_path)
            tempo = atempo_chain(p.speed) if has else None
            if has and (abs(p.speed - 1.0) < 1e-6 or tempo):
                chain = [f"volume={vol:.4f}"]
                if tempo:
                    chain.insert(0, tempo)
                chain.append("apad")
                self._wav(["-i", str(p.visual_path), "-vn", "-af", ",".join(chain),
                           "-t", f"{p.slot_duration:.4f}"], piece)
                used = True
            else:
                self._silence(p.slot_duration, piece)
            pieces.append(piece)
        if not used:
            return None
        return self._concat_wavs(pieces, self.work / "srcaudio.m4a", self.s.render_audio_kbps)

    def _build_bgm(self) -> Path | None:
        from .capcut_engine import resolve_music_roles
        from .media import media_duration_sec
        if not (self.s.enable_bgm and self.job.assets.bgm_files):
            return None
        total = self.job.duration
        roles = resolve_music_roles(self.s, self.job.assets.bgm_files)
        intros = [r for r in roles if r[1]]
        bgs = [r for r in roles if r[2]]
        pdir = self.work / "bgm"
        pdir.mkdir(parents=True, exist_ok=True)
        pieces: list[Path] = []
        cursor = 0.0
        if intros:
            f, _, _, mul = intros[0]
            dur = min(media_duration_sec(f), self.s.bgm_intro_max_dur, total)
            piece = pdir / "b_intro.wav"
            self._wav(["-i", str(f), "-vn", "-t", f"{dur:.4f}",
                       "-af", f"volume={self.s.bgm_intro_vol_high * mul:.4f},"
                              f"afade=t=out:st={max(0.0, dur - min(1.0, dur / 3)):.4f}"
                              f":d={min(1.0, dur / 3):.4f},apad", ], piece)
            pieces.append(piece)
            cursor = dur
        idx = 0
        while bgs and cursor < total - 0.05 and idx < 400:
            self._check()
            f, _, _, mul = bgs[idx % len(bgs)]
            want = min(media_duration_sec(f), total - cursor)
            piece = pdir / f"b_{idx:03d}.wav"
            fade = min(float(self.s.crossfade_sec), max(0.1, want / 3))
            self._wav(["-i", str(f), "-vn", "-t", f"{want:.4f}",
                       "-af", f"volume={self.s.bgm_body_vol * mul:.4f},"
                              f"afade=t=in:st=0:d={fade:.4f},"
                              f"afade=t=out:st={max(0.0, want - fade):.4f}:d={fade:.4f},apad"],
                      piece)
            pieces.append(piece)
            cursor += want
            idx += 1
        return self._concat_wavs(pieces, self.work / "bgm.m4a", self.s.render_audio_kbps)

    def _build_sfx(self) -> Path | None:
        from .media import media_duration_sec
        items = [it for it in self.job.assets.sfx_items
                 if self.s.sfx_roles.get(it["name"]) == "placed"]
        if not items:
            return None
        plan = self.job.plan
        args: list[str] = []
        chains: list[str] = []
        labels: list[str] = []
        for i, it in enumerate(items[:24]):
            start = plan[i % len(plan)].start
            try:
                dur = min(2.0, media_duration_sec(Path(it["path"])))
            except Exception:
                continue
            args += ["-i", str(it["path"])]
            lab = f"[s{i}]"
            chains.append(f"[{len(labels)}:a]atrim=0:{dur:.3f},"
                          f"adelay={int(start * 1000)}|{int(start * 1000)}{lab}")
            labels.append(lab)
        if not labels:
            return None
        chain = ";".join(chains) + ";" + "".join(labels) + \
            f"amix=inputs={len(labels)}:duration=longest:normalize=0[aout]"
        out = self.work / "sfx.m4a"
        self._ffmpeg(args + ["-filter_complex", chain, "-map", "[aout]",
                             "-c:a", "aac", "-b:a", f"{self.s.render_audio_kbps}k",
                             str(out)], 0.0, "audio")
        return out

    # -- bước 4: trộn cuối ------------------------------------------------ #
    def final_args(self, video: Path, tracks: list[Path], out: Path) -> list[str]:
        s, w, h = self.s, self.w, self.h
        args = ["-i", str(video)]
        for t in tracks:
            args += ["-i", str(t)]
        extra_index = 1 + len(tracks)
        vchain = ["[0:v]null[v0]"]
        cur = "[v0]"
        claim = self.job.assets.claim if s.enable_claim else None
        logo = self.job.assets.logo if s.enable_logo else None
        if claim and Path(claim).is_file():
            args += ["-loop", "1", "-t", f"{min(s.claim_dur, self.job.duration):.4f}",
                     "-i", str(claim)]
            vchain.append(f"[{extra_index}:v]scale={w}:{h}:force_original_aspect_ratio="
                          f"decrease,setsar=1[claim]")
            vchain.append(f"{cur}[claim]overlay=x=(W-w)/2:y=(H-h)/2"
                          f":enable='lt(t,{min(s.claim_dur, self.job.duration):.4f})'[v1]")
            cur = "[v1]"
            extra_index += 1
        if logo and Path(logo).is_file():
            # PHẢI giới hạn -t: input "-loop 1" không bao giờ báo hết dữ liệu,
            # thiếu -t là ffmpeg treo vĩnh viễn ở bước trộn cuối.
            args += ["-loop", "1", "-t", f"{self.job.duration:.4f}", "-i", str(logo)]
            size = probe_size(self.ffprobe, Path(logo)) or (w, h)
            fit = min(w / max(1, size[0]), h / max(1, size[1]))
            lw = _even(max(8.0, size[0] * fit * float(s.logo_scale)))
            x, y = overlay_position(s.logo_x, s.logo_y, w, h)
            vchain.append(f"[{extra_index}:v]scale={lw}:-2,setsar=1[logo]")
            vchain.append(f"{cur}[logo]overlay=x={x}:y={y}:shortest=1[v2]")
            cur = "[v2]"
            extra_index += 1
        if (self.job.srt_path and s.render_burn_subs and s.enable_subtitles
                and Path(self.job.srt_path).is_file()):
            vchain.append(f"{cur}subtitles=filename='{ass_escape(Path(self.job.srt_path))}'"
                          f":force_style='{subtitle_force_style(s, h)}'[vsub]")
            cur = "[vsub]"
        vchain.append(f"{cur}format=yuv420p[vout]")
        chain = ";".join(vchain)
        amap = "0:a?"
        if tracks:
            ins = "".join(f"[{i + 1}:a]" for i in range(len(tracks)))
            chain += ";" + ins + (f"amix=inputs={len(tracks)}:duration=longest:normalize=0"
                                  f",alimiter=limit=0.97[aout]"
                                  if len(tracks) > 1 else "anull[aout]")
            amap = "[aout]"
        return args + ["-filter_complex", chain, "-map", "[vout]", "-map", amap,
                       "-c:v", self.encoder,
                       *quality_args(self.encoder, s.render_crf, s.render_preset),
                       "-c:a", "aac", "-b:a", f"{s.render_audio_kbps}k",
                       "-movflags", "+faststart",
                       "-t", f"{self.job.duration:.4f}", str(out)]

    # -- điều phối -------------------------------------------------------- #
    def run(self) -> Path:
        job = self.job
        self._t0 = time.time()
        job.status = "running"
        job.out_path.parent.mkdir(parents=True, exist_ok=True)
        self.work.mkdir(parents=True, exist_ok=True)
        self.log(f"[RENDER] {job.name}: {self.w}x{self.h} @{self.fps}fps, "
                 f"{len(job.plan)} cảnh, {job.duration / 60:.1f} phút, encoder {self.encoder}")
        try:
            segs = self._render_scenes()
            video = self._concat(segs)
            tracks = [t for t in (self._build_voice(), self._build_source_audio(),
                                  self._build_bgm(), self._build_sfx()) if t]
            self._finish_phase("audio")
            self.log(f"[RENDER] Đang trộn {len(tracks)} đường tiếng và ghi file cuối…")
            self._ffmpeg(self.final_args(video, tracks, job.out_path),
                         job.duration, "final")
            self._finish_phase("final")
        except Cancelled:
            job.status = "cancelled"
            self._kill()
            raise
        finally:
            shutil.rmtree(self.work, ignore_errors=True)
        job.status = "done"
        job.percent = 100.0
        job.eta_sec = 0.0
        self.log(f"[SUCCESS] Render xong sau {self._fmt(time.time() - self._t0)}: {job.out_path}")
        return job.out_path

    @staticmethod
    def _fmt(sec: float) -> str:
        sec = int(max(0, sec))
        h, rest = divmod(sec, 3600)
        m, s = divmod(rest, 60)
        return f"{h}h{m:02d}m" if h else f"{m}:{s:02d}"


def fmt_eta(sec: float) -> str:
    """Thời gian còn lại dạng người đọc được."""
    sec = int(max(0, round(sec)))
    if sec <= 0:
        return "—"
    h, rest = divmod(sec, 3600)
    m, s = divmod(rest, 60)
    if h:
        return f"{h} giờ {m:02d} phút"
    if m:
        return f"{m} phút {s:02d} giây"
    return f"{s} giây"
