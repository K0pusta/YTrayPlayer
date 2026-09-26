from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Optional

from config import DATA_DIR
from logging_setup import log
from youtube import Track

RESUME_PATH = DATA_DIR / "resume.json"

class Resume:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: Optional[dict] = None
        self.load()

    # -------------------------------------------------------------- storage

    def load(self) -> None:
        if RESUME_PATH.exists():
            try:
                with open(RESUME_PATH, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                log.exception("Не удалось прочитать resume.json")
                self._data = None
        else:
            self._data = None

    def save(self) -> None:
        if self._data is None:
            return
        try:
            RESUME_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(RESUME_PATH, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            log.exception("Не удалось сохранить resume.json")

    # -------------------------------------------------------------- public

    def set_track(self, track: Track) -> None:
        if not track or not track.url:
            return
        with self._lock:
            self._data = {
                "url": track.url,
                "title": track.title or "Unknown",
                "is_live": bool(track.is_live),
                "saved_at": datetime.now().isoformat(timespec="seconds"),
            }
            self.save()
        log.debug("resume сохранён: %s", track.title[:40])

    def get_track(self) -> Optional[Track]:
        with self._lock:
            if not self._data:
                return None
            url = self._data.get("url")
            if not url:
                return None
            return Track(
                url=url,
                title=self._data.get("title", "Unknown"),
                is_live=bool(self._data.get("is_live", False)),
            )

    def clear(self) -> None:
        with self._lock:
            self._data = None
            try:
                if RESUME_PATH.exists():
                    RESUME_PATH.unlink()
            except Exception:
                pass