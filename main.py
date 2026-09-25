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
from input_dialog import InputDialog
from favorites import Favorites
from playlists import Playlists, is_playlist_url
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
    last_url = {"value": ""}

    hotkeys_active = {"value": bool(config.get("hotkeys_enabled", True))}

    ui_queue: "_queue.Queue" = _queue.Queue()

    # --- хоткеи ---
    hk = HotkeyManager()

    def _hotkeys_enabled() -> bool:
        return hotkeys_active["value"] and bool(config.get("hotkeys_enabled", True))

    def hk_play_pause():
        if not _hotkeys_enabled():
            return
        print("\n[hotkey] play/pause")
        player.pause()

    def hk_next():
        if not _hotkeys_enabled():
            return
        print("\n[hotkey] next")
        q.next()

    def hk_prev():
        if not _hotkeys_enabled():
            return
        print("\n[hotkey] prev")
        q.prev()

    def hk_vol_up():
        if not _hotkeys_enabled():
            return
        player.next_vol(5)
        print(f"\n[hotkey] volume → {int(config.get('volume', 100))}")

    def hk_vol_down():
        if not _hotkeys_enabled():
            return
        player.next_vol(-5)
        print(f"\n[hotkey] volume → {int(config.get('volume', 100))}")

    def hk_favorite():
        if not _hotkeys_enabled():
            return
        cur = q.current()
        if not cur:
            print("\n[hotkey] favorite: нет текущего трека")
            return
        added = fav.add_track(cur)
        if added:
            print(f"\n[hotkey] добавлено в избранное: {cur.title}")
            if tray_ref["obj"]:
                tray_ref["obj"].refresh_menu()
        else:
            print(f"\n[hotkey] уже в избранном: {cur.title}")

    def hk_play_clip():
        if not _hotkeys_enabled():
            return
        url = get_youtube_from_clipboard()
        if url:
            print(f"\n[hotkey] clipboard → {url}")
            last_url["value"] = url
            q.play_url(url)

    for name, cb in [
        ("play_pause", hk_play_pause),
        ("next", hk_next),
        ("prev", hk_prev),
        ("vol_up", hk_vol_up),
        ("vol_down", hk_vol_down),
        ("favorite", hk_favorite),
        ("play_clip", hk_play_clip),
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
            print(f"\n[clipboard] играем: {url}")
            last_url["value"] = url
            q.play_url(url)

    def tray_input_url():
        ui_queue.put("input_url")

    def tray_add_favorite():
        cur = q.current()
        if not cur:
            print("\n[fav] нет текущего трека")
            return
        added = fav.add_track(cur)
        if added:
            print(f"\n[fav] добавлено: {cur.title}")
            if tray_ref["obj"]:
                tray_ref["obj"].refresh_menu()
        else:
            print(f"\n[fav] уже в избранном: {cur.title}")

    def favorites_provider():
        return fav.all()

    def tray_play_favorite(url: str):
        print(f"\n[fav] играем: {url}")
        last_url["value"] = url
        q.play_url(url)

    def tray_remove_favorite(url: str):
        if fav.remove_by_url(url):
            print(f"\n[fav] удалено: {url}")
            if tray_ref["obj"]:
                tray_ref["obj"].refresh_menu()

    def tray_save_playlist():
        ui_queue.put("save_playlist")

    def playlists_provider():
        return pls.all()

    def tray_play_playlist(url: str):
        print(f"\n[pls] играем плейлист: {url}")
        last_url["value"] = url
        q.play_url(url)

    def tray_remove_playlist(url: str):
        if pls.remove_by_url(url):
            print(f"\n[pls] удалён: {url}")
            if tray_ref["obj"]:
                tray_ref["obj"].refresh_menu()

    def tray_toggle_notifications():
        new_val = not notify.is_enabled()
        notify.set_enabled(new_val)
        print(f"\n[notify] {'включены' if new_val else 'выключены'}")

    def notifications_state():
        return notify.is_enabled()

    def tray_toggle_hotkeys():
        new_val = not bool(config.get("hotkeys_enabled", True))
        config.set("hotkeys_enabled", new_val)
        hotkeys_active["value"] = new_val
        print(f"\n[hotkeys] {'включены' if new_val else 'выключены'}")

    def hotkeys_state():
        return bool(config.get("hotkeys_enabled", True)) and hotkeys_active["value"]

    def tray_set_language(lang: str):
        i18n.set_language(lang)
        print(f"\n[i18n] язык: {lang}")
        if tray_ref["obj"]:
            tray_ref["obj"].rebuild_menu()

    def language_state():
        return str(config.get("language", "ru"))

    def tray_update_ytdlp():
        print("\n[ytdlp] обновляем…")
        notify.notify_info("Обновление yt-dlp…")

        def on_done(ok: bool, msg: str):
            print(f"\n[ytdlp] {msg}")
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
        on_save_playlist=tray_save_playlist,
        playlists_provider=playlists_provider,
        on_play_playlist=tray_play_playlist,
        on_remove_playlist=tray_remove_playlist,
        on_toggle_notifications=tray_toggle_notifications,
        notifications_state=notifications_state,
        on_toggle_hotkeys=tray_toggle_hotkeys,
        hotkeys_state=hotkeys_state,
        on_set_language=tray_set_language,
        language_state=language_state,
        on_update_ytdlp=tray_update_ytdlp,
    )
    tray_ref["obj"] = tray
    tray.start()

    _orig_on_track = q.on_track_changed

    def on_track_with_tray(track: Track):
        if _orig_on_track:
            _orig_on_track(track)
        tag = "LIVE" if track.is_live else "VOD"
        tray.set_title(f"[{tag}] {track.title}")

    q.on_track_changed = on_track_with_tray
    # --- конец трея ---

    print("Играем стартовый URL…")
    q.play_startup()

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
                print(f"volume → {int(config.get('volume', 100))}")
            elif cmd == "-":
                player.next_vol(-5)
                print(f"volume → {int(config.get('volume', 100))}")
            elif cmd == "m":
                player.toggle_mute()
                print("mute toggle")
            elif cmd.startswith("u "):
                url = cmd[2:].strip()
                if url:
                    last_url["value"] = url
                    q.play_url(url)
            else:
                print("Неизвестная команда")

    threading.Thread(target=input_loop, name="input", daemon=True).start()

    def process_ui_task(task: str) -> None:
        if task == "input_url":
            url = InputDialog.get_url("Играть ссылку")
            if url:
                print(f"\n[input] играем: {url}")
                last_url["value"] = url
                q.play_url(url)
        elif task == "save_playlist":
            url = last_url["value"]
            if not url:
                print("\n[pls] нет последней ссылки")
                return
            if not is_playlist_url(url):
                print(f"\n[pls] это не плейлист: {url}")
                return
            name = InputDialog.get_name("Имя плейлиста")
            if not name:
                return
            added = pls.add(name, url)
            if added:
                print(f"\n[pls] сохранён: {name} → {url}")
                if tray_ref["obj"]:
                    tray_ref["obj"].refresh_menu()
            else:
                print(f"\n[pls] уже есть плейлист с таким URL")

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