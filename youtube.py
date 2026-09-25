from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

from config import config
from logging_setup import log

IS_WINDOWS = sys.platform.startswith("win")

# --- VIDEO_ID ----------------------------------------------------------------

_VIDEO_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|/live/|/shorts/|/embed/)([A-Za-z0-9_-]{11})"
)


def extract_video_id(url: str) -> Optional[str]:
    if not url:
        return None
    m = _VIDEO_ID_RE.search(url)
    return m.group(1) if m else None


def make_mix_url(video_url: str) -> Optional[str]:
    vid = extract_video_id(video_url)
    if not vid:
        return None
    return f"https://www.youtube.com/watch?v={vid}&list=RD{vid}"


# --- утилиты -----------------------------------------------------------------

def _resolve_bin(rel_path: str) -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent
    p = Path(rel_path)
    return p if p.is_absolute() else base / p

def _run_ytdlp(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    exe = _resolve_bin(config.get("ytdlp_path", "bin/yt-dlp.exe"))
    if not exe.exists():
        raise FileNotFoundError(f"yt-dlp не найден: {exe}")
    cmd = [str(exe), *args]
    log.debug("yt-dlp: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
    )

# --- Track -------------------------------------------------------------------

class Track:
    __slots__ = ("url", "title", "is_live", "stream_url", "duration", "kind")

    def __init__(self, url: str, title: str = "", is_live: bool = False,
                 stream_url: str = "", duration: Optional[float] = None,
                 kind: str = "video"):
        self.url = url
        self.title = title
        self.is_live = is_live
        self.stream_url = stream_url
        self.duration = duration
        self.kind = kind

    def __repr__(self) -> str:
        tag = "LIVE" if self.is_live else "VOD"
        return f"<Track {tag} {self.title[:40]!r}>"


# --- резолв ------------------------------------------------------------------

def resolve(url: str) -> Track:
    args = [
        "--dump-single-json",
        "--no-warnings",
        "--no-playlist",
        "--format", "bestaudio/best",
        "--no-cache-dir",
        url,
    ]
    try:
        p = _run_ytdlp(args)
    except subprocess.TimeoutExpired:
        raise RuntimeError("yt-dlp timeout")

    if p.returncode != 0:
        err = (p.stderr or "").strip().splitlines()
        msg = err[-1] if err else f"yt-dlp exit {p.returncode}"
        raise RuntimeError(msg)

    try:
        info = json.loads(p.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"yt-dlp вернул не JSON: {e}")

    return _info_to_track(info)


def resolve_playlist(url: str) -> list[Track]:
    args = [
        "--dump-single-json",
        "--no-warnings",
        "--flat-playlist",
        "--no-cache-dir",
        url,
    ]
    try:
        p = _run_ytdlp(args, timeout=120)
    except subprocess.TimeoutExpired:
        raise RuntimeError("yt-dlp timeout")

    if p.returncode != 0:
        err = (p.stderr or "").strip().splitlines()
        msg = err[-1] if err else f"yt-dlp exit {p.returncode}"
        raise RuntimeError(msg)

    info = json.loads(p.stdout)

    if "entries" in info:
        out: list[Track] = []
        for e in info["entries"]:
            if not e:
                continue
            out.append(_info_to_track(e, flat=True))
        return out

    return [_info_to_track(info)]


def _info_to_track(info: dict[str, Any], flat: bool = False) -> Track:
    url = info.get("webpage_url") or info.get("url") or ""

    if not url and info.get("id"):
        url = f"https://www.youtube.com/watch?v={info['id']}"

    title = info.get("title") or "Unknown"
    live_status = info.get("live_status")
    is_live = live_status == "is_live" or bool(info.get("is_live"))

    duration = info.get("duration")
    kind = "live" if is_live else "video"

    stream_url = ""
    if not flat:
        stream_url = info.get("url") or ""
        if is_live and not stream_url:
            stream_url = info.get("manifest_url") or ""

    return Track(url=url, title=title, is_live=is_live,
                 stream_url=stream_url, duration=duration, kind=kind)

# --- async-обёртки -----------------------------------------------------------

def resolve_async(url: str,
                  on_done: Callable[[Optional[Track], Optional[Exception]], None]) -> None:
    def worker():
        try:
            t = resolve(url)
            on_done(t, None)
        except Exception as e:
            log.exception("resolve_async")
            on_done(None, e)
    threading.Thread(target=worker, name="resolve", daemon=True).start()

def resolve_playlist_async(url: str,
                           on_done: Callable[[Optional[list[Track]], Optional[Exception]], None]) -> None:
    def worker():
        try:
            tracks = resolve_playlist(url)
            on_done(tracks, None)
        except Exception as e:
            log.exception("resolve_playlist_async")
            on_done(None, e)
    threading.Thread(target=worker, name="resolve-playlist", daemon=True).start()

# --- обновление yt-dlp -------------------------------------------------------

YTDLP_RELEASE_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"


def update_ytdlp(on_done: Optional[Callable[[bool, str], None]] = None) -> None:
    def worker():
        try:
            exe = _resolve_bin(config.get("ytdlp_path", "bin/yt-dlp.exe"))
            tmp = exe.with_suffix(".new")
            log.info("Скачиваем свежий yt-dlp: %s", YTDLP_RELEASE_URL)
            urllib.request.urlretrieve(YTDLP_RELEASE_URL, tmp)
            if exe.exists():
                exe.unlink()
            tmp.rename(exe)
            log.info("yt-dlp обновлён")
            if on_done:
                on_done(True, "yt-dlp обновлён")
        except Exception as e:
            log.exception("update_ytdlp")
            if on_done:
                on_done(False, f"Ошибка обновления yt-dlp: {e}")
    threading.Thread(target=worker, name="ytdlp-update", daemon=True).start()