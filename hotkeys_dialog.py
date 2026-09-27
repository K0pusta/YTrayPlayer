from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config import config, HOTKEY_DESCRIPTIONS
from hotkey_widget import HotkeyEdit
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

class HotkeysDialog(QDialog):

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Настройка хоткеев")
        self.setMinimumWidth(560)
        self.setMinimumHeight(500)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        ip = _icon_path()
        if ip:
            self.setWindowIcon(QIcon(ip))

        self.result_hotkeys: Optional[dict] = None

        cur = config.get("hotkeys", {}) or {}
        self._current: dict[str, dict] = {}
        for name in HOTKEY_DESCRIPTIONS:
            spec = cur.get(name, {})
            self._current[name] = {
                "mods": int(spec.get("mods", 0)),
                "key": int(spec.get("key", 0)),
                "enabled": bool(spec.get("enabled", True)),
            }

        from config import DEFAULTS
        self._defaults: dict[str, dict] = {}
        for name, spec in DEFAULTS.get("hotkeys", {}).items():
            self._defaults[name] = {
                "mods": int(spec["mods"]),
                "key": int(spec["key"]),
                "enabled": bool(spec.get("enabled", True)),
            }

        self._edits: dict[str, HotkeyEdit] = {}
        self._checks: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)

        header = QLabel(
            "Нажмите на комбинацию, чтобы изменить её. "
            "Esc — отмена изменения. Нужен минимум один модификатор (Ctrl/Alt/Shift/Win)."
        )
        header.setWordWrap(True)
        header.setStyleSheet("color: #aaa; margin-bottom: 6px;")
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)

        grid.addWidget(self._bold(QLabel("Действие")), 0, 0)
        grid.addWidget(self._bold(QLabel("Комбинация")), 0, 1)
        grid.addWidget(self._bold(QLabel("Вкл")), 0, 2)
        grid.addWidget(self._bold(QLabel("Сброс")), 0, 3)

        row = 1
        for name, description in HOTKEY_DESCRIPTIONS.items():
            spec = self._current[name]

            lbl = QLabel(description)

            edit = HotkeyEdit(spec["mods"], spec["key"])
            self._edits[name] = edit

            chk = QCheckBox()
            chk.setChecked(spec["enabled"])
            self._checks[name] = chk

            btn_reset = QPushButton("Сброс")
            btn_reset.setFixedWidth(80)
            btn_reset.clicked.connect(
                lambda _=False, n=name: self._on_reset(n)
            )

            grid.addWidget(lbl, row, 0)
            grid.addWidget(edit, row, 1)
            grid.addWidget(chk, row, 2, alignment=Qt.AlignCenter)
            grid.addWidget(btn_reset, row, 3)
            row += 1

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)

        btn_reset_all = QPushButton("Сбросить всё")
        btn_reset_all.clicked.connect(self._on_reset_all)
        bottom.addWidget(btn_reset_all)

        bottom.addSpacing(20)

        self.btn_cancel = QPushButton("Отмена")
        self.btn_ok = QPushButton("Сохранить")
        self.btn_ok.setDefault(True)
        bottom.addWidget(self.btn_cancel)
        bottom.addWidget(self.btn_ok)
        layout.addLayout(bottom)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._on_save)

    # ---------------------------------------------------------- public

    @staticmethod
    def pick() -> Optional[dict]:
        _ensure_app()
        dlg = HotkeysDialog()
        code = dlg.exec()
        if code != QDialog.Accepted:
            return None
        return dlg.result_hotkeys

    # ---------------------------------------------------------- callbacks

    def _on_reset(self, name: str) -> None:
        d = self._defaults.get(name)
        if not d:
            return
        self._edits[name].set_hotkey(d["mods"], d["key"])
        self._checks[name].setChecked(d["enabled"])

    def _on_reset_all(self) -> None:
        for name in HOTKEY_DESCRIPTIONS:
            self._on_reset(name)

    def _on_save(self) -> None:
        out: dict[str, dict] = {}
        for name in HOTKEY_DESCRIPTIONS:
            mods, key = self._edits[name].get_hotkey()
            enabled = self._checks[name].isChecked()
            out[name] = {"mods": mods, "key": key, "enabled": enabled}
        self.result_hotkeys = out
        self.accept()

    # ---------------------------------------------------------- util

    @staticmethod
    def _bold(lbl: QLabel) -> QLabel:
        f = lbl.font()
        f.setBold(True)
        lbl.setFont(f)
        return lbl