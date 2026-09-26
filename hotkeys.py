from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes
from typing import Callable, Optional

from config import config
from logging_setup import log

IS_WINDOWS = sys.platform.startswith("win")

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

HOTKEY_IDS = {
    "play_pause": 1,
    "next": 2,
    "prev": 3,
    "vol_up": 4,
    "vol_down": 5,
    "favorite": 6,
    "play_clip": 7,
    "toggle_shuffle": 9,
}

if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                      wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype = wintypes.BOOL

    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL

    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG),
                                   wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = wintypes.BOOL

    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT,
                                          wintypes.WPARAM, wintypes.LPARAM]
    user32.PostThreadMessageW.restype = wintypes.BOOL

class HotkeyManager:
    def __init__(self) -> None:
        self._pending: dict[int, tuple[str, int, int, Callable[[], None]]] = {}
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._thread_id: int = 0
        self._registered_ids: list[int] = []

    def register(self, name: str, callback: Callable[[], None]) -> bool:
        if not IS_WINDOWS:
            log.warning("Хоткеи поддерживаются только на Windows")
            return False

        spec = config.get("hotkeys", {}).get(name)
        if not spec:
            log.warning("Хоткей %s не описан в config", name)
            return False

        hk_id = HOTKEY_IDS.get(name)
        if hk_id is None:
            log.warning("Неизвестный хоткей: %s", name)
            return False

        mods = int(spec["mods"]) | MOD_NOREPEAT
        key = int(spec["key"])
        self._pending[hk_id] = (name, mods, key, callback)
        return True

    def start(self) -> None:
        if not IS_WINDOWS:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="hotkeys", daemon=True)
        self._thread.start()
        for _ in range(50):
            if self._thread_id:
                break
            threading.Event().wait(0.02)

    def stop(self) -> None:
        self._stop.set()
        if IS_WINDOWS and self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2)

    def unregister_all(self) -> None:
        self._pending.clear()
        self._callbacks.clear()

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        log.info("HotkeyManager: поток запущен (thread_id=%s)", self._thread_id)

        for hk_id, (name, mods, key, cb) in self._pending.items():
            ok = user32.RegisterHotKey(None, hk_id, mods, key)
            if not ok:
                err = ctypes.get_last_error()
                log.error("RegisterHotKey(%s) провалился: err=%s (вероятно, комбинация занята)", name, err)
                continue
            self._registered_ids.append(hk_id)
            self._callbacks[hk_id] = cb
            log.info("Хоткей зарегистрирован: %s (mods=0x%X, key=0x%X)", name, mods, key)

        msg = wintypes.MSG()
        while not self._stop.is_set():
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or ret == -1:
                break
            if msg.message == WM_HOTKEY:
                hk_id = int(msg.wParam)
                cb = self._callbacks.get(hk_id)
                if cb:
                    try:
                        cb()
                    except Exception:
                        log.exception("Ошибка в колбэке хоткея id=%s", hk_id)
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        for hk_id in self._registered_ids:
            try:
                user32.UnregisterHotKey(None, hk_id)
            except Exception:
                pass
        self._registered_ids.clear()
        log.info("HotkeyManager: поток завершён")


def hotkey_to_string(mods: int, key: int) -> str:
    parts = []
    if mods & MOD_CONTROL: parts.append("Ctrl")
    if mods & MOD_ALT:     parts.append("Alt")
    if mods & MOD_SHIFT:   parts.append("Shift")
    if mods & MOD_WIN:     parts.append("Win")
    vk_names = {
        0x50: "P", 0x4D: "M", 0x46: "F", 0x56: "V", 0x30: "0",
        0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    }
    parts.append(vk_names.get(key, f"0x{key:02X}"))
    return "+".join(parts)