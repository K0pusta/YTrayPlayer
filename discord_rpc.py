from __future__ import annotations

import threading
import time
from typing import Optional

from config import config
from logging_setup import log

try:
    from pypresence import Presence
    from pypresence.exceptions import DiscordNotFound, InvalidID, PipeClosed
    HAS_PYPRESENCE = True
except ImportError:
    HAS_PYPRESENCE = False
    Presence = None  # type: ignore
    DiscordNotFound = Exception  # type: ignore
    InvalidID = Exception  # type: ignore
    PipeClosed = Exception  # type: ignore

class DiscordRPC:
    def __init__(self) -> None:
        self._rpc: Optional["Presence"] = None
        self._connected = False
        self._lock = threading.Lock()
        self._app_id: str = str(config.get("discord_app_id", "") or "")
        self._enabled: bool = bool(config.get("discord_rpc", True))

        self._current_title: str = ""
        self._current_uploader: str = ""
        self._current_is_live: bool = False

        if not HAS_PYPRESENCE:
            log.info("pypresence не установлен — Discord RPC отключён")
            return

        if not self._app_id:
            log.info("discord_app_id не задан — Discord RPC отключён")
            return

        if not self._enabled:
            log.info("Discord RPC выключен в конфиге")
            return

        self._try_connect()

    # -------------------------------------------------------------- подключение

    def _try_connect(self) -> None:
        if not HAS_PYPRESENCE or not self._app_id:
            return
        try:
            self._rpc = Presence(self._app_id)
            self._rpc.connect()
            self._connected = True
            log.info("Discord RPC подключён (app_id=%s)", self._app_id)
        except Exception as e:
            self._connected = False
            self._rpc = None
            log.info("Discord RPC не подключился: %s", e)

    def _ensure_connected(self) -> bool:
        if not self._enabled or not HAS_PYPRESENCE or not self._app_id:
            return False
        if self._connected and self._rpc is not None:
            return True
        # Попробовать переподключиться
        self._try_connect()
        return self._connected

    # -------------------------------------------------------------- API

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        config.set("discord_rpc", self._enabled)
        log.info("Discord RPC: %s", "вкл" if self._enabled else "выкл")

        if not self._enabled:
            self.clear()
            return

        if self._ensure_connected() and self._current_title:
            self._update_presence()

    def is_enabled(self) -> bool:
        return self._enabled

    def is_connected(self) -> bool:
        return self._connected

    def update_track(self, title: str, uploader: str = "", is_live: bool = False) -> None:
        self._current_title = title or ""
        self._current_uploader = uploader or ""
        self._current_is_live = bool(is_live)
        self._update_presence()

    def clear(self) -> None:
        if not self._connected or self._rpc is None:
            return
        try:
            self._rpc.clear()
            log.debug("Discord RPC: cleared")
        except Exception as e:
            log.debug("Discord RPC clear error: %s", e)
            self._connected = False

    def shutdown(self) -> None:
        try:
            if self._rpc and self._connected:
                self._rpc.clear()
                self._rpc.close()
        except Exception:
            pass
        self._connected = False
        self._rpc = None

    # -------------------------------------------------------------- внутреннее

    def _update_presence(self) -> None:
        if not self._enabled:
            return
        if not self._ensure_connected() or self._rpc is None:
            return
        if not self._current_title:
            return

        title = self._current_title[:128]
        state = self._current_uploader[:128] if self._current_uploader else ""

        details_prefix = "🔴 Live: " if self._current_is_live else ""
        details = (details_prefix + title)[:128]

        start_ts = int(time.time())

        try:
            with self._lock:
                self._rpc.update(
                    details=details,
                    state=state or "YTrayPlayer",
                    start=start_ts,
                    large_image="ytray_logo" if self._has_large_asset() else None,
                    large_text="YTrayPlayer",
                    small_image=None,
                    small_text=None,
                )
            log.debug("Discord RPC обновлён: %s", details)
        except Exception as e:
            log.debug("Discord RPC update error: %s", e)
            self._connected = False

    def _has_large_asset(self) -> bool:
        return False