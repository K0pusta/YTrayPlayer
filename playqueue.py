from __future__ import annotations

import threading
from typing import Callable, Optional

from config import config
from logging_setup import log
from player import MpvPlayer
from youtube import Track, resolve, resolve_playlist, make_mix_url

class PlaybackQueue:
    def __init__(self, player: MpvPlayer):
        self.player = player
        self.items: list[Track] = []
        self.index: int = -1
        self._lock = threading.Lock()
        self._advancing = False
        self._last_played: Optional[Track] = None

        self.on_track_changed: Optional[Callable[[Track], None]] = None
        self.on_queue_changed: Optional[Callable[[], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

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
        threading.Thread(
            target=self._expand_and_play, args=(url,), daemon=True
        ).start()

    def next(self) -> None:
        with self._lock:
            if self.items and 0 <= self.index < len(self.items) - 1:
                self.index += 1
                track = self.items[self.index]
                self._resolve_and_play(track)
                return
        # либо пусто, либо конец очереди → рекомендации
        self.play_recommendations()

    def prev(self) -> None:
        with self._lock:
            if self.items and self.index > 0:
                self.index -= 1
                track = self.items[self.index]
                self._resolve_and_play(track)
                return
            if self.items:
                self.index = 0
                track = self.items[0]
                self._resolve_and_play(track)
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
        self._notify_queue()

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

        def worker():
            try:
                tracks = resolve_playlist(mix_url)
                if not tracks:
                    log.warning("Mix пустой → обычное радио")
                    self._play_radio()
                    return

                filtered = [t for t in tracks if t.url != base.url]
                if filtered:
                    tracks = filtered

                with self._lock:
                    self.items = list(tracks)
                    self.index = 0
                self._notify_queue()
                self._resolve_and_play(tracks[0])
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
                self._play_track(track)
            except Exception as e:
                log.exception("_load_single")
                if self.on_error:
                    self.on_error(f"Не удалось запустить: {e}")
        threading.Thread(target=worker, name="load-single", daemon=True).start()

    def _expand_and_play(self, url: str) -> None:
        try:
            tracks = resolve_playlist(url)
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
        self._notify_queue()
        self._resolve_and_play(tracks[0])

    def _resolve_and_play(self, track: Track) -> None:
        if track.is_live or not track.stream_url:
            def worker():
                try:
                    fresh = resolve(track.url)
                    track.stream_url = fresh.stream_url
                    track.is_live = fresh.is_live
                    track.title = fresh.title or track.title
                    self._play_track(track)
                except Exception as e:
                    log.exception("_resolve_and_play")
                    if self.on_error:
                        self.on_error(f"Ошибка трека: {e}")
                    self.next()
            threading.Thread(target=worker, name="resolve-play", daemon=True).start()
        else:
            self._play_track(track)

    def _play_track(self, track: Track) -> None:
        if not track.stream_url:
            if self.on_error:
                self.on_error(f"Нет потока для {track.title}")
            self.next()
            return

        self._last_played = track
        log.info("Играем: %s (%s)", track.title, "LIVE" if track.is_live else "VOD")
        self.player.play_url(track.stream_url)

        if self.on_track_changed:
            self.on_track_changed(track)

    def _play_radio(self) -> None:
        url = config.get("radio_url")
        log.info("Очередь пуста → радио: %s", url)
        self._load_single(url)

    def _on_end_file(self, reason: str) -> None:
        if reason in ("stop", "quit", "redirect"):
            log.debug("end-file (%s) — игнорируем", reason)
            return

        if self._advancing:
            log.debug("end-file (%s) — уже переключаемся, игнор", reason)
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