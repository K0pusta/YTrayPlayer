from __future__ import annotations

import queue
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

# --- очередь уведомлений + один воркер ---------------------------------------

_queue: "queue.Queue[Optional[tuple[str, str]]]" = queue.Queue()
_worker_started = False
_worker_lock = threading.Lock()

def _icon_path() -> Optional[str]:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent
    p = base / "assets" / "icon.ico"
    return str(p) if p.exists() else None

def _worker_loop() -> None:
    log.info("notify: воркер тостов запущен")
    while True:
        item = _queue.get()
        if item is None:
            log.info("notify: воркер тостов завершён")
            return
        title, message = item
        try:
            kwargs = {
                "title": title,
                "body": message,
                "duration": "short",
            }
            icon = _icon_path()
            if icon:
                kwargs["icon"] = icon
            _toast(**kwargs)
        except Exception:
            log.exception("Ошибка показа уведомления")

def _ensure_worker() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        threading.Thread(target=_worker_loop, name="toast-worker", daemon=True).start()
        _worker_started = True


def _show(title: str, message: str) -> None:
    if not config.get("notifications", True):
        return
    if _toast is None:
        log.debug("win11toast недоступен, пропуск: %s / %s", title, message)
        return

    _ensure_worker()
    _queue.put((title, message))

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