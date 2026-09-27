from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logging_setup import log
from playlists import Playlists

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

class PlaylistEditorDialog(QDialog):
    def __init__(self, pls: Playlists, playlist_name: str, parent=None) -> None:
        super().__init__(parent)
        self.pls = pls
        self.original_name = playlist_name
        self.current_name = playlist_name

        self.tracks: list[dict] = []
        item = pls.get(playlist_name)
        if item and item.get("type") == "user":
            for t in item.get("tracks", []):
                self.tracks.append(dict(t))

        self.result_data: Optional[dict] = None

        self.setWindowTitle(f"Редактор плейлиста — {playlist_name}")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        ip = _icon_path()
        if ip:
            self.setWindowIcon(QIcon(ip))

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Плейлист:"))
        self.lbl_name = QLabel(f"<b>{playlist_name}</b>")
        top.addWidget(self.lbl_name, 1)
        self.btn_rename = QPushButton("Переименовать")
        self.btn_rename.clicked.connect(self._on_rename)
        top.addWidget(self.btn_rename)
        layout.addLayout(top)

        self.list = QListWidget()
        layout.addWidget(self.list, 1)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #888;")
        layout.addWidget(self.lbl_status)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.btn_cancel = QPushButton("Отмена")
        self.btn_ok = QPushButton("Сохранить")
        self.btn_ok.setDefault(True)
        bottom.addWidget(self.btn_cancel)
        bottom.addWidget(self.btn_ok)
        layout.addLayout(bottom)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._on_save)

        self._refresh_list()

    def _refresh_list(self) -> None:
        self.list.clear()

        if not self.tracks:
            item = QListWidgetItem("(плейлист пуст)")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.list.addItem(item)
            self.lbl_status.setText("0 треков")
            return

        for idx, t in enumerate(self.tracks):
            widget = self._make_row(t, idx)
            list_item = QListWidgetItem(self.list)
            list_item.setSizeHint(widget.sizeHint())
            self.list.addItem(list_item)
            self.list.setItemWidget(list_item, widget)

        self.lbl_status.setText(f"{len(self.tracks)} треков")

    def _make_row(self, track: dict, idx: int) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(8)

        title = track.get("title", "Unknown")
        is_live = track.get("is_live", False)
        uploader = track.get("uploader", "") or ""

        tag = "[LIVE] " if is_live else ""
        author = f" — {uploader}" if uploader else ""
        label_text = f"{tag}{title}{author}"

        lbl = QLabel(label_text)
        lbl.setWordWrap(False)
        h.addWidget(lbl, 1)

        btn_del = QPushButton("✕")
        btn_del.setFixedWidth(32)
        btn_del.setToolTip("Удалить трек (применится после «Сохранить»)")
        btn_del.clicked.connect(lambda _=False, i=idx: self._on_remove(i))
        h.addWidget(btn_del)

        return w

    def _on_remove(self, idx: int) -> None:
        if 0 <= idx < len(self.tracks):
            removed = self.tracks.pop(idx)
            log.info("Помечен на удаление: %s", removed.get("title"))
            self._refresh_list()

    def _on_rename(self) -> None:
        dlg = _RenameDialog(self.current_name, self)
        if dlg.exec() == QDialog.Accepted and dlg.new_name:
            new_name = dlg.new_name
            if new_name == self.current_name:
                return
            existing = self.pls.get(new_name)
            if existing is not None:
                QMessageBox.warning(self, "Ошибка", f"Имя «{new_name}» уже занято")
                return
            self.current_name = new_name
            self.lbl_name.setText(f"<b>{new_name}</b>")
            self.setWindowTitle(f"Редактор плейлиста — {new_name}")

    def _on_save(self) -> None:
        renamed = self.current_name != self.original_name
        result = {
            "name_old": self.original_name,
            "name_new": self.current_name,
            "renamed": renamed,
            "tracks": list(self.tracks),
        }
        self.result_data = result
        self.accept()

    @staticmethod
    def pick(pls: Playlists, name: str) -> Optional[dict]:
        _ensure_app()
        dlg = PlaylistEditorDialog(pls, name)
        code = dlg.exec()
        if code != QDialog.Accepted:
            return None
        return dlg.result_data

class _RenameDialog(QDialog):
    def __init__(self, current: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Переименовать плейлист")
        self.setMinimumWidth(360)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        self.new_name: Optional[str] = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Новое имя плейлиста:"))

        self.edit = QLineEdit()
        self.edit.setText(current)
        self.edit.selectAll()
        layout.addWidget(self.edit)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btn_ok = QPushButton("OK")
        btn_ok.setDefault(True)
        btn_cancel = QPushButton("Отмена")
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

        btn_ok.clicked.connect(self._on_ok)
        btn_cancel.clicked.connect(self.reject)
        self.edit.returnPressed.connect(self._on_ok)

    def _on_ok(self) -> None:
        name = self.edit.text().strip()
        if not name:
            return
        self.new_name = name
        self.accept()