from __future__ import annotations

import queue as _queue
import threading
import time

from config import config
from logging_setup import log
from player import MpvPlayer
from playqueue import PlaybackQueue
from hotkeys import HotkeyManager
from tray import TrayIcon
from clipboard import get_youtube_from_clipboard
from input_dialog import InputDialog, PlaylistPickerDialog
from favorites import Favorites
from playlists import Playlists, is_playlist_url
from resume import Resume
from youtube import Track, update_ytdlp
from i18n import i18n
import notify

def on_track(track: Track) -> None:
    tag = "LIVE" if track.is_live else "VOD"
    print(f"\n▶ [{tag}] {track.title}\n")
    notify.notify_track(track.title, track.is_live)

def on_error(msg: str) -> None:
    print(f"\n⚠ {msg}\n")
    notify.notify_error(msg)

def main() -> None:
    print("Запуск mpv…")
    player = MpvPlayer()

    q = PlaybackQueue(player)
    q.on_track_changed = on_track
    q.on_error = on_error

    quit_flag = {"stop": False}
    tray_ref = {"obj": None}
    fav = Favorites()
    pls = Playlists()
    resume = Resume()
    last_url = {"value": ""}

    hotkeys_active = {"value": bool(config.get("hotkeys_enabled", True))}
    favorites_shuffle = {"value": bool(config.get("favorites_shuffle", False))}

    ui_queue: "_queue.Queue" = _queue.Queue()

    # --- хоткеи ---
    hk = HotkeyManager()

    def _hotkeys_enabled() -> bool:
        return hotkeys_active["value"] and bool(config.get("hotkeys_enabled", True))

    def hk_play_pause():
        if not _hotkeys_enabled():
            return
        player.pause()

    def hk_next():
        if not _hotkeys_enabled():
            return
        q.next()

    def hk_prev():
        if not _hotkeys_enabled():
            return
        q.prev()

    def hk_vol_up():
        if not _hotkeys_enabled():
            return
        player.next_vol(5)

    def hk_vol_down():
        if not _hotkeys_enabled():
            return
        player.next_vol(-5)

    def hk_favorite():
        if not _hotkeys_enabled():
            return
        cur = q.current()
        if not cur:
            return
        added = fav.add_track(cur)
        if added:
            print(f"\n[hotkey] добавлено в избранное: {cur.title}")
            if tray_ref["obj"]:
                tray_ref["obj"].refresh_menu()

    def hk_play_clip():
        if not _hotkeys_enabled():
            return
        url = get_youtube_from_clipboard()
        if url:
            last_url["value"] = url
            q.play_url(url)

    def hk_toggle_shuffle():
        if not _hotkeys_enabled():
            return
        new_val = not q.shuffle
        q.set_shuffle(new_val)
        print(f"\n[hotkey] shuffle: {'вкл' if new_val else 'выкл'}")
        if tray_ref["obj"]:
            tray_ref["obj"].refresh_menu()

    for name, cb in [
        ("play_pause", hk_play_pause),
        ("next", hk_next),
        ("prev", hk_prev),
        ("vol_up", hk_vol_up),
        ("vol_down", hk_vol_down),
        ("favorite", hk_favorite),
        ("play_clip", hk_play_clip),
        ("toggle_shuffle", hk_toggle_shuffle),
    ]:
        hk.register(name, cb)

    hk.start()
    # --- конец хоткеев ---

    # --- трей ---
    def tray_play_pause():
        player.pause()

    def tray_next():
        q.next()

    def tray_prev():
        q.prev()

    def tray_quit():
        quit_flag["stop"] = True

    def tray_play_clipboard():
        url = get_youtube_from_clipboard()
        if url:
            last_url["value"] = url
            q.play_url(url)

    def tray_input_url():
        ui_queue.put("input_url")

    def tray_add_favorite():
        cur = q.current()
        if not cur:
            return
        if fav.add_track(cur):
            if tray_ref["obj"]:
                tray_ref["obj"].refresh_menu()

    def favorites_provider():
        return fav.all()

    def tray_play_favorite(url: str):
        last_url["value"] = url
        q.play_url(url)

    def tray_remove_favorite(url: str):
        if fav.remove_by_url(url):
            if tray_ref["obj"]:
                tray_ref["obj"].refresh_menu()

    def tray_play_all_favorites():
        tracks = fav.all_tracks()
        if not tracks:
            notify.notify_info("Избранное пусто")
            return
        q.play_tracks(tracks, shuffle=favorites_shuffle["value"])
        print(f"\n[fav] играем всё избранное ({len(tracks)} треков, shuffle={favorites_shuffle['value']})")

    # --- плейлисты ---

    def tray_save_playlist():
        ui_queue.put("save_playlist")

    def tray_create_playlist():
        ui_queue.put("create_playlist")

    def tray_add_to_playlist():
        ui_queue.put("add_to_playlist")

    def playlists_provider():
        return pls.all()

    def tray_play_playlist(name: str):
        item = pls.get(name)
        if not item:
            return
        if item.get("type") == "user":
            tracks = pls.user_tracks(name)
            if not tracks:
                notify.notify_info(f"Плейлист «{name}» пуст")
                return
            q.play_tracks(tracks)
        else:
            last_url["value"] = item.get("url", "")
            q.play_url(item.get("url", ""))

    def tray_play_playlist_shuffle(name: str):
        item = pls.get(name)
        if not item or item.get("type") != "user":
            return
        tracks = pls.user_tracks(name)
        if not tracks:
            notify.notify_info(f"Плейлист «{name}» пуст")
            return
        q.play_tracks(tracks, shuffle=True)

    def tray_remove_playlist(name: str):
        if pls.remove_by_name(name):
            if tray_ref["obj"]:
                tray_ref["obj"].refresh_menu()

    # --- уведомления / хоткеи / shuffle / язык / ytdlp ---

    def tray_toggle_notifications():
        new_val = not notify.is_enabled()
        notify.set_enabled(new_val)

    def notifications_state():
        return notify.is_enabled()

    def tray_toggle_hotkeys():
        new_val = not bool(config.get("hotkeys_enabled", True))
        config.set("hotkeys_enabled", new_val)
        hotkeys_active["value"] = new_val

    def hotkeys_state():
        return bool(config.get("hotkeys_enabled", True)) and hotkeys_active["value"]

    def tray_toggle_shuffle():
        new_val = not q.shuffle
        q.set_shuffle(new_val)
        print(f"\n[shuffle] {'вкл' if new_val else 'выкл'}")

    def shuffle_state():
        return q.shuffle

    def tray_toggle_favorites_shuffle():
        new_val = not favorites_shuffle["value"]
        favorites_shuffle["value"] = new_val
        config.set("favorites_shuffle", new_val)
        print(f"\n[fav-shuffle] {'вкл' if new_val else 'выкл'}")

    def favorites_shuffle_state():
        return favorites_shuffle["value"]

    def tray_set_language(lang: str):
        i18n.set_language(lang)
        if tray_ref["obj"]:
            tray_ref["obj"].rebuild_menu()

    def language_state():
        return str(config.get("language", "ru"))

    def tray_update_ytdlp():
        notify.notify_info("Обновление yt-dlp…")

        def on_done(ok: bool, msg: str):
            if ok:
                notify.notify_info("yt-dlp обновлён")
            else:
                notify.notify_error(msg)

        update_ytdlp(on_done)

    tray = TrayIcon(
        on_play_pause=tray_play_pause,
        on_next=tray_next,
        on_prev=tray_prev,
        on_quit=tray_quit,
        on_play_clipboard=tray_play_clipboard,
        on_input_url=tray_input_url,
        on_add_favorite=tray_add_favorite,
        favorites_provider=favorites_provider,
        on_play_favorite=tray_play_favorite,
        on_remove_favorite=tray_remove_favorite,
        on_play_all_favorites=tray_play_all_favorites,
        on_toggle_favorites_shuffle=tray_toggle_favorites_shuffle,
        favorites_shuffle_state=favorites_shuffle_state,
        on_save_playlist=tray_save_playlist,
        playlists_provider=playlists_provider,
        on_play_playlist=tray_play_playlist,
        on_play_playlist_shuffle=tray_play_playlist_shuffle,
        on_remove_playlist=tray_remove_playlist,
        on_create_playlist=tray_create_playlist,
        on_add_current_to_playlist=tray_add_to_playlist,
        on_toggle_notifications=tray_toggle_notifications,
        notifications_state=notifications_state,
        on_toggle_hotkeys=tray_toggle_hotkeys,
        hotkeys_state=hotkeys_state,
        on_toggle_shuffle=tray_toggle_shuffle,
        shuffle_state=shuffle_state,
        on_set_language=tray_set_language,
        language_state=language_state,
        on_update_ytdlp=tray_update_ytdlp,
    )
    tray_ref["obj"] = tray
    tray.start()

    # --- лог mpv media-title (для диагностики) ---
    def _on_mpv_title(t: str) -> None:
        log.info("main: mpv media-title = %s", t)

    player.on_title = _on_mpv_title

    _orig_on_track = q.on_track_changed

    def on_track_with_tray(track: Track):
        if _orig_on_track:
            _orig_on_track(track)
        tag = "LIVE" if track.is_live else "VOD"
        tray.set_title(f"[{tag}] {track.title}")

    q.on_track_changed = on_track_with_tray

    def on_track_started(track: Track):
        resume.set_track(track)

    q.on_track_started = on_track_started
    # --- конец трея ---

    # --- старт: resume или start_url ---
    start_url = config.get("start_url")
    if start_url:
        print("Играем стартовый URL…")
        q.play_startup()
    else:
        rt = resume.get_track()
        if rt:
            print(f"Продолжаем с: {rt.title}")
            q.play_track_direct(rt)
        else:
            print("Нечего продолжать — ждём команды пользователя")
    # --- конец старта ---

    def watchdog():
        while not quit_flag["stop"]:
            time.sleep(5)
            player.ensure_alive()

    threading.Thread(target=watchdog, name="watchdog", daemon=True).start()

    print(
        "\nКоманды: n=next  p=prev  s=play/pause  +=громче  -=тише  "
        "m=mute  u <url>=играть  q=выход\n"
    )

    def input_loop():
        while not quit_flag["stop"]:
            try:
                cmd = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                quit_flag["stop"] = True
                break
            if not cmd:
                continue
            if cmd == "q":
                quit_flag["stop"] = True
                break
            elif cmd == "n":
                q.next()
            elif cmd == "p":
                q.prev()
            elif cmd in ("s", " "):
                player.pause()
            elif cmd == "+":
                player.next_vol(5)
            elif cmd == "-":
                player.next_vol(-5)
            elif cmd == "m":
                player.toggle_mute()
            elif cmd.startswith("u "):
                url = cmd[2:].strip()
                if url:
                    last_url["value"] = url
                    q.play_url(url)

    threading.Thread(target=input_loop, name="input", daemon=True).start()

    # --- UI-задачи ---

    def process_ui_task(task: str) -> None:
        if task == "input_url":
            url = InputDialog.get_url("Играть ссылку")
            if url:
                last_url["value"] = url
                q.play_url(url)

        elif task == "save_playlist":
            url = last_url["value"]
            if not url:
                notify.notify_info("Нет последней ссылки")
                return
            if not is_playlist_url(url):
                notify.notify_info("Это не плейлист")
                return
            name = InputDialog.get_name(
                title="Сохранить YouTube-плейлист",
                prompt="Введите имя плейлиста:",
            )
            if not name:
                return
            if pls.add_youtube(name, url):
                notify.notify_info(f"Плейлист «{name}» сохранён")
                if tray_ref["obj"]:
                    tray_ref["obj"].refresh_menu()
            else:
                notify.notify_info("Имя занято или такой плейлист уже сохранён")

        elif task == "create_playlist":
            name = InputDialog.get_name(
                title="Новый плейлист",
                prompt="Введите имя нового плейлиста:",
            )
            if not name:
                return
            if pls.add_user(name):
                notify.notify_info(f"Плейлист «{name}» создан")
                if tray_ref["obj"]:
                    tray_ref["obj"].refresh_menu()
            else:
                notify.notify_info("Имя занято")

        elif task == "add_to_playlist":
            cur = q.current()
            if not cur:
                notify.notify_info("Нет текущего трека")
                return

            selected, create_new = PlaylistPickerDialog.pick(pls.all())

            if create_new:
                name = InputDialog.get_name(
                    title="Новый плейлист",
                    prompt="Введите имя нового плейлиста:",
                )
                if not name:
                    return
                if pls.add_user(name):
                    pls.add_track_to_user(name, cur)
                    notify.notify_info(f"Создан «{name}» и добавлен трек")
                    if tray_ref["obj"]:
                        tray_ref["obj"].refresh_menu()
                else:
                    notify.notify_info("Имя занято")
                return

            if not selected:
                return
            if pls.add_track_to_user(selected, cur):
                notify.notify_info(f"Добавлено в «{selected}»")
                if tray_ref["obj"]:
                    tray_ref["obj"].refresh_menu()
            else:
                notify.notify_info("Трек уже в плейлисте")

    try:
        while not quit_flag["stop"]:
            try:
                task = ui_queue.get(timeout=0.2)
                process_ui_task(task)
            except _queue.Empty:
                pass
    except KeyboardInterrupt:
        quit_flag["stop"] = True
    finally:
        print("\nВыход…")
        tray.stop()
        hk.unregister_all()
        hk.stop()
        player.shutdown()


if __name__ == "__main__":
    main()