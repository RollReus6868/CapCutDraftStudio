"""Điểm vào của tool — giữ nguyên `python -m capcut_draft_studio.app`."""
from __future__ import annotations

from .ui.app import App, main  # noqa: F401  (re-export cho tương thích ngược)

if __name__ == "__main__":
    main()
