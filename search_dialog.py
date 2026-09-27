from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import Qt, QObject, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from logging_setup import log
from youtube import Track, search

def _icon_path() -> Optional[str]:
    from pathlib import Path
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent
    p = base / "assets" / "icon.ico"
    return str(p) if p.exists() else None

def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app

def _format_duration(seconds: Optional[float]) -> str:
    if not seconds:
        return ""
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

class _SearchWorker(QObject):
    finished = Signal(list)   # list[Track]
    error = Signal(str)

    def __init__(self, query: str, limit: int) -> None:
        super().__init__()
        self.query = query
        self.limit = limit

    def run(self) -> None:
        try:
            log.info("Поиск: %r (limit=%d)", self.query, self.limit)
            tracks = search(self.query, limit=self.limit)
            log.info("Поиск: найдено %d", len(tracks))
            self.finished.emit(tracks)
        except Exception as e:
            log.exception("Поиск упал")
            self.error.emit(str(e))


# --- окно поиска -------------------------------------------------------------

class SearchDialog(QDialog):
    LIMIT = 10

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Поиск на YouTube")
        self.setMinimumWidth(600)
        self.setMinimumHeight(450)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        ip = _icon_path()
        if ip:
            self.setWindowIcon(QIcon(ip))

        self.selected_track: Optional[Track] = None
        self._thread: Optional[QThread] = None
        self._worker: Optional[_SearchWorker] = None

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Введите запрос (например, lofi hip hop)…")
        self.btn_search = QPushButton("Найти")
        top.addWidget(self.edit, 1)
        top.addWidget(self.btn_search)
        layout.addLayout(top)

        self.status = QLabel("")
        layout.addWidget(self.status)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._on_item_activated)
        layout.addWidget(self.list, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.btn_ok = QPushButton("Играть")
        self.btn_ok.setEnabled(False)
        self.btn_cancel = QPushButton("Отмена")
        bottom.addWidget(self.btn_cancel)
        bottom.addWidget(self.btn_ok)
        layout.addLayout(bottom)

        self.btn_search.clicked.connect(self._start_search)
        self.edit.returnPressed.connect(self._start_search)
        self.btn_ok.clicked.connect(self._on_ok)
        self.btn_cancel.clicked.connect(self.reject)
        self.list.itemSelectionChanged.connect(self._on_selection_changed)

    # -------------------------------------------------------------- поиск

    def _start_search(self) -> None:
        query = self.edit.text().strip()
        if not query:
            return

        self.list.clear()
        self.status.setText("Поиск…")
        self.btn_search.setEnabled(False)
        self.btn_ok.setEnabled(False)

        self._thread = QThread()
        self._worker = _SearchWorker(query, self.LIMIT)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_search_finished)
        self._worker.error.connect(self._on_search_error)

        self._thread.start()

    def _on_search_finished(self, tracks: list) -> None:
        self._cleanup_thread()
        self.btn_search.setEnabled(True)

        if not tracks:
            self.status.setText("Ничего не найдено — попробуйте другой запрос")
            return

        self.status.setText(f"Найдено: {len(tracks)}")

        for t in tracks:
            tag = "[LIVE] " if t.is_live else ""
            dur = _format_duration(t.duration)
            dur_part = f"  ({dur})" if dur else ""
            author = f" — {t.uploader}" if t.uploader else ""
            label = f"{tag}{t.title}{author}{dur_part}"

            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, t)
            self.list.addItem(item)

    def _on_search_error(self, msg: str) -> None:
        self._cleanup_thread()
        self.btn_search.setEnabled(True)
        self.status.setText(f"Ошибка: {msg}")

    def _cleanup_thread(self) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
        self._thread = None
        self._worker = None

    # -------------------------------------------------------------- выбор

    def _on_selection_changed(self) -> None:
        self.btn_ok.setEnabled(self.list.currentItem() is not None)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        track: Track = item.data(Qt.UserRole)
        if track:
            self.selected_track = track
            self.accept()

    def _on_ok(self) -> None:
        item = self.list.currentItem()
        if not item:
            return
        self.selected_track = item.data(Qt.UserRole)
        self.accept()

    # -------------------------------------------------------------- закрытие

    def closeEvent(self, event) -> None:
        self._cleanup_thread()
        super().closeEvent(event)

    # -------------------------------------------------------------- public

    @staticmethod
    def pick() -> Optional[Track]:
        _ensure_app()
        dlg = SearchDialog()
        dlg.edit.setFocus()
        code = dlg.exec()
        if code != QDialog.Accepted:
            return None
        return dlg.selected_track