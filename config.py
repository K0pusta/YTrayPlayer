from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

APP_NAME = "YTrayPlayer"

def _appdata_dir() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
    else:
        exe_dir = Path(__file__).parent

    if (exe_dir / "portable.flag").exists():
        return exe_dir / "data"

    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / APP_NAME

DATA_DIR = _appdata_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_PATH = DATA_DIR / "config.json"
FAVORITES_PATH = DATA_DIR / "favorites.json"
PLAYLISTS_PATH = DATA_DIR / "playlists.json"
LOGS_DIR = DATA_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

DEFAULTS: dict[str, Any] = {
    # Что играет при старте. Пусто = ничего не играет, ждём команды пользователя.
    "start_url": "",

    # Радио-режим: играет, когда очередь пуста
    "radio_url": "https://www.youtube.com/live/rFZHOHl-L8A",

    # Громкость mpv (0–150)
    "volume": 100,

    # Язык: "ru" | "en"
    "language": "ru",

    # Уведомления вкл/выкл
    "notifications": True,

    # Хоткеи вкл/выкл
    "hotkeys_enabled": True,

    # Shuffle очереди
    "shuffle_queue": False,

    # Настраиваемые хоткеи (формат pywin32)
    "hotkeys": {
        "play_pause":       {"mods": 0x0003, "key": 0x50},   # Ctrl+Alt+P
        "next":             {"mods": 0x0003, "key": 0x27},   # Ctrl+Alt+Right
        "prev":             {"mods": 0x0003, "key": 0x25},   # Ctrl+Alt+Left
        "vol_up":           {"mods": 0x0003, "key": 0x26},   # Ctrl+Alt+Up
        "vol_down":         {"mods": 0x0003, "key": 0x28},   # Ctrl+Alt+Down
        "mute":             {"mods": 0x0003, "key": 0x4D},   # Ctrl+Alt+M
        "favorite":         {"mods": 0x0003, "key": 0x46},   # Ctrl+Alt+F
        "play_clip":        {"mods": 0x0003, "key": 0x56},   # Ctrl+Alt+V
        "add_to_playlist":  {"mods": 0x0003, "key": 0x41},   # Ctrl+Alt+A
        "toggle_shuffle":   {"mods": 0x0003, "key": 0x53},   # Ctrl+Alt+S
    },

    # Пути к бинарникам (относительно папки exe/проекта)
    "mpv_path": "bin/mpv/mpv.exe",
    "ytdlp_path": "bin/yt-dlp.exe",

    # Логи
    "log_level": "INFO",
}

class Config:
    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self._data: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self._data = _merge(DEFAULTS, loaded)
            except Exception:
                self._data = dict(DEFAULTS)
        else:
            self._data = dict(DEFAULTS)
            self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default if default is not None else DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out

config = Config()