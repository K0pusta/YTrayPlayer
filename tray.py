from __future__ import annotations

import functools
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

import pystray
from PIL import Image, ImageDraw

from logging_setup import log
from i18n import t

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent

def _load_icon() -> Image.Image:
    icon_path = _base_dir() / "assets" / "icon.ico"
    if icon_path.exists():
        try:
            img = Image.open(icon_path).convert("RGBA")
            if img.size != (64, 64):
                img = img.resize((64, 64), Image.LANCZOS)
            log.info("Иконка загружена: %s", icon_path)
            return img
        except Exception:
            log.exception("Не удалось загрузить %s", icon_path)
    else:
        log.warning("Иконка не найдена: %s", icon_path)

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, size - 4, size - 4), fill=(30, 30, 30, 255))
    d.rectangle((38, 16, 42, 44), fill=(255, 255, 255, 255))
    d.ellipse((26, 38, 40, 52), fill=(255, 255, 255, 255))
    d.rectangle((42, 16, 50, 22), fill=(255, 255, 255, 255))
    return img

class TrayIcon:
    def __init__(
        self,
        on_play_pause: Callable[[], None],
        on_next: Callable[[], None],
        on_prev: Callable[[], None],
        on_quit: Callable[[], None],
        on_play_clipboard: Optional[Callable[[], None]] = None,
        on_input_url: Optional[Callable[[], None]] = None,
        on_add_favorite: Optional[Callable[[], None]] = None,
        favorites_provider: Optional[Callable[[], list[dict]]] = None,
        on_play_favorite: Optional[Callable[[str], None]] = None,
        on_remove_favorite: Optional[Callable[[str], None]] = None,
        on_play_all_favorites: Optional[Callable[[], None]] = None,
        on_toggle_favorites_shuffle: Optional[Callable[[], None]] = None,
        favorites_shuffle_state: Optional[Callable[[], bool]] = None,
        on_save_playlist: Optional[Callable[[], None]] = None,
        playlists_provider: Optional[Callable[[], list[dict]]] = None,
        on_play_playlist: Optional[Callable[[str], None]] = None,
        on_play_playlist_shuffle: Optional[Callable[[str], None]] = None,
        on_remove_playlist: Optional[Callable[[str], None]] = None,
        on_create_playlist: Optional[Callable[[], None]] = None,
        on_add_current_to_playlist: Optional[Callable[[], None]] = None,
        on_toggle_notifications: Optional[Callable[[], None]] = None,
        notifications_state: Optional[Callable[[], bool]] = None,
        on_toggle_hotkeys: Optional[Callable[[], None]] = None,
        hotkeys_state: Optional[Callable[[], bool]] = None,
        on_toggle_shuffle: Optional[Callable[[], None]] = None,
        shuffle_state: Optional[Callable[[], bool]] = None,
        on_set_language: Optional[Callable[[str], None]] = None,
        language_state: Optional[Callable[[], str]] = None,
        on_update_ytdlp: Optional[Callable[[], None]] = None,
    ) -> None:
        self.on_play_pause = on_play_pause
        self.on_next = on_next
        self.on_prev = on_prev
        self.on_quit = on_quit
        self.on_play_clipboard = on_play_clipboard
        self.on_input_url = on_input_url
        self.on_add_favorite = on_add_favorite
        self.favorites_provider = favorites_provider
        self.on_play_favorite = on_play_favorite
        self.on_remove_favorite = on_remove_favorite
        self.on_play_all_favorites = on_play_all_favorites
        self.on_toggle_favorites_shuffle = on_toggle_favorites_shuffle
        self.favorites_shuffle_state = favorites_shuffle_state
        self.on_save_playlist = on_save_playlist
        self.playlists_provider = playlists_provider
        self.on_play_playlist = on_play_playlist
        self.on_play_playlist_shuffle = on_play_playlist_shuffle
        self.on_remove_playlist = on_remove_playlist
        self.on_create_playlist = on_create_playlist
        self.on_add_current_to_playlist = on_add_current_to_playlist
        self.on_toggle_notifications = on_toggle_notifications
        self.notifications_state = notifications_state
        self.on_toggle_hotkeys = on_toggle_hotkeys
        self.hotkeys_state = hotkeys_state
        self.on_toggle_shuffle = on_toggle_shuffle
        self.shuffle_state = shuffle_state
        self.on_set_language = on_set_language
        self.language_state = language_state
        self.on_update_ytdlp = on_update_ytdlp

        self._icon: Optional[pystray.Icon] = None
        self._title: str = "YTray Player"
        self._thread: Optional[threading.Thread] = None

    # -------------------------------------------------------------- меню

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(t("play_pause", "Play / Pause"),
                             self._click_play_pause, default=True),
            pystray.MenuItem(t("next", "Next"), self._click_next),
            pystray.MenuItem(t("prev", "Prev"), self._click_prev),
            pystray.MenuItem(
                t("shuffle", "Shuffle очередь"),
                self._click_toggle_shuffle,
                checked=lambda item: bool(self.shuffle_state and self.shuffle_state()),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(t("play_clipboard", "Play from clipboard"),
                             self._click_play_clipboard),
            pystray.MenuItem(t("input_url", "Enter URL…"),
                             self._click_input_url),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(t("add_favorite", "Add to favorites"),
                             self._click_add_favorite),
            pystray.MenuItem(t("favorites", "Favorites"),
                             self._submenu_favorites()),
            pystray.MenuItem(t("save_playlist", "Save current playlist…"),
                             self._click_save_playlist),
            pystray.MenuItem(t("create_playlist", "Создать плейлист…"),
                             self._click_create_playlist),
            pystray.MenuItem(t("add_to_playlist", "Добавить в плейлист…"),
                             self._click_add_to_playlist),
            pystray.MenuItem(t("playlists", "Playlists"),
                             self._submenu_playlists()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                t("notifications", "Notifications"),
                self._click_toggle_notifications,
                checked=lambda item: bool(self.notifications_state and self.notifications_state()),
            ),
            pystray.MenuItem(
                t("hotkeys", "Hotkeys"),
                self._click_toggle_hotkeys,
                checked=lambda item: bool(self.hotkeys_state and self.hotkeys_state()),
            ),
            pystray.MenuItem(t("language", "Language"), self._submenu_language()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(t("update_ytdlp", "Update yt-dlp"),
                             self._click_update_ytdlp),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(t("quit", "Quit"), self._click_quit),
        )

    def start(self) -> None:
        self._icon = pystray.Icon(
            name="ytray", icon=_load_icon(),
            title=self._title, menu=self._build_menu(),
        )
        self._thread = threading.Thread(target=self._icon.run, name="tray", daemon=True)
        self._thread.start()
        log.info("Трей-иконка запущена")

    def stop(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass

    def rebuild_menu(self) -> None:
        if not self._icon:
            return
        try:
            self._icon.menu = self._build_menu()
            self._icon.update_menu()
        except Exception:
            log.exception("rebuild_menu")

    def set_title(self, title: str) -> None:
        self._title = title or "YTray Player"
        if self._icon:
            try:
                self._icon.title = self._title
            except Exception:
                pass

    def refresh_menu(self) -> None:
        if self._icon:
            try:
                self._icon.update_menu()
            except Exception:
                pass

    # -------------------------------------------------------------- подменю: избранное

    def _submenu_favorites(self) -> pystray.Menu:
        def make_items():
            result = []
            result.append(pystray.MenuItem(
                t("play_all_favorites", "▶ Слушать всё избранное"),
                self._click_play_all_favorites,
            ))
            result.append(pystray.MenuItem(
                t("favorites_shuffle", "Shuffle избранного"),
                self._click_toggle_favorites_shuffle,
                checked=lambda item: bool(self.favorites_shuffle_state and self.favorites_shuffle_state()),
            ))
            result.append(pystray.Menu.SEPARATOR)

            if not self.favorites_provider:
                result.append(pystray.MenuItem(t("empty", "(пусто)"), None, enabled=False))
                return result
            try:
                items = self.favorites_provider()
            except Exception:
                result.append(pystray.MenuItem(t("error", "(ошибка)"), None, enabled=False))
                return result

            if not items:
                result.append(pystray.MenuItem(t("empty", "(пусто)"), None, enabled=False))
                return result

            for it in items:
                url = it.get("url", "")
                title = it.get("title", "Unknown")
                tag = "[LIVE] " if it.get("is_live") else ""
                label = f"{tag}{title[:60]}"
                sub = pystray.Menu(
                    pystray.MenuItem(t("play", "Play"),
                                     functools.partial(self._click_play_favorite_item, url=url)),
                    pystray.MenuItem(t("remove_from_favorites", "Remove from favorites"),
                                     functools.partial(self._click_remove_favorite_item, url=url)),
                )
                result.append(pystray.MenuItem(label, sub))
            return result

        return pystray.Menu(make_items)

    def _click_play_all_favorites(self, icon, item) -> None:
        if self.on_play_all_favorites:
            try:
                self.on_play_all_favorites()
            except Exception:
                log.exception("play_all_favorites")

    def _click_toggle_favorites_shuffle(self, icon, item) -> None:
        if self.on_toggle_favorites_shuffle:
            try:
                self.on_toggle_favorites_shuffle()
            except Exception:
                log.exception("toggle_favorites_shuffle")
        self.refresh_menu()

    def _click_play_favorite_item(self, icon, item, url: str = "") -> None:
        if not url:
            return
        try:
            if self.on_play_favorite:
                self.on_play_favorite(url)
        except Exception:
            log.exception("play_favorite")

    def _click_remove_favorite_item(self, icon, item, url: str = "") -> None:
        if not url:
            return
        try:
            if self.on_remove_favorite:
                self.on_remove_favorite(url)
        except Exception:
            log.exception("remove_favorite")

    def _click_add_favorite(self, icon, item) -> None:
        if self.on_add_favorite:
            try:
                self.on_add_favorite()
            except Exception:
                log.exception("add_favorite")

    # -------------------------------------------------------------- подменю: плейлисты

    def _submenu_playlists(self) -> pystray.Menu:
        def make_items():
            if not self.playlists_provider:
                return [pystray.MenuItem(t("empty", "(пусто)"), None, enabled=False)]
            try:
                items = self.playlists_provider()
            except Exception:
                return [pystray.MenuItem(t("error", "(ошибка)"), None, enabled=False)]

            if not items:
                return [pystray.MenuItem(t("empty", "(пусто)"), None, enabled=False)]

            result = []
            for it in items:
                name = it.get("name", "Unknown")
                ptype = it.get("type", "youtube")
                label = name[:60]

                if ptype == "youtube":
                    sub = pystray.Menu(
                        pystray.MenuItem(t("play", "Играть"),
                                         functools.partial(self._click_play_playlist_item, name=name)),
                        pystray.MenuItem(t("remove_from_playlists", "Удалить"),
                                         functools.partial(self._click_remove_playlist_item, name=name)),
                    )
                else:
                    sub = pystray.Menu(
                        pystray.MenuItem(t("play", "Играть"),
                                         functools.partial(self._click_play_playlist_item, name=name)),
                        pystray.MenuItem(t("play_shuffle", "Играть в shuffle"),
                                         functools.partial(self._click_play_playlist_shuffle, name=name)),
                        pystray.MenuItem(t("delete_playlist", "Удалить плейлист"),
                                         functools.partial(self._click_remove_playlist_item, name=name)),
                    )
                result.append(pystray.MenuItem(label, sub))
            return result

        return pystray.Menu(make_items)

    def _click_save_playlist(self, icon, item) -> None:
        if self.on_save_playlist:
            try:
                self.on_save_playlist()
            except Exception:
                log.exception("save_playlist")

    def _click_create_playlist(self, icon, item) -> None:
        if self.on_create_playlist:
            try:
                self.on_create_playlist()
            except Exception:
                log.exception("create_playlist")

    def _click_add_to_playlist(self, icon, item) -> None:
        if self.on_add_current_to_playlist:
            try:
                self.on_add_current_to_playlist()
            except Exception:
                log.exception("add_to_playlist")

    def _click_play_playlist_item(self, icon, item, name: str = "") -> None:
        if name and self.on_play_playlist:
            try:
                self.on_play_playlist(name)
            except Exception:
                log.exception("play_playlist")

    def _click_play_playlist_shuffle(self, icon, item, name: str = "") -> None:
        if name and self.on_play_playlist_shuffle:
            try:
                self.on_play_playlist_shuffle(name)
            except Exception:
                log.exception("play_playlist_shuffle")

    def _click_remove_playlist_item(self, icon, item, name: str = "") -> None:
        if name and self.on_remove_playlist:
            try:
                self.on_remove_playlist(name)
            except Exception:
                log.exception("remove_playlist")

    # -------------------------------------------------------------- подменю: язык

    def _submenu_language(self) -> pystray.Menu:
        def make_items():
            cur = self.language_state() if self.language_state else "ru"
            return [
                pystray.MenuItem(t("lang_ru", "Русский"),
                                 functools.partial(self._click_set_language_item, lang="ru"),
                                 checked=lambda item: cur == "ru", radio=True),
                pystray.MenuItem(t("lang_en", "English"),
                                 functools.partial(self._click_set_language_item, lang="en"),
                                 checked=lambda item: cur == "en", radio=True),
            ]
        return pystray.Menu(make_items)

    def _click_set_language_item(self, icon, item, lang: str = "ru") -> None:
        if self.on_set_language:
            try:
                self.on_set_language(lang)
            except Exception:
                log.exception("set_language")

    # -------------------------------------------------------------- клики

    def _click_play_pause(self, icon, item) -> None:
        if self.on_play_pause:
            try: self.on_play_pause()
            except Exception: log.exception("play_pause")

    def _click_next(self, icon, item) -> None:
        if self.on_next:
            try: self.on_next()
            except Exception: log.exception("next")

    def _click_prev(self, icon, item) -> None:
        if self.on_prev:
            try: self.on_prev()
            except Exception: log.exception("prev")

    def _click_quit(self, icon, item) -> None:
        try:
            if self.on_quit:
                self.on_quit()
        except Exception:
            log.exception("quit")
        try:
            icon.stop()
        except Exception:
            pass

    def _click_play_clipboard(self, icon, item) -> None:
        if self.on_play_clipboard:
            try: self.on_play_clipboard()
            except Exception: log.exception("play_clipboard")

    def _click_input_url(self, icon, item) -> None:
        if self.on_input_url:
            try: self.on_input_url()
            except Exception: log.exception("input_url")

    def _click_toggle_notifications(self, icon, item) -> None:
        if self.on_toggle_notifications:
            try: self.on_toggle_notifications()
            except Exception: log.exception("toggle_notifications")
        self.refresh_menu()

    def _click_toggle_hotkeys(self, icon, item) -> None:
        if self.on_toggle_hotkeys:
            try: self.on_toggle_hotkeys()
            except Exception: log.exception("toggle_hotkeys")
        self.refresh_menu()

    def _click_toggle_shuffle(self, icon, item) -> None:
        if self.on_toggle_shuffle:
            try: self.on_toggle_shuffle()
            except Exception: log.exception("toggle_shuffle")
        self.refresh_menu()

    def _click_update_ytdlp(self, icon, item) -> None:
        if self.on_update_ytdlp:
            try: self.on_update_ytdlp()
            except Exception: log.exception("update_ytdlp")