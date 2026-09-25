from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from config import config
from logging_setup import log

IS_WINDOWS = sys.platform.startswith("win")

def _resolve_bin(rel_path: str) -> Path:
    """Путь к бинарнику относительно папки exe/проекта."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent
    p = Path(rel_path)
    return p if p.is_absolute() else base / p

class MpvPlayer:
    def __init__(self) -> None:
        self.proc: Optional[subprocess.Popen] = None
        self.ipc_path: str = ""
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_reader = threading.Event()
        self._lock = threading.Lock()
        self._restart_times: list[float] = []

        self.on_end_file: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_title: Optional[Callable[[str], None]] = None
        self.on_time: Optional[Callable[[float, float], None]] = None

        self._current_title: str = ""
        self._volume: int = int(config.get("volume", 100))

        self._start()

    # ------------------------------------------------------------------ запуск

    def _start(self) -> None:
        mpv_exe = _resolve_bin(config.get("mpv_path", "bin/mpv/mpv.exe"))
        if not mpv_exe.exists():
            raise FileNotFoundError(f"mpv не найден: {mpv_exe}")

        # синхронизируем сохранённую громкость перед запуском
        self._volume = max(0, min(150, int(config.get("volume", 100))))

        if IS_WINDOWS:
            self.ipc_path = rf"\\.\pipe\mpv-ytray-{os.getpid()}"
        else:
            self.ipc_path = f"/tmp/mpv-ytray-{os.getpid()}.sock"

        args = [
            str(mpv_exe),
            "--no-video",
            "--idle=yes",
            "--ytdl=no",
            "--cache=yes",
            "--cache-on-disk=no",
            "--cache-pause=no",
            "--demuxer-max-bytes=512M",
            "--demuxer-max-back-bytes=64M",
            "--demuxer-readahead-secs=60",
            "--network-timeout=60",
            "--save-position-on-quit=no",
            "--volume=" + str(self._volume),
            f"--input-ipc-server={self.ipc_path}",
            "--really-quiet",
        ]

        log.info("Запуск mpv: %s", " ".join(args))
        self.proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
        )

        self._wait_for_ipc(timeout=5.0)

        self._stop_reader.clear()
        self._reader_thread = threading.Thread(
            target=self._event_loop, name="mpv-events", daemon=True
        )
        self._reader_thread.start()

        self._subscribe_events()
        log.info("mpv запущен (pid=%s, ipc=%s)", self.proc.pid, self.ipc_path)

    def _wait_for_ipc(self, timeout: float = 5.0) -> None:
        end = time.time() + timeout
        last_err: Optional[Exception] = None
        while time.time() < end:
            try:
                self._open_conn().close()
                return
            except OSError as e:
                last_err = e
                time.sleep(0.05)
        raise RuntimeError(f"mpv IPC не поднялся за {timeout}s: {last_err}")

    # ------------------------------------------------------------------ сокет

    def _open_conn(self):
        if IS_WINDOWS:
            return open(self.ipc_path, "r+b", buffering=0)
        import socket
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.ipc_path)
        return s

    def _send(self, *args: Any) -> None:
        with self._lock:
            try:
                conn = self._open_conn()
            except OSError:
                log.debug("IPC недоступен, команда пропущена: %s", args)
                return
            try:
                payload = json.dumps({"command": list(args)}) + "\n"
                if IS_WINDOWS:
                    conn.write(payload.encode("utf-8"))
                    conn.flush()
                else:
                    conn.sendall(payload.encode("utf-8"))
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------ события

    def _subscribe_events(self) -> None:
        self._send("observe_property", 1, "media-title")
        self._send("observe_property", 2, "time-pos")
        self._send("observe_property", 3, "duration")
        self._send("observe_property", 4, "pause")

    def _event_loop(self) -> None:
        if IS_WINDOWS:
            self._event_loop_windows()
        else:
            self._event_loop_unix()

    def _event_loop_windows(self) -> None:
        while not self._stop_reader.is_set():
            try:
                with open(self.ipc_path, "rb", buffering=0) as f:
                    buf = b""
                    while not self._stop_reader.is_set():
                        chunk = f.read(4096)
                        if not chunk:
                            break
                        buf += chunk
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            if line.strip():
                                self._handle_event_line(line.decode("utf-8", "replace"))
            except OSError:
                time.sleep(0.2)

    def _event_loop_unix(self) -> None:
        import socket
        while not self._stop_reader.is_set():
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(self.ipc_path)
                buf = b""
                while not self._stop_reader.is_set():
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if line.strip():
                            self._handle_event_line(line.decode("utf-8", "replace"))
                s.close()
            except OSError:
                time.sleep(0.2)

    def _handle_event_line(self, line: str) -> None:
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            return

        event = evt.get("event")
        if event == "property-change":
            name = evt.get("name")
            data = evt.get("data")
            if name == "media-title" and isinstance(data, str):
                self._current_title = data
                if self.on_title:
                    try:
                        self.on_title(data)
                    except Exception:
                        log.exception("on_title")
        elif event == "end-file":
            reason = evt.get("reason", "")
            log.debug("mpv end-file, reason=%s", reason)
            if self.on_end_file:
                try:
                    self.on_end_file(reason)
                except Exception:
                    log.exception("on_end_file")
        elif event == "start-file":
            log.debug("mpv start-file")

    # ------------------------------------------------------------------ API

    def play_url(self, url: str) -> None:
        log.info("mpv loadfile: %s", url[:120])
        self._send("loadfile", url, "replace")

    def pause(self) -> None:
        self._send("cycle", "pause")

    def set_pause(self, value: bool) -> None:
        self._send("set_property", "pause", bool(value))

    def stop(self) -> None:
        self._send("stop")

    def next_vol(self, delta: int) -> None:
        new_v = max(0, min(150, self._volume + int(delta)))
        self._volume = new_v
        self._send("set_property", "volume", new_v)
        config.set("volume", new_v)
        log.debug("volume → %s", new_v)

    def set_volume(self, v: int) -> None:
        v = max(0, min(150, int(v)))
        self._volume = v
        self._send("set_property", "volume", v)
        config.set("volume", v)
        log.debug("volume → %s", v)

    def get_volume(self) -> int:
        return self._volume

    def toggle_mute(self) -> None:
        self._send("cycle", "mute")

    def seek(self, seconds: int) -> None:
        self._send("seek", seconds)

    # ------------------------------------------------------------------ watchdog

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def ensure_alive(self) -> None:
        if self.is_alive():
            return

        now = time.time()
        self._restart_times = [t for t in self._restart_times if now - t < 600]
        if len(self._restart_times) >= 5:
            log.error("mpv падал 5 раз за 10 минут — перезапуск остановлен")
            if self.on_error:
                try:
                    self.on_error("mpv падает слишком часто, перезапуск остановлен")
                except Exception:
                    pass
            return

        self._restart_times.append(now)
        log.warning("mpv упал, перезапуск (%d/5)", len(self._restart_times))
        try:
            self._start()
            if self.on_error:
                try:
                    self.on_error("mpv перезапущен после падения")
                except Exception:
                    pass
        except Exception:
            log.exception("Не удалось перезапустить mpv")

    def shutdown(self) -> None:
        self._stop_reader.set()
        if self.proc and self.proc.poll() is None:
            try:
                self._send("quit")
            except Exception:
                pass
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        log.info("mpv остановлен")