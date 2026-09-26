from __future__ import annotations

import random
import threading
from collections import OrderedDict
from typing import Callable, Optional

from config import config
from logging_setup import log
from player import MpvPlayer
from youtube import (
    Track,
    resolve,
    resolve_playlist,
    make_mix_url,
    extract_video_id,
)

CACHE_SIZE = 4
MIX_QUEUE_LIMIT = 20

class PlaybackQueue:
    def __init__(self, player: MpvPlayer):
        self.player = player
        self.items: list[Track] = []
        self.index: int = -1
        self._lock = threading.Lock()
        self._advancing = False
        self._last_played: Optional[Track] = None

        self._stream_cache: "OrderedDict[str, str]" = OrderedDict()
        self._preloading = False

        self.shuffle: bool = bool(config.get("shuffle_queue", False))
        self._shuffle_history: list[int] = []

        self._failed_next_streak = 0

        self.on_track_changed: Optional[Callable[[Track], None]] = None
        self.on_queue_changed: Optional[Callable[[], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_track_started: Optional[Callable[[Track], None]] = None

        self.player.on_end_file = self._on_end_file
        self.player.on_error = self._on_player_error

    # ------------------------------------------------------------- API

    def play_startup(self) -> None:
        url = config.get("start_url")
        if not url:
            log.info("start_url пустой — автозапуск отключён")
            return
        self._load_single(url)

    def play_url(self, url: str) -> None:
        log.info("play_url: %s", url)
        # очищаем текущую очередь, чтобы Mix строился от нового трека
        with self._lock:
            self.items.clear()
            self.index = -1
            self._shuffle_history.clear()
        self._notify_queue()

        threading.Thread(
            target=self._expand_and_play, args=(url,), daemon=True
        ).start()

    def play_tracks(self, tracks: list[Track], shuffle: bool = False) -> None:
        if not tracks:
            return
        working = list(tracks)
        if shuffle:
            random.shuffle(working)
        with self._lock:
            self.items = working
            self.index = 0
            self._shuffle_history.clear()
        self._notify_queue()
        log.info("play_tracks: %d треков, shuffle=%s", len(working), shuffle)
        self._resolve_and_play(working[0])

    def play_track_direct(self, track: Track) -> None:
        log.info("play_track_direct: %s", track.title)
        self._resolve_and_play(track)

    def set_shuffle(self, enabled: bool) -> None:
        self.shuffle = bool(enabled)
        config.set("shuffle_queue", self.shuffle)
        log.info("shuffle: %s", self.shuffle)

    def next(self) -> None:
        track_to_play: Optional[Track] = None
        with self._lock:
            if self.items:
                if self.shuffle and len(self.items) > 1:
                    candidates = [i for i in range(len(self.items)) if i != self.index]
                    if candidates:
                        self._shuffle_history.append(self.index)
                        self.index = random.choice(candidates)
                        track_to_play = self.items[self.index]
                elif 0 <= self.index < len(self.items) - 1:
                    self.index += 1
                    track_to_play = self.items[self.index]

        if track_to_play is not None:
            self._resolve_and_play(track_to_play)
            return

        self.play_recommendations()

    def prev(self) -> None:
        track_to_play: Optional[Track] = None
        with self._lock:
            if self.shuffle and self._shuffle_history:
                self.index = self._shuffle_history.pop()
                if 0 <= self.index < len(self.items):
                    track_to_play = self.items[self.index]
            elif self.items and self.index > 0:
                self.index -= 1
                track_to_play = self.items[self.index]
            elif self.items:
                self.index = 0
                track_to_play = self.items[0]

        if track_to_play is not None:
            self._resolve_and_play(track_to_play)
            return

        self.play_recommendations()

    def current(self) -> Optional[Track]:
        with self._lock:
            if 0 <= self.index < len(self.items):
                return self.items[self.index]
        return None

    def clear(self) -> None:
        with self._lock:
            self.items.clear()
            self.index = -1
            self._shuffle_history.clear()
        self._notify_queue()

    # ------------------------------------------------------------- кэш

    def _cache_get(self, track: Track) -> Optional[str]:
        vid = extract_video_id(track.url)
        if not vid:
            return None
        with self._lock:
            return self._stream_cache.get(vid)

    def _cache_put(self, track: Track, stream_url: str) -> None:
        vid = extract_video_id(track.url)
        if not vid or not stream_url:
            return
        with self._lock:
            self._stream_cache[vid] = stream_url
            while len(self._stream_cache) > CACHE_SIZE:
                self._stream_cache.popitem(last=False)

    # ------------------------------------------------------------- рекомендации

    def play_recommendations(self) -> None:
        base = self._last_played
        if not base or not base.url:
            log.info("Нет базы для рекомендаций → обычное радио")
            self._play_radio()
            return
        if base.is_live:
            log.info("База — live-стрим → обычное радио")
            self._play_radio()
            return

        mix_url = make_mix_url(base.url)
        if not mix_url:
            log.info("Не удалось построить Mix → обычное радио")
            self._play_radio()
            return

        log.info("Строим рекомендации от: %s → %s", base.title, mix_url)
        base_vid = extract_video_id(base.url)

        def worker():
            try:
                log.info("Mix: начинаю резолв (limit=%d)…", MIX_QUEUE_LIMIT)
                tracks = resolve_playlist(mix_url, limit=MIX_QUEUE_LIMIT)
                log.info("Mix: получено %d треков", len(tracks) if tracks else 0)

                if not tracks:
                    log.warning("Mix пустой → обычное радио")
                    self._play_radio()
                    return

                filtered = [t for t in tracks if extract_video_id(t.url) != base_vid]
                if not filtered:
                    filtered = tracks
                filtered = filtered[:MIX_QUEUE_LIMIT]

                with self._lock:
                    self.items = list(filtered)
                    self.index = 0
                    self._shuffle_history.clear()
                self._notify_queue()
                self._resolve_and_play(filtered[0])
            except Exception as e:
                log.exception("play_recommendations")
                if self.on_error:
                    self.on_error(f"Рекомендации не сработали: {e}")
                self._play_radio()

        threading.Thread(target=worker, name="mix", daemon=True).start()

    # ------------------------------------------------------------- внутреннее

    def _load_single(self, url: str) -> None:
        def worker():
            try:
                track = resolve(url)
                self._failed_next_streak = 0
                self._play_track(track)
            except Exception as e:
                log.exception("_load_single")
                if self.on_error:
                    self.on_error(f"Не удалось запустить: {e}")
                self._failed_next_streak += 1
                if self._failed_next_streak >= 3:
                    self._failed_next_streak = 0
                    return
                self._play_radio()
        threading.Thread(target=worker, name="load-single", daemon=True).start()

    def _expand_and_play(self, url: str) -> None:
        try:
            tracks = resolve_playlist(url, limit=MIX_QUEUE_LIMIT)
        except Exception as e:
            log.exception("_expand_and_play")
            if self.on_error:
                self.on_error(f"Ошибка разбора ссылки: {e}")
            return

        if not tracks:
            if self.on_error:
                self.on_error("Пустая ссылка")
            return

        with self._lock:
            insert_at = self.index + 1 if self.index >= 0 else 0
            self.items[insert_at:insert_at] = tracks
            self.index = insert_at
            self._shuffle_history.clear()
        self._notify_queue()
        self._resolve_and_play(tracks[0])

    def _resolve_and_play(self, track: Track) -> None:
        cached = self._cache_get(track)
        if cached and not track.is_live:
            track.stream_url = cached
            self._failed_next_streak = 0
            self._play_track(track)
            self._preload_next()
            return

        def worker():
            try:
                fresh = resolve(track.url)
                track.stream_url = fresh.stream_url
                track.is_live = fresh.is_live
                track.title = fresh.title or track.title
                if not track.is_live:
                    self._cache_put(track, track.stream_url)
                self._failed_next_streak = 0
                self._play_track(track)
                self._preload_next()
            except Exception as e:
                log.exception("_resolve_and_play: %s", track.title[:40])
                if self.on_error:
                    self.on_error(f"Ошибка трека: {e}")
                self._failed_next_streak += 1
                if self._failed_next_streak >= 3:
                    self._failed_next_streak = 0
                    return
                self.next()
        threading.Thread(target=worker, name="resolve-play", daemon=True).start()

    def _play_track(self, track: Track) -> None:
        if not track.stream_url:
            if self.on_error:
                self.on_error(f"Нет потока для {track.title}")
            self._failed_next_streak += 1
            if self._failed_next_streak >= 3:
                self._failed_next_streak = 0
                return
            self.next()
            return

        self._failed_next_streak = 0
        self._last_played = track
        log.info("Играем: %s (%s)", track.title, "LIVE" if track.is_live else "VOD")
        self.player.play_url(track.stream_url)

        if self.on_track_started:
            try:
                self.on_track_started(track)
            except Exception:
                log.exception("on_track_started")

        if self.on_track_changed:
            self.on_track_changed(track)

    # ------------------------------------------------------------- предзагрузка

    def _next_track(self) -> Optional[Track]:
        with self._lock:
            if self.shuffle and len(self.items) > 1:
                candidates = [i for i in range(len(self.items)) if i != self.index]
                if candidates:
                    return self.items[random.choice(candidates)]
            if self.items and 0 <= self.index < len(self.items) - 1:
                return self.items[self.index + 1]
        return None

    def _preload_next(self) -> None:
        if self._preloading:
            return
        nxt = self._next_track()
        if not nxt:
            return
        if nxt.is_live:
            return
        if self._cache_get(nxt):
            return

        self._preloading = True

        def worker():
            try:
                fresh = resolve(nxt.url)
                if fresh.stream_url and not fresh.is_live:
                    nxt.stream_url = fresh.stream_url
                    nxt.title = fresh.title or nxt.title
                    self._cache_put(nxt, fresh.stream_url)
                    log.info("preload done: %s", nxt.title[:40])
            except Exception:
                log.exception("preload")
            finally:
                self._preloading = False

        threading.Thread(target=worker, name="preload", daemon=True).start()

    # ------------------------------------------------------------- радио

    def _play_radio(self) -> None:
        url = config.get("radio_url")
        if not url:
            log.info("radio_url пустой — стоп")
            self.player.stop()
            return
        log.info("Очередь пуста → радио: %s", url)
        self._load_single(url)

    # ------------------------------------------------------------- end-file

    def _on_end_file(self, reason: str) -> None:
        if reason in ("stop", "quit", "redirect"):
            return

        if self._advancing:
            return
        self._advancing = True
        try:
            log.info("end-file (%s) → next", reason)
            self.next()
        finally:
            threading.Timer(0.5, self._reset_advancing).start()

    def _reset_advancing(self) -> None:
        self._advancing = False

    def _on_player_error(self, msg: str) -> None:
        if self.on_error:
            self.on_error(msg)

    def _notify_queue(self) -> None:
        if self.on_queue_changed:
            try:
                self.on_queue_changed()
            except Exception:
                log.exception("on_queue_changed")