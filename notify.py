from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Optional

from config import config
from logging_setup import log

IS_WINDOWS = sys.platform.startswith("win")

try:
    if IS_WINDOWS:
        from win11toast import toast as _toast  # type: ignore
    else:
        _toast = None
except Exception:
    log.exception("win11toast недоступен")
    _toast = None

def _icon_path() -> Optional[str]:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent
    p = base / "assets" / "icon.ico"
    return str(p) if p.exists() else None

def _show(title: str, message: str) -> None:
    if not config.get("notifications", True):
        log.debug("Уведомления отключены, пропуск: %s / %s", title, message)
        return
    if _toast is None:
        log.debug("win11toast недоступен, пропуск: %s / %s", title, message)
        return

    icon = _icon_path()

    def worker():
        try:
            kwargs = {
                "title": title,
                "body": message,
                "duration": "short",
            }
            if icon:
                kwargs["icon"] = icon
            _toast(**kwargs)
        except Exception:
            log.exception("Ошибка показа уведомления")

    threading.Thread(target=worker, name="toast", daemon=True).start()

# ---------------------------------------------------------------- публичные

def notify_track(title: str, is_live: bool) -> None:
    tag = "LIVE" if is_live else "VOD"
    _show(f"▶ Сейчас играет [{tag}]", title or "Unknown")

def notify_error(message: str) -> None:
    _show("⚠ Ошибка", message)

def notify_info(message: str) -> None:
    _show("YTray Player", message)

def set_enabled(enabled: bool) -> None:
    config.set("notifications", bool(enabled))
    log.info("Уведомления: %s", "вкл" if enabled else "выкл")

def is_enabled() -> bool:
    return bool(config.get("notifications", True))