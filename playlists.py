from __future__ import annotations

import json
import re
import threading
from datetime import datetime

from config import PLAYLISTS_PATH
from logging_setup import log

# Паттерны: ссылка на плейлист YouTube
PLAYLIST_PATTERNS = [
    re.compile(r"^https?://(www\.)?youtube\.com/playlist\?.*list=[\w-]+", re.I),
    re.compile(r"^https?://(www\.)?youtube\.com/watch\?.*list=[\w-]+", re.I),
    re.compile(r"^https?://music\.youtube\.com/playlist\?.*list=[\w-]+", re.I),
]


def is_playlist_url(url: str) -> bool:
    if not url:
        return False
    return any(p.match(url.strip()) for p in PLAYLIST_PATTERNS)

class Playlists:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: list[dict] = []
        self.load()

    # -------------------------------------------------------------- public

    def load(self) -> None:
        if PLAYLISTS_PATH.exists():
            try:
                with open(PLAYLISTS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._items = data.get("items", []) or []
            except Exception:
                log.exception("Не удалось прочитать playlists.json")
                self._items = []
        else:
            self._items = []

    def save(self) -> None:
        PLAYLISTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(PLAYLISTS_PATH, "w", encoding="utf-8") as f:
            json.dump({"items": self._items}, f, ensure_ascii=False, indent=2)

    def all(self) -> list[dict]:
        with self._lock:
            return list(self._items)

    def add(self, name: str, url: str) -> bool:
        name = (name or "").strip()
        url = (url or "").strip()
        if not name or not url:
            return False

        with self._lock:
            for it in self._items:
                if it.get("url") == url:
                    log.info("Плейлист с таким URL уже сохранён: %s", url)
                    return False

            item = {
                "name": name,
                "url": url,
                "added": datetime.now().isoformat(timespec="seconds"),
            }
            self._items.append(item)
            self.save()
            log.info("Плейлист сохранён: %s → %s", name, url)
            return True

    def remove_by_url(self, url: str) -> bool:
        with self._lock:
            before = len(self._items)
            self._items = [it for it in self._items if it.get("url") != url]
            if len(self._items) != before:
                self.save()
                return True
        return False

    def get_by_url(self, url: str) -> dict | None:
        with self._lock:
            for it in self._items:
                if it.get("url") == url:
                    return dict(it)
        return None