from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

APP_NAME = "YTrayPlayer"
_log = logging.getLogger(__name__)

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
    "start_url": "",
    "radio_url": "https://www.youtube.com/live/rFZHOHl-L8A",
    "volume": 100,
    "language": "ru",
    "notifications": True,
    "hotkeys_enabled": True,
    "shuffle_queue": False,
    "favorites_shuffle": False,
    "discord_rpc": False,
    "discord_app_id": "",
    "hotkeys": {
        "play_pause":     {"mods": 0x0003, "key": 0x50},
        "next":           {"mods": 0x0003, "key": 0x27},
        "prev":           {"mods": 0x0003, "key": 0x25},
        "vol_up":         {"mods": 0x0003, "key": 0x26},
        "vol_down":       {"mods": 0x0003, "key": 0x28},
        "mute":           {"mods": 0x0003, "key": 0x4D},
        "favorite":       {"mods": 0x0003, "key": 0x46},
        "play_clip":      {"mods": 0x0003, "key": 0x56},
        "toggle_shuffle": {"mods": 0x0003, "key": 0x53},
    },
    "mpv_path": "bin/mpv/mpv.exe",
    "ytdlp_path": "bin/yt-dlp.exe",
    "log_level": "INFO",
}

HOTKEY_DESCRIPTIONS: dict[str, str] = {
    "play_pause":     "Play / Pause",
    "next":           "Следующий трек",
    "prev":           "Предыдущий трек",
    "vol_up":         "Громкость +5",
    "vol_down":       "Громкость −5",
    "mute":           "Mute (вкл/выкл звук)",
    "favorite":       "Добавить в избранное",
    "play_clip":      "Играть ссылку из буфера",
    "toggle_shuffle": "Вкл/выкл Shuffle очереди",
}


class Config:

    SAVE_INTERVAL_SEC = 2.0

    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self._path_str = str(path)
        self._data: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._dirty = threading.Event()
        self._shutdown = threading.Event()
        self._writer_thread: Optional[threading.Thread] = None
        self.load()
        self._start_writer()

    # -------------------------------------------------------------- load

    def load(self) -> None:
        if self.path.exists():
            try:
                with open(self._path_str, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self._data = _merge(DEFAULTS, loaded)
            except Exception:
                _log.exception("Не удалось прочитать %s — беру дефолты", self._path_str)
                self._data = dict(DEFAULTS)
        else:
            self._data = dict(DEFAULTS)
            self.save_now()

    # -------------------------------------------------------------- writer

    def _start_writer(self) -> None:
        def loop():
            _log.debug("config: поток-писатель запущен")
            while not self._shutdown.is_set():
                # ждём либо 2 секунды, либо сигнала shutdown
                self._shutdown.wait(timeout=self.SAVE_INTERVAL_SEC)
                if self._dirty.is_set():
                    self.save_now()
            _log.debug("config: поток-писатель завершён")

        self._writer_thread = threading.Thread(
            target=loop, name="config-writer", daemon=True
        )
        self._writer_thread.start()

    def shutdown(self) -> None:
        self._shutdown.set()
        if self._dirty.is_set():
            self.save_now()

    # -------------------------------------------------------------- save

    def save_now(self) -> None:
        with self._lock:
            try:
                data = json.dumps(self._data, ensure_ascii=False, indent=2)
                with open(self._path_str, "w", encoding="utf-8") as f:
                    f.write(data)
                self._dirty.clear()
            except Exception:
                _log.exception("Не удалось сохранить %s", self._path_str)

    def save(self) -> None:
        self._dirty.set()

    # -------------------------------------------------------------- access

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if key in self._data:
                return self._data[key]
            if default is not None:
                return default
            return DEFAULTS.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
        self.save()

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

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