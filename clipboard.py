"""
Чтение ссылки из буфера обмена Windows.
Возвращает None, если в буфере не YouTube-ссылка.
"""
from __future__ import annotations

import re
import sys

from logging_setup import log

IS_WINDOWS = sys.platform.startswith("win")

# Паттерны ссылок
YT_PATTERNS = [
    re.compile(r"^https?://(www\.)?youtube\.com/watch\?.*v=[\w-]+", re.I),
    re.compile(r"^https?://youtu\.be/[\w-]+", re.I),
    re.compile(r"^https?://(www\.)?youtube\.com/live/[\w-]+", re.I),
    re.compile(r"^https?://(www\.)?youtube\.com/playlist\?.*list=[\w-]+", re.I),
    re.compile(r"^https?://music\.youtube\.com/[\w-]+", re.I),
    re.compile(r"^https?://(www\.)?youtube\.com/shorts/[\w-]+", re.I),
]

def _read_clipboard_win() -> str:
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL

        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL

        if not user32.OpenClipboard(None):
            return ""

        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return ""
            try:
                text = ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
            return text or ""
        finally:
            user32.CloseClipboard()
    except Exception:
        log.exception("Ошибка чтения буфера")
        return ""

def read_clipboard() -> str:
    if not IS_WINDOWS:
        return ""
    return _read_clipboard_win().strip()

def is_youtube_url(text: str) -> bool:
    if not text:
        return False
    text = text.strip()
    return any(p.match(text) for p in YT_PATTERNS)

def get_youtube_from_clipboard() -> str | None:
    text = read_clipboard()
    if not text:
        return None
    # берём первую строку — вдруг в буфере многострочный текст
    first_line = text.splitlines()[0].strip()
    if is_youtube_url(first_line):
        return first_line
    return None