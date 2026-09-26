from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from config import config
from logging_setup import log

IS_WINDOWS = sys.platform.startswith("win")

try:
    import win32file
    import pywintypes
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

FILE_FLAG_OVERLAPPED = 0x40000000

def _resolve_bin(rel_path: str) -> Path:
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
        self._handle = None
        self._reader_thread: Optional[threading.Thread] = None
        self._writer_thread: Optional[threading.Thread] = None
        self._output_thread: Optional[threading.Thread] = None
        self._write_queue: "queue.Queue[Optional[bytes]]" = queue.Queue()
        self._stop_reader = threading.Event()
        self._restart_times: list[float] = []

        self.on_end_file: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_title: Optional[Callable[[str], None]] = None

        self._current_title: str = ""
        self._volume: int = int(config.get("volume", 100))
        self._last_loadfile: Optional[str] = None

        self._start()

    # ------------------------------------------------------------------ запуск

    def _start(self) -> None:
        mpv_exe = _resolve_bin(config.get("mpv_path", "bin/mpv/mpv.exe"))
        if not mpv_exe.exists():
            raise FileNotFoundError(f"mpv не найден: {mpv_exe}")

        self._volume = max(0, min(150, int(config.get("volume", 100))))

        if IS_WINDOWS:
            self.ipc_path = rf"\\.\pipe\mpv-ytray-{os.getpid()}"
        else:
            self.ipc_path = f"/tmp/mpv-ytray-{os.getpid()}.sock"
            try:
                os.unlink(self.ipc_path)
            except OSError:
                pass

        args = [
            str(mpv_exe),
            "--no-video",
            "--idle=yes",
            "--ytdl=no",
            "--cache=yes",
            "--cache-on-disk=no",
            "--cache-pause=no",
            "--demuxer-max-bytes=128M",
            "--demuxer-max-back-bytes=16M",
            "--demuxer-readahead-secs=20",
            "--network-timeout=60",
            "--save-position-on-quit=no",
            "--msg-level=ao=info,all=warn",
            "--volume=" + str(self._volume),
            f"--input-ipc-server={self.ipc_path}",
        ]

        log.info("Запуск mpv: %s", " ".join(args))
        self.proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        self._stop_reader.clear()
        self._write_queue = queue.Queue()

        self._output_thread = threading.Thread(
            target=self._mpv_output_loop, name="mpv-output", daemon=True
        )
        self._output_thread.start()

        self._open_conn_with_retry(timeout=10.0)

        self._writer_thread = threading.Thread(
            target=self._write_loop, name="mpv-writer", daemon=True
        )
        self._writer_thread.start()

        self._reader_thread = threading.Thread(
            target=self._event_loop, name="mpv-events", daemon=True
        )
        self._reader_thread.start()

        self._subscribe_events()
        log.info("mpv запущен (pid=%s, ipc=%s)", self.proc.pid, self.ipc_path)

    def _mpv_output_loop(self) -> None:
        if not self.proc or not self.proc.stdout:
            return
        try:
            for line in self.proc.stdout:
                line = line.rstrip()
                if line:
                    log.info("mpv> %s", line)
        except Exception:
            pass

    def _open_conn_with_retry(self, timeout: float = 10.0) -> None:
        end = time.time() + timeout
        last_err: Optional[Exception] = None
        attempt = 0
        while time.time() < end:
            attempt += 1
            try:
                if IS_WINDOWS and HAS_WIN32:
                    self._handle = win32file.CreateFile(
                        self.ipc_path,
                        win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                        0,
                        None,
                        win32file.OPEN_EXISTING,
                        FILE_FLAG_OVERLAPPED,
                        None,
                    )
                else:
                    import socket
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.connect(self.ipc_path)
                    self._handle = s
                log.info("IPC подключён (попытка %d)", attempt)
                return
            except Exception as e:
                last_err = e
                if attempt <= 3 or attempt % 5 == 0:
                    log.warning("IPC попытка %d: %s", attempt, e)
                time.sleep(0.3)
        raise RuntimeError(f"mpv IPC не открылся за {timeout}s: {last_err}")

    def _close_conn(self) -> None:
        try:
            if self._handle is not None:
                if IS_WINDOWS and HAS_WIN32:
                    win32file.CloseHandle(self._handle)
                else:
                    self._handle.close()
        except Exception:
            pass
        self._handle = None

    # ------------------------------------------------------------------ запись (очередь)

    def _write_loop(self) -> None:
        while not self._stop_reader.is_set():
            try:
                payload = self._write_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if payload is None:
                break
            handle = self._handle
            if handle is None:
                continue
            try:
                if IS_WINDOWS and HAS_WIN32:
                    win32file.WriteFile(handle, payload)
                else:
                    handle.sendall(payload)
                log.debug("writer: OK")
            except Exception as e:
                log.warning("Ошибка IPC write: %s", e)
        log.debug("writer завершён")

    def _send(self, *args: Any) -> None:
        if self._handle is None:
            return
        payload = (json.dumps({"command": list(args)}) + "\n").encode("utf-8")
        log.info("IPC → %s", args)
        try:
            self._write_queue.put(payload)
        except Exception as e:
            log.warning("Ошибка постановки в очередь: %s", e)

    def _subscribe_events(self) -> None:
        self._send("observe_property", 1, "media-title")
        self._send("observe_property", 2, "time-pos")
        self._send("observe_property", 3, "duration")
        self._send("observe_property", 4, "pause")

    # ------------------------------------------------------------------ чтение

    def _event_loop(self) -> None:
        if IS_WINDOWS and HAS_WIN32:
            self._event_loop_windows()
        else:
            self._event_loop_unix()

    def _event_loop_windows(self) -> None:
        buf = b""
        while not self._stop_reader.is_set():
            handle = self._handle
            if handle is None:
                time.sleep(0.2)
                continue
            try:
                err, data = win32file.ReadFile(handle, 4096)
                if data:
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if line.strip():
                            self._handle_event_line(line.decode("utf-8", "replace"))
                else:
                    time.sleep(0.05)
            except pywintypes.error as e:
                if e.winerror == 997:
                    time.sleep(0.05)
                    continue
                log.debug("IPC read: %s", e)
                time.sleep(0.3)
            except Exception as e:
                log.debug("IPC read: %s", e)
                time.sleep(0.3)

    def _event_loop_unix(self) -> None:
        buf = b""
        while not self._stop_reader.is_set():
            handle = self._handle
            if handle is None:
                time.sleep(0.2)
                continue
            try:
                chunk = handle.recv(4096)
                if not chunk:
                    time.sleep(0.05)
                    continue
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line.strip():
                        self._handle_event_line(line.decode("utf-8", "replace"))
            except OSError as e:
                log.debug("IPC recv: %s", e)
                time.sleep(0.3)

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
                log.info("mpv media-title: %s", data)
                if self.on_title:
                    try:
                        self.on_title(data)
                    except Exception:
                        log.exception("on_title")
        elif event == "end-file":
            reason = evt.get("reason", "")
            log.info("mpv end-file, reason=%s", reason)
            if self.on_end_file:
                try:
                    self.on_end_file(reason)
                except Exception:
                    log.exception("on_end_file")

    # ------------------------------------------------------------------ API

    def play_url(self, url: str) -> None:
        log.info("mpv loadfile (полный): %s", url)
        self._last_loadfile = url
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

    def set_volume(self, v: int) -> None:
        v = max(0, min(150, int(v)))
        self._volume = v
        self._send("set_property", "volume", v)
        config.set("volume", v)

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
        if not self.is_alive():
            log.warning("mpv не жив — перезапуск")
            self._restart_mpv("процесс упал")

    def _restart_mpv(self, reason: str) -> None:
        now = time.time()
        self._restart_times = [t for t in self._restart_times if now - t < 600]
        if len(self._restart_times) >= 5:
            log.error("mpv перезапускается слишком часто — стоп")
            if self.on_error:
                try:
                    self.on_error("mpv падает слишком часто, перезапуск остановлен")
                except Exception:
                    pass
            return

        self._restart_times.append(now)
        log.warning("Перезапуск mpv (%s), попытка %d/5", reason, len(self._restart_times))

        self._stop_reader.set()
        try:
            self._write_queue.put_nowait(None)
        except Exception:
            pass
        self._close_conn()

        try:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
                self.proc.wait(timeout=2)
        except Exception:
            pass

        try:
            self._start()
            if self._last_loadfile:
                log.info("Восстанавливаем трек после перезапуска mpv")
                self._send("loadfile", self._last_loadfile, "replace")
        except Exception:
            log.exception("Не удалось перезапустить mpv")

    def shutdown(self) -> None:
        self._stop_reader.set()
        try:
            if self.proc and self.proc.poll() is None:
                self._send("quit")
                time.sleep(0.3)
                try:
                    self.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
        except Exception:
            pass
        try:
            self._write_queue.put_nowait(None)
        except Exception:
            pass
        self._close_conn()
        log.info("mpv остановлен")