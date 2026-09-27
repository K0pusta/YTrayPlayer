from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes
from typing import Callable, Optional

from config import config
from logging_setup import log

IS_WINDOWS = sys.platform.startswith("win")

# --- WinAPI константы --------------------------------------------------------

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

# ID хоткеев
HOTKEY_IDS = {
    "play_pause": 1,
    "next": 2,
    "prev": 3,
    "vol_up": 4,
    "vol_down": 5,
    "favorite": 6,
    "play_clip": 7,
    "toggle_shuffle": 8,
}

# --- Обёртка WinAPI ----------------------------------------------------------

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

_VK_NAMES = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x1B: "Esc",
    0x20: "Space",
    0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    0x2D: "Ins", 0x2E: "Del",
    0x30: "0", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4",
    0x35: "5", 0x36: "6", 0x37: "7", 0x38: "8", 0x39: "9",
}

def _vk_name(vk: int) -> str:
    # A-Z
    if 0x41 <= vk <= 0x5A:
        return chr(vk)
    # F1-F24
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x70 + 1}"
    return _VK_NAMES.get(vk, f"0x{vk:02X}")

def vk_to_string(mods: int, key: int) -> str:
    parts = []
    if mods & MOD_CONTROL: parts.append("Ctrl")
    if mods & MOD_ALT:     parts.append("Alt")
    if mods & MOD_SHIFT:   parts.append("Shift")
    if mods & MOD_WIN:     parts.append("Win")
    parts.append(_vk_name(key))
    return "+".join(parts)

# --- Менеджер хоткеев --------------------------------------------------------

class HotkeyManager:

    def __init__(self) -> None:
        self._pending: dict[int, tuple[str, int, int, Callable[[], None]]] = {}
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._registered_ids: list[int] = []
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._thread_id: int = 0
        self._ready = threading.Event()

        self.last_registered: list[str] = []
        self.last_failed: list[tuple[str, int]] = []  # (name, error_code)

    # -------------------------------------------------------------- public

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

        if not spec.get("enabled", True):
            log.info("Хоткей %s отключён — не регистрируем", name)
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
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2.0)

    def stop(self) -> None:
        self._stop.set()
        if IS_WINDOWS and self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2)

    def unregister_all(self) -> None:
        self._pending.clear()
        self._callbacks.clear()

    def reregister(self) -> tuple[list[str], list[tuple[str, int]]]:
        if not IS_WINDOWS:
            return [], []
        if not self._thread or not self._thread.is_alive():
            log.warning("Поток хоткеев не запущен — reregister пропущен")
            return [], []

        saved_callbacks = dict(self._callbacks)

        # Снять все
        for hk_id in self._registered_ids:
            try:
                user32.UnregisterHotKey(None, hk_id)
            except Exception:
                pass
        self._registered_ids.clear()
        self._callbacks.clear()
        self._pending.clear()

        self.last_registered = []
        self.last_failed = []

        for name, hk_id in HOTKEY_IDS.items():
            spec = config.get("hotkeys", {}).get(name)
            if not spec:
                continue

            cb = saved_callbacks.get(hk_id)
            if cb is None:
                continue

            if not spec.get("enabled", True):
                log.info("Хоткей %s отключён — не регистрируем", name)
                continue

            mods = int(spec["mods"]) | MOD_NOREPEAT
            key = int(spec["key"])

            ok = user32.RegisterHotKey(None, hk_id, mods, key)
            if not ok:
                err = ctypes.get_last_error()
                log.error("reregister: RegisterHotKey(%s) err=%s", name, err)
                self.last_failed.append((name, err))
                continue

            self._registered_ids.append(hk_id)
            self._callbacks[hk_id] = cb
            self.last_registered.append(name)
            log.info("reregister: хоткей %s зарегистрирован", name)

        return self.last_registered, self.last_failed

    # -------------------------------------------------------------- internal

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        log.info("HotkeyManager: поток запущен (thread_id=%s)", self._thread_id)

        for hk_id, (name, mods, key, cb) in self._pending.items():
            ok = user32.RegisterHotKey(None, hk_id, mods, key)
            if not ok:
                err = ctypes.get_last_error()
                log.error("RegisterHotKey(%s) провалился: err=%s", name, err)
                self.last_failed.append((name, err))
                continue
            self._registered_ids.append(hk_id)
            self._callbacks[hk_id] = cb
            self.last_registered.append(name)
            log.info("Хоткей зарегистрирован: %s (mods=0x%X, key=0x%X)", name, mods, key)

        self._ready.set()

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