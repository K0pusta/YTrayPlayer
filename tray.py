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
        on_search: Optional[Callable[[], None]] = None,
        on_add_favorite: Optional[Callable[[], None]] = None,
        favorites_provider: Optional[Callable[[], list[dict]]] = None,
        on_play_favorite: Optional[Callable[[str], None]] = None,
        on_remove_favorite: Optional[Callable[[str], None]] = None,
        on_play_all_favorites: Optional[Callable[[], None]] = None,
        on_save_playlist: Optional[Callable[[], None]] = None,
        playlists_provider: Optional[Callable[[], list[dict]]] = None,
        on_play_playlist: Optional[Callable[[str], None]] = None,
        on_play_playlist_shuffle: Optional[Callable[[str], None]] = None,
        on_remove_playlist: Optional[Callable[[str], None]] = None,
        on_edit_playlist: Optional[Callable[[str], None]] = None,
        on_create_playlist: Optional[Callable[[], None]] = None,
        on_add_current_to_playlist: Optional[Callable[[], None]] = None,
        on_toggle_shuffle: Optional[Callable[[], None]] = None,
        shuffle_state: Optional[Callable[[], bool]] = None,
        on_open_settings: Optional[Callable[[], None]] = None,
    ) -> None:
        self.on_play_pause = on_play_pause
        self.on_next = on_next
        self.on_prev = on_prev
        self.on_quit = on_quit
        self.on_play_clipboard = on_play_clipboard
        self.on_input_url = on_input_url
        self.on_search = on_search
        self.on_add_favorite = on_add_favorite
        self.favorites_provider = favorites_provider
        self.on_play_favorite = on_play_favorite
        self.on_remove_favorite = on_remove_favorite
        self.on_play_all_favorites = on_play_all_favorites
        self.on_save_playlist = on_save_playlist
        self.playlists_provider = playlists_provider
        self.on_play_playlist = on_play_playlist
        self.on_play_playlist_shuffle = on_play_playlist_shuffle
        self.on_remove_playlist = on_remove_playlist
        self.on_edit_playlist = on_edit_playlist
        self.on_create_playlist = on_create_playlist
        self.on_add_current_to_playlist = on_add_current_to_playlist
        self.on_toggle_shuffle = on_toggle_shuffle
        self.shuffle_state = shuffle_state
        self.on_open_settings = on_open_settings

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
            pystray.MenuItem(t("search", "🔍 Поиск…"),
                             self._click_search),
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
            pystray.MenuItem(t("settings", "⚙️ Настройки…"),
                             self._click_settings),
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

    # -------------------------------------------------------------- избранное

    def _submenu_favorites(self) -> pystray.Menu:
        def make_items():
            result = []
            result.append(pystray.MenuItem(
                t("play_all_favorites", "▶ Слушать всё избранное"),
                self._click_play_all_favorites,
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
            try: self.on_play_all_favorites()
            except Exception: log.exception("play_all_favorites")

    def _click_play_favorite_item(self, icon, item, url: str = "") -> None:
        if not url: return
        try:
            if self.on_play_favorite: self.on_play_favorite(url)
        except Exception: log.exception("play_favorite")

    def _click_remove_favorite_item(self, icon, item, url: str = "") -> None:
        if not url: return
        try:
            if self.on_remove_favorite: self.on_remove_favorite(url)
        except Exception: log.exception("remove_favorite")

    def _click_add_favorite(self, icon, item) -> None:
        if self.on_add_favorite:
            try: self.on_add_favorite()
            except Exception: log.exception("add_favorite")

    # -------------------------------------------------------------- плейлисты

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
                        pystray.MenuItem(t("edit_playlist", "✏️ Редактировать…"),
                                         functools.partial(self._click_edit_playlist, name=name)),
                        pystray.MenuItem(t("delete_playlist", "Удалить плейлист"),
                                         functools.partial(self._click_remove_playlist_item, name=name)),
                    )
                result.append(pystray.MenuItem(label, sub))
            return result

        return pystray.Menu(make_items)

    def _click_save_playlist(self, icon, item) -> None:
        if self.on_save_playlist:
            try: self.on_save_playlist()
            except Exception: log.exception("save_playlist")

    def _click_create_playlist(self, icon, item) -> None:
        if self.on_create_playlist:
            try: self.on_create_playlist()
            except Exception: log.exception("create_playlist")

    def _click_add_to_playlist(self, icon, item) -> None:
        if self.on_add_current_to_playlist:
            try: self.on_add_current_to_playlist()
            except Exception: log.exception("add_to_playlist")

    def _click_play_playlist_item(self, icon, item, name: str = "") -> None:
        if name and self.on_play_playlist:
            try: self.on_play_playlist(name)
            except Exception: log.exception("play_playlist")

    def _click_play_playlist_shuffle(self, icon, item, name: str = "") -> None:
        if name and self.on_play_playlist_shuffle:
            try: self.on_play_playlist_shuffle(name)
            except Exception: log.exception("play_playlist_shuffle")

    def _click_edit_playlist(self, icon, item, name: str = "") -> None:
        if name and self.on_edit_playlist:
            try: self.on_edit_playlist(name)
            except Exception: log.exception("edit_playlist")

    def _click_remove_playlist_item(self, icon, item, name: str = "") -> None:
        if name and self.on_remove_playlist:
            try: self.on_remove_playlist(name)
            except Exception: log.exception("remove_playlist")

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
            if self.on_quit: self.on_quit()
        except Exception: log.exception("quit")
        try: icon.stop()
        except Exception: pass

    def _click_play_clipboard(self, icon, item) -> None:
        if self.on_play_clipboard:
            try: self.on_play_clipboard()
            except Exception: log.exception("play_clipboard")

    def _click_input_url(self, icon, item) -> None:
        if self.on_input_url:
            try: self.on_input_url()
            except Exception: log.exception("input_url")

    def _click_search(self, icon, item) -> None:
        if self.on_search:
            try: self.on_search()
            except Exception: log.exception("search")

    def _click_toggle_shuffle(self, icon, item) -> None:
        if self.on_toggle_shuffle:
            try: self.on_toggle_shuffle()
            except Exception: log.exception("toggle_shuffle")
        self.refresh_menu()

    def _click_settings(self, icon, item) -> None:
        if self.on_open_settings:
            try: self.on_open_settings()
            except Exception: log.exception("open_settings")