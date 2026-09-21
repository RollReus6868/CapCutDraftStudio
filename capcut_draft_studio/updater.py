"""Kiểm tra và tải bản cập nhật từ GitHub Releases.

Nguyên tắc an toàn: **không bao giờ** chạy file tải về nếu SHA-256 của nó không
khớp với giá trị công bố trong release (file `SHA256SUMS.txt`). Không có bảng
băm hợp lệ thì coi như không có bản cập nhật.

Repo được cấu hình ở `REPO` bên dưới, hoặc ghi đè bằng biến môi trường
`CAPCUT_DRAFT_STUDIO_REPO` (dạng "user/repo") để tiện thử nghiệm.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

#: Đổi thành repo thật của bạn sau khi tạo trên GitHub.
REPO = "RollReus6868/CapCutDraftStudio"
API = "https://api.github.com/repos/{repo}/releases/latest"
USER_AGENT = "CapCut-Draft-Studio"
SUMS_ASSET = "SHA256SUMS.txt"
TIMEOUT = 15


def repo_slug() -> str:
    return (os.environ.get("CAPCUT_DRAFT_STUDIO_REPO") or REPO).strip().strip("/")


def releases_url() -> str:
    return f"https://github.com/{repo_slug()}/releases"


# --------------------------------------------------------------------------- #
# so sánh phiên bản
# --------------------------------------------------------------------------- #


def parse_version(raw: str) -> tuple[int, ...]:
    """'v0.4.1' -> (0, 4, 1). Phần không phải số bị bỏ qua."""
    nums = re.findall(r"\d+", str(raw or ""))
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(candidate: str, current: str) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    size = max(len(a), len(b))
    a += (0,) * (size - len(a))
    b += (0,) * (size - len(b))
    return a > b


# --------------------------------------------------------------------------- #
# tải & xác thực
# --------------------------------------------------------------------------- #


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_package(path: Path, expected_sha256: str) -> bool:
    expected = (expected_sha256 or "").strip().lower()
    return len(expected) == 64 and sha256_file(path).lower() == expected


def _open(url: str, timeout: int = TIMEOUT):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_manifest(url: str, timeout: int = TIMEOUT) -> dict:
    with _open(url, timeout) as r:
        return json.load(r)


def parse_sums(text: str) -> dict[str, str]:
    """Đọc file kiểu `sha256  tên-file` (định dạng chuẩn của sha256sum)."""
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        m = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", line.strip())
        if m:
            out[Path(m.group(2)).name] = m.group(1).lower()
    return out


def asset_pattern() -> re.Pattern:
    """File cài đặt hợp lệ cho hệ điều hành đang chạy."""
    if os.name == "nt":
        return re.compile(r"windows.*setup.*\.exe$|\.exe$", re.I)
    if sys.platform == "darwin":
        return re.compile(r"\.dmg$", re.I)
    return re.compile(r"\.tar\.gz$|\.zip$", re.I)


@dataclass
class UpdateInfo:
    version: str
    name: str
    notes: str
    url: str
    sha256: str
    size: int
    page: str

    @property
    def size_mb(self) -> float:
        return self.size / 1_000_000.0


def check(current_version: str, timeout: int = TIMEOUT) -> UpdateInfo | None:
    """Trả về bản mới nếu có, None nếu đã mới nhất / không mạng / thiếu SHA-256."""
    try:
        data = fetch_manifest(API.format(repo=repo_slug()), timeout)
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("draft"):
        return None
    tag = str(data.get("tag_name") or data.get("name") or "")
    if not tag or not is_newer(tag, current_version):
        return None
    assets = [a for a in (data.get("assets") or []) if isinstance(a, dict)]
    sums: dict[str, str] = {}
    for a in assets:
        if str(a.get("name", "")).lower() == SUMS_ASSET.lower():
            try:
                with _open(str(a.get("browser_download_url")), timeout) as r:
                    sums = parse_sums(r.read().decode("utf-8", "replace"))
            except (urllib.error.URLError, OSError):
                return None
            break
    if not sums:
        return None      # không có bảng băm -> từ chối cập nhật
    pattern = asset_pattern()
    for a in assets:
        name = str(a.get("name") or "")
        if name.lower() == SUMS_ASSET.lower() or not pattern.search(name):
            continue
        digest = sums.get(name)
        if not digest:
            continue
        return UpdateInfo(
            version=tag.lstrip("vV"), name=name,
            notes=str(data.get("body") or "").strip(),
            url=str(a.get("browser_download_url") or ""),
            sha256=digest, size=int(a.get("size") or 0),
            page=str(data.get("html_url") or releases_url()),
        )
    return None


def download(info: UpdateInfo, dest_dir: Path, progress=None, cancel=None,
             timeout: int = 60) -> Path:
    """Tải file cài đặt và BẮT BUỘC khớp SHA-256 mới trả về."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / info.name
    tmp = target.with_suffix(target.suffix + ".part")
    done = 0
    with _open(info.url, timeout) as r, tmp.open("wb") as f:
        total = int(r.headers.get("Content-Length") or info.size or 0)
        while True:
            if cancel and cancel():
                tmp.unlink(missing_ok=True)
                raise RuntimeError("Đã huỷ tải bản cập nhật")
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(100.0 * done / total)
    if not verify_package(tmp, info.sha256):
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            "File tải về KHÔNG khớp mã kiểm tra SHA-256 của bản phát hành.\n"
            "Tool đã xoá file để an toàn. Hãy thử lại, hoặc tải thủ công tại:\n"
            f"{info.page}")
    tmp.replace(target)
    return target


def launch_installer(path: Path) -> None:
    """Mở bộ cài vừa tải; app nên tự thoát ngay sau đó."""
    path = Path(path)
    if os.name == "nt":
        os.startfile(str(path))          # noqa: S606 - đã xác thực SHA-256
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
