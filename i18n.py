from __future__ import annotations

import json
import sys
from pathlib import Path

from config import config
from logging_setup import log

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


_LOCALES_DIR = _base_dir() / "locales"

_FALLBACK = {
    "ru": {
        "play_pause": "Play / Pause",
        "next": "Следующий",
        "prev": "Предыдущий",
        "play_clipboard": "Играть из буфера",
        "input_url": "Ввести ссылку…",
        "add_favorite": "Добавить в избранное",
        "favorites": "Избранное",
        "save_playlist": "Сохранить текущий плейлист…",
        "playlists": "Плейлисты",
        "notifications": "Уведомления",
        "hotkeys": "Хоткеи",
        "language": "Язык",
        "lang_ru": "Русский",
        "lang_en": "English",
        "update_ytdlp": "Обновить yt-dlp",
        "quit": "Выход",
        "empty": "(пусто)",
        "error": "(ошибка)",
        "play": "Играть",
        "remove_from_favorites": "Удалить из избранного",
        "remove_from_playlists": "Удалить из плейлистов",
        "notify_updated": "yt-dlp обновлён",
        "notify_update_failed": "Ошибка обновления yt-dlp",
    },
    "en": {
        "play_pause": "Play / Pause",
        "next": "Next",
        "prev": "Previous",
        "play_clipboard": "Play from clipboard",
        "input_url": "Enter URL…",
        "add_favorite": "Add to favorites",
        "favorites": "Favorites",
        "save_playlist": "Save current playlist…",
        "playlists": "Playlists",
        "notifications": "Notifications",
        "hotkeys": "Hotkeys",
        "language": "Language",
        "lang_ru": "Русский",
        "lang_en": "English",
        "update_ytdlp": "Update yt-dlp",
        "quit": "Quit",
        "empty": "(empty)",
        "error": "(error)",
        "play": "Play",
        "remove_from_favorites": "Remove from favorites",
        "remove_from_playlists": "Remove from playlists",
        "notify_updated": "yt-dlp updated",
        "notify_update_failed": "yt-dlp update failed",
    },
}

class I18n:
    def __init__(self) -> None:
        self._strings: dict[str, str] = {}
        self.load()

    def load(self) -> None:
        lang = str(config.get("language", "ru")).lower()
        if lang not in ("ru", "en"):
            lang = "ru"

        self._strings = dict(_FALLBACK.get(lang, _FALLBACK["ru"]))

        path = _LOCALES_DIR / f"{lang}.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._strings.update({k: str(v) for k, v in data.items()})
                log.info("Локализация загружена: %s (%s)", lang, path)
            except Exception:
                log.exception("Не удалось прочитать %s", path)

    def t(self, key: str, default: str = "") -> str:
        return self._strings.get(key, default or key)

    def set_language(self, lang: str) -> None:
        lang = lang.lower()
        if lang not in ("ru", "en"):
            return
        config.set("language", lang)
        self.load()
        log.info("Язык переключён: %s", lang)

i18n = I18n()

def t(key: str, default: str = "") -> str:
    return i18n.t(key, default)