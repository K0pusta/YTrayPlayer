from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Optional

from config import FAVORITES_PATH
from logging_setup import log
from youtube import Track

class Favorites:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: list[dict] = []
        self.load()

    def load(self) -> None:
        if FAVORITES_PATH.exists():
            try:
                with open(FAVORITES_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._items = data.get("items", []) or []
            except Exception:
                log.exception("Не удалось прочитать favorites.json")
                self._items = []
        else:
            self._items = []

    def save(self) -> None:
        FAVORITES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(FAVORITES_PATH, "w", encoding="utf-8") as f:
            json.dump({"items": self._items}, f, ensure_ascii=False, indent=2)

    def all(self) -> list[dict]:
        with self._lock:
            return list(self._items)

    def all_tracks(self) -> list[Track]:
        with self._lock:
            return [
                Track(
                    url=it.get("url", ""),
                    title=it.get("title", "Unknown"),
                    is_live=bool(it.get("is_live", False)),
                )
                for it in self._items
                if it.get("url")
            ]

    def add_track(self, track: Track) -> bool:
        if not track or not track.url:
            return False

        with self._lock:
            for it in self._items:
                if it.get("url") == track.url:
                    log.info("Уже в избранном: %s", track.title)
                    return False

            item = {
                "url": track.url,
                "title": track.title or "Unknown",
                "is_live": bool(track.is_live),
                "added": datetime.now().isoformat(timespec="seconds"),
            }
            self._items.append(item)
            self.save()
            log.info("Добавлено в избранное: %s", item["title"])
            return True

    def remove_by_url(self, url: str) -> bool:
        with self._lock:
            before = len(self._items)
            self._items = [it for it in self._items if it.get("url") != url]
            if len(self._items) != before:
                self.save()
                return True
        return False

    def is_favorite(self, url: str) -> bool:
        with self._lock:
            return any(it.get("url") == url for it in self._items)