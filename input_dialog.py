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

class InputDialog(QDialog):
    def __init__(self, title: str = "Введите ссылку", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(500)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        ip = _icon_path()
        if ip:
            self.setWindowIcon(QIcon(ip))

        layout = QVBoxLayout(self)

        self.label = QLabel("Вставьте ссылку на YouTube (трек, live, плейлист):")
        layout.addWidget(self.label)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("https://www.youtube.com/watch?v=...")
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

        self.result_url: Optional[str] = None

    # -------------------------------------------------------------- public

    @staticmethod
    def get_url(title: str = "Введите ссылку") -> Optional[str]:

        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        dlg = InputDialog(title=title)
        dlg.edit.setFocus()
        code = dlg.exec()

        result = dlg.edit.text().strip() if code == QDialog.Accepted else None
        log.info("InputDialog.get_url результат: %r", result)
        return result or None

    @staticmethod
    def get_name(title: str = "Имя плейлиста", default: str = "") -> Optional[str]:
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        dlg = InputDialog(title=title)
        dlg.label.setText("Введите имя плейлиста:")
        dlg.edit.setPlaceholderText("Мой любимый плейлист")
        if default:
            dlg.edit.setText(default)
        dlg.edit.setFocus()
        dlg.edit.selectAll()

        code = dlg.exec()
        result = dlg.edit.text().strip() if code == QDialog.Accepted else None
        log.info("InputDialog.get_name результат: %r", result)
        return result or None