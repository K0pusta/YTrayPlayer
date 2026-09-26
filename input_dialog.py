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
    QPushButton,
    QVBoxLayout,
)

from logging_setup import log

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

class InputDialog(QDialog):

    def __init__(self, title: str = "Введите", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(500)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        ip = _icon_path()
        if ip:
            self.setWindowIcon(QIcon(ip))

        layout = QVBoxLayout(self)

        self.label = QLabel("Введите значение:")
        layout.addWidget(self.label)

        self.edit = QLineEdit()
        layout.addWidget(self.edit)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setDefault(True)
        self.btn_cancel = QPushButton("Отмена")
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        layout.addLayout(btns)

        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        self.edit.returnPressed.connect(self.accept)

    @staticmethod
    def get_url(title: str = "Введите ссылку") -> Optional[str]:
        _ensure_app()
        dlg = InputDialog(title=title)
        dlg.label.setText("Вставьте ссылку на YouTube (трек, live, плейлист):")
        dlg.edit.setPlaceholderText("https://www.youtube.com/watch?v=...")
        dlg.edit.setFocus()
        code = dlg.exec()
        result = dlg.edit.text().strip() if code == QDialog.Accepted else None
        log.info("InputDialog.get_url: %r", result)
        return result or None

    @staticmethod
    def get_name(title: str = "Имя", prompt: str = "Введите имя:",
                 default: str = "") -> Optional[str]:
        _ensure_app()
        dlg = InputDialog(title=title)
        dlg.label.setText(prompt)
        if default:
            dlg.edit.setText(default)
        dlg.edit.setFocus()
        dlg.edit.selectAll()
        code = dlg.exec()
        result = dlg.edit.text().strip() if code == QDialog.Accepted else None
        log.info("InputDialog.get_name: %r", result)
        return result or None

class PlaylistPickerDialog(QDialog):

    def __init__(self, playlists: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Добавить в плейлист")
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        ip = _icon_path()
        if ip:
            self.setWindowIcon(QIcon(ip))

        layout = QVBoxLayout(self)

        lbl = QLabel("Выберите плейлист:")
        layout.addWidget(lbl)

        self.list = QListWidget()
        self._playlists = [p for p in playlists if p.get("type") == "user"]
        for p in self._playlists:
            name = p.get("name", "?")
            cnt = len(p.get("tracks", []))
            item = QListWidgetItem(f"{name}  ({cnt})")
            item.setData(Qt.UserRole, name)
            self.list.addItem(item)
        if self._playlists:
            self.list.setCurrentRow(0)
        layout.addWidget(self.list)

        self.btn_new = QPushButton("+ Создать новый плейлист…")
        layout.addWidget(self.btn_new)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setDefault(True)
        self.btn_cancel = QPushButton("Отмена")
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        layout.addLayout(btns)

        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_new.clicked.connect(self._on_new)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())

        self.selected_name: Optional[str] = None
        self.create_new: bool = False

    def _on_new(self) -> None:
        self.create_new = True
        self.accept()

    def accept(self) -> None:
        if not self.create_new:
            item = self.list.currentItem()
            if item is None:
                return
            self.selected_name = item.data(Qt.UserRole)
        super().accept()

    @staticmethod
    def pick(playlists: list[dict]) -> tuple[Optional[str], bool]:
        _ensure_app()
        dlg = PlaylistPickerDialog(playlists)
        code = dlg.exec()
        if code != QDialog.Accepted:
            return (None, False)
        return (dlg.selected_name, dlg.create_new)