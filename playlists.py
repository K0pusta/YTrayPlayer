from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from typing import Optional

from config import PLAYLISTS_PATH
from logging_setup import log
from youtube import Track

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

    # -------------------------------------------------------------- storage

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

    # -------------------------------------------------------------- общее

    def all(self) -> list[dict]:
        with self._lock:
            return list(self._items)

    def get(self, name: str) -> Optional[dict]:
        with self._lock:
            for it in self._items:
                if it.get("name") == name:
                    return dict(it)
        return None

    def remove_by_name(self, name: str) -> bool:
        with self._lock:
            before = len(self._items)
            self._items = [it for it in self._items if it.get("name") != name]
            if len(self._items) != before:
                self.save()
                return True
        return False

    def remove_by_url(self, url: str) -> bool:
        with self._lock:
            before = len(self._items)
            self._items = [
                it for it in self._items
                if not (it.get("type") == "youtube" and it.get("url") == url)
            ]
            if len(self._items) != before:
                self.save()
                return True
        return False

    # -------------------------------------------------------------- youtube

    def add_youtube(self, name: str, url: str) -> bool:
        name = (name or "").strip()
        url = (url or "").strip()
        if not name or not url:
            return False

        with self._lock:
            for it in self._items:
                if it.get("type") == "youtube" and it.get("url") == url:
                    log.info("YouTube-плейлист уже сохранён: %s", url)
                    return False
                if it.get("name") == name:
                    log.info("Имя плейлиста занято: %s", name)
                    return False

            item = {
                "name": name,
                "type": "youtube",
                "url": url,
                "added": datetime.now().isoformat(timespec="seconds"),
            }
            self._items.append(item)
            self.save()
            log.info("YouTube-плейлист сохранён: %s", name)
            return True

    # -------------------------------------------------------------- user

    def add_user(self, name: str) -> bool:
        name = (name or "").strip()
        if not name:
            return False
        with self._lock:
            for it in self._items:
                if it.get("name") == name:
                    log.info("Имя плейлиста занято: %s", name)
                    return False
            item = {
                "name": name,
                "type": "user",
                "tracks": [],
                "added": datetime.now().isoformat(timespec="seconds"),
            }
            self._items.append(item)
            self.save()
            log.info("User-плейлист создан: %s", name)
            return True

    def add_track_to_user(self, name: str, track: Track) -> bool:
        if not track or not track.url:
            return False
        with self._lock:
            for it in self._items:
                if it.get("name") == name and it.get("type") == "user":
                    for t in it.get("tracks", []):
                        if t.get("url") == track.url:
                            log.info("Трек уже в плейлисте %s", name)
                            return False
                    it.setdefault("tracks", []).append({
                        "url": track.url,
                        "title": track.title or "Unknown",
                        "is_live": bool(track.is_live),
                        "added": datetime.now().isoformat(timespec="seconds"),
                    })
                    self.save()
                    log.info("Трек добавлен в %s: %s", name, track.title)
                    return True
        return False

    def remove_track_from_user(self, name: str, url: str) -> bool:
        with self._lock:
            for it in self._items:
                if it.get("name") == name and it.get("type") == "user":
                    before = len(it.get("tracks", []))
                    it["tracks"] = [t for t in it.get("tracks", []) if t.get("url") != url]
                    if len(it["tracks"]) != before:
                        self.save()
                        return True
        return False

    def user_tracks(self, name: str) -> list[Track]:
        with self._lock:
            for it in self._items:
                if it.get("name") == name and it.get("type") == "user":
                    return [
                        Track(
                            url=t.get("url", ""),
                            title=t.get("title", "Unknown"),
                            is_live=bool(t.get("is_live", False)),
                        )
                        for t in it.get("tracks", [])
                        if t.get("url")
                    ]
        return []