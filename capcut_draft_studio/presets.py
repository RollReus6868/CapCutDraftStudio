"""Quản lý nhiều preset kênh + lịch sử project gần đây.

Preset được lưu trong presets/<slug>.json cạnh tool, độc lập với
channel-settings.json (file đó vẫn nằm trong folder kênh như cũ).
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from .config import DEFAULT_CHANNEL_KEYS, load_json, save_json

# Các key thuộc về "chỗ để file", lưu kèm preset cho tiện chuyển kênh
PATH_KEYS = {
    "input_dir", "channel_dir", "capcut_drafts", "draft_name",
    "bgm_dir", "logo_path", "claim_path", "subtitle_file", "aspect",
}
PRESET_KEYS = DEFAULT_CHANNEL_KEYS | PATH_KEYS
MAX_RECENT = 12


def slugify(name: str) -> str:
    s = re.sub(r"[^\w\s.-]", "", name, flags=re.UNICODE).strip()
    s = re.sub(r"\s+", "-", s).strip("-.")
    return (s or "preset")[:60]


class PresetStore:
    """Đọc/ghi các preset kênh trong một thư mục."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

    def path_for(self, name: str) -> Path:
        return self.folder / f"{slugify(name)}.json"

    def names(self) -> list[str]:
        out = []
        for p in sorted(self.folder.glob("*.json"), key=lambda x: x.stem.lower()):
            data = load_json(p, None)
            if isinstance(data, dict):
                out.append(str(data.get("_name") or p.stem))
        return out

    def load(self, name: str) -> dict:
        data = load_json(self.path_for(name), {})
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if k in PRESET_KEYS}

    def save(self, name: str, values: dict) -> Path:
        name = name.strip()
        if not name:
            raise ValueError("Tên preset không được rỗng")
        payload = {k: v for k, v in values.items() if k in PRESET_KEYS}
        payload["_name"] = name
        payload["_saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        p = self.path_for(name)
        save_json(p, payload)
        return p

    def delete(self, name: str) -> bool:
        p = self.path_for(name)
        if p.is_file():
            p.unlink()
            return True
        return False

    def rename(self, old: str, new: str) -> bool:
        data = load_json(self.path_for(old), None)
        if not isinstance(data, dict):
            return False
        self.save(new, data)
        self.delete(old)
        return True

    def meta(self, name: str) -> dict:
        data = load_json(self.path_for(name), {})
        return data if isinstance(data, dict) else {}


class RecentStore:
    """Danh sách project mở gần đây (input_dir + tên draft)."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def items(self) -> list[dict]:
        data = load_json(self.path, [])
        if not isinstance(data, list):
            return []
        return [d for d in data if isinstance(d, dict) and d.get("input_dir")]

    def add(self, input_dir: str, draft_name: str, channel_dir: str = "") -> None:
        input_dir = (input_dir or "").strip()
        if not input_dir:
            return
        items = [d for d in self.items()
                 if str(d.get("input_dir", "")).lower() != input_dir.lower()]
        items.insert(0, {
            "input_dir": input_dir,
            "draft_name": draft_name,
            "channel_dir": channel_dir,
            "at": time.strftime("%Y-%m-%d %H:%M"),
        })
        save_json(self.path, items[:MAX_RECENT])

    def clear(self) -> None:
        save_json(self.path, [])
