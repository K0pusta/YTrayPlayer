from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import config, DEFAULTS, HOTKEY_DESCRIPTIONS
from hotkey_widget import HotkeyEdit
from logging_setup import log

APP_VERSION = "1.2.0"
GITHUB_URL = "https://github.com/K0pusta/YTrayPlayer"

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

class SettingsDialog(QDialog):

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(620)
        self.setMinimumHeight(560)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        ip = _icon_path()
        if ip:
            self.setWindowIcon(QIcon(ip))

        self.result_data: Optional[dict] = None

        self._current_lang = str(config.get("language", "ru"))
        self._current_notif = bool(config.get("notifications", True))
        self._current_discord = bool(config.get("discord_rpc", True))

        cur_hotkeys = config.get("hotkeys", {}) or {}
        self._current_hotkeys: dict[str, dict] = {}
        for name in HOTKEY_DESCRIPTIONS:
            spec = cur_hotkeys.get(name, {})
            self._current_hotkeys[name] = {
                "mods": int(spec.get("mods", 0)),
                "key": int(spec.get("key", 0)),
                "enabled": bool(spec.get("enabled", True)),
            }

        self._default_hotkeys: dict[str, dict] = {}
        for name, spec in DEFAULTS.get("hotkeys", {}).items():
            self._default_hotkeys[name] = {
                "mods": int(spec["mods"]),
                "key": int(spec["key"]),
                "enabled": bool(spec.get("enabled", True)),
            }

        self._hotkey_edits: dict[str, HotkeyEdit] = {}
        self._hotkey_checks: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._build_tab_general(), "Общие")
        tabs.addTab(self._build_tab_hotkeys(), "Хоткеи")
        tabs.addTab(self._build_tab_about(), "О программе")
        layout.addWidget(tabs, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        btn_cancel = QPushButton("Отмена")
        btn_ok = QPushButton("Сохранить")
        btn_ok.setDefault(True)
        bottom.addWidget(btn_cancel)
        bottom.addWidget(btn_ok)
        layout.addLayout(bottom)

        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._on_save)

    # ---------------------------------------------------------- вкладки

    def _build_tab_general(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(12)

        # Язык
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Язык:"))
        self.cmb_lang = QComboBox()
        self.cmb_lang.addItem("Русский", "ru")
        self.cmb_lang.addItem("English", "en")
        idx = 0 if self._current_lang == "ru" else 1
        self.cmb_lang.setCurrentIndex(idx)
        self.cmb_lang.setFixedWidth(180)
        lang_row.addWidget(self.cmb_lang)
        lang_row.addStretch(1)
        v.addLayout(lang_row)

        self.chk_notifications = QCheckBox("Показывать уведомления Windows")
        self.chk_notifications.setChecked(self._current_notif)
        v.addWidget(self.chk_notifications)

        self.chk_discord = QCheckBox("Показывать трек в Discord (Rich Presence)")
        self.chk_discord.setChecked(self._current_discord)
        v.addWidget(self.chk_discord)

        v.addStretch(1)

        hint = QLabel(
            "Изменения применятся сразу после нажатия «Сохранить». "
            "Некоторые параметры (язык) подхватятся без перезапуска плеера."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")
        v.addWidget(hint)

        return w

    def _build_tab_hotkeys(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(8)

        header = QLabel(
            "Нажмите на комбинацию, чтобы изменить её. Esc — отмена изменения. "
            "Нужен минимум один модификатор (Ctrl, Alt, Shift или Win)."
        )
        header.setWordWrap(True)
        header.setStyleSheet("color: #aaa; margin-bottom: 6px;")
        v.addWidget(header)

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
            spec = self._current_hotkeys[name]

            lbl = QLabel(description)

            edit = HotkeyEdit(spec["mods"], spec["key"])
            self._hotkey_edits[name] = edit

            chk = QCheckBox()
            chk.setChecked(spec["enabled"])
            self._hotkey_checks[name] = chk

            btn_reset = QPushButton("Сброс")
            btn_reset.setFixedWidth(80)
            btn_reset.clicked.connect(lambda _=False, n=name: self._on_reset_hotkey(n))

            grid.addWidget(lbl, row, 0)
            grid.addWidget(edit, row, 1)
            grid.addWidget(chk, row, 2, alignment=Qt.AlignCenter)
            grid.addWidget(btn_reset, row, 3)
            row += 1

        scroll.setWidget(content)
        v.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        btn_reset_all = QPushButton("Сбросить всё к дефолтам")
        btn_reset_all.clicked.connect(self._on_reset_all_hotkeys)
        bottom.addWidget(btn_reset_all)
        bottom.addStretch(1)
        v.addLayout(bottom)

        return w

    def _build_tab_about(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(12)

        title = QLabel(f"<b>YTrayPlayer</b> v{APP_VERSION}")
        title.setStyleSheet("font-size: 16px;")
        v.addWidget(title)

        desc = QLabel(
            "Плеер YouTube-музыки в системном трее Windows.\n"
            "Играет треки, live-стримы, плейлисты и рекомендации. "
            "Управляется глобальными хоткеями."
        )
        desc.setWordWrap(True)
        v.addWidget(desc)

        github = QLabel(f'<a href="{GITHUB_URL}">{GITHUB_URL}</a>')
        github.setOpenExternalLinks(True)
        v.addWidget(github)

        v.addSpacing(12)

        btn_update = QPushButton("Обновить yt-dlp")
        btn_update.setFixedWidth(200)
        btn_update.clicked.connect(self._on_update_ytdlp)
        v.addWidget(btn_update)

        self.lbl_update_status = QLabel("")
        self.lbl_update_status.setStyleSheet("color: #888;")
        v.addWidget(self.lbl_update_status)

        v.addStretch(1)
        return w

    # ---------------------------------------------------------- callbacks

    def _on_reset_hotkey(self, name: str) -> None:
        d = self._default_hotkeys.get(name)
        if not d:
            return
        self._hotkey_edits[name].set_hotkey(d["mods"], d["key"])
        self._hotkey_checks[name].setChecked(d["enabled"])

    def _on_reset_all_hotkeys(self) -> None:
        for name in HOTKEY_DESCRIPTIONS:
            self._on_reset_hotkey(name)

    def _on_update_ytdlp(self) -> None:
        from youtube import update_ytdlp
        self.lbl_update_status.setText("Обновление…")

        def on_done(ok: bool, msg: str):
            self.lbl_update_status.setText(msg)

        update_ytdlp(on_done)

    def _on_save(self) -> None:
        data: dict = {}
        data["language"] = self.cmb_lang.currentData() or "ru"
        data["notifications"] = self.chk_notifications.isChecked()
        data["discord_rpc"] = self.chk_discord.isChecked()

        hotkeys: dict[str, dict] = {}
        for name in HOTKEY_DESCRIPTIONS:
            mods, key = self._hotkey_edits[name].get_hotkey()
            enabled = self._hotkey_checks[name].isChecked()
            hotkeys[name] = {"mods": mods, "key": key, "enabled": enabled}
        data["hotkeys"] = hotkeys

        self.result_data = data
        self.accept()

    # ---------------------------------------------------------- public

    @staticmethod
    def pick() -> Optional[dict]:
        _ensure_app()
        dlg = SettingsDialog()
        code = dlg.exec()
        if code != QDialog.Accepted:
            return None
        return dlg.result_data

    # ---------------------------------------------------------- util

    @staticmethod
    def _bold(lbl: QLabel) -> QLabel:
        f = lbl.font()
        f.setBold(True)
        lbl.setFont(f)
        return lbl