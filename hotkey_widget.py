from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLabel, QPushButton

from logging_setup import log

MOD_ALT     = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT   = 0x0004
MOD_WIN     = 0x0008

# --- Qt modifiers -> WinAPI --------------------------------------------------

def _qt_mods_to_win(qt_mods: Qt.KeyboardModifier) -> int:
    out = 0
    if qt_mods & Qt.ControlModifier:
        out |= MOD_CONTROL
    if qt_mods & Qt.AltModifier:
        out |= MOD_ALT
    if qt_mods & Qt.ShiftModifier:
        out |= MOD_SHIFT
    if qt_mods & Qt.MetaModifier:
        out |= MOD_WIN
    return out

# --- Qt key -> VK ------------------------------------------------------------

_QT_KEY_TO_VK: dict[int, int] = {
    int(Qt.Key_Escape):       0x1B,
    int(Qt.Key_Tab):          0x09,
    int(Qt.Key_Backspace):    0x08,
    int(Qt.Key_Return):       0x0D,
    int(Qt.Key_Enter):        0x0D,
    int(Qt.Key_Insert):       0x2D,
    int(Qt.Key_Delete):       0x2E,
    int(Qt.Key_Home):         0x24,
    int(Qt.Key_End):          0x23,
    int(Qt.Key_PageUp):       0x21,
    int(Qt.Key_PageDown):     0x22,
    int(Qt.Key_Left):         0x25,
    int(Qt.Key_Up):           0x26,
    int(Qt.Key_Right):        0x27,
    int(Qt.Key_Down):         0x28,
    int(Qt.Key_Space):        0x20,
    int(Qt.Key_CapsLock):     0x14,
    int(Qt.Key_NumLock):      0x90,
    int(Qt.Key_ScrollLock):   0x91,
    int(Qt.Key_Pause):        0x13,
    int(Qt.Key_Print):        0x2C,
    int(Qt.Key_Minus):        0xBD,   # OEM minus
    int(Qt.Key_Equal):        0xBB,   # OEM plus
    int(Qt.Key_BracketLeft):  0xDB,   # [
    int(Qt.Key_BracketRight): 0xDD,   # ]
    int(Qt.Key_Backslash):    0xDC,   # \
    int(Qt.Key_Semicolon):    0xBA,   # ;
    int(Qt.Key_Apostrophe):   0xDE,   # '
    int(Qt.Key_Comma):        0xBC,   # ,
    int(Qt.Key_Period):       0xBE,   # .
    int(Qt.Key_Slash):        0xBF,   # /
    int(Qt.Key_QuoteLeft):    0xC0,   # `
}

def _qt_key_to_vk(qt_key: int) -> Optional[int]:
    # A-Z
    if int(Qt.Key_A) <= qt_key <= int(Qt.Key_Z):
        return 0x41 + (qt_key - int(Qt.Key_A))
    # 0-9 (верхние цифры)
    if int(Qt.Key_0) <= qt_key <= int(Qt.Key_9):
        return 0x30 + (qt_key - int(Qt.Key_0))
    # F1-F24
    if int(Qt.Key_F1) <= qt_key <= int(Qt.Key_F24):
        return 0x70 + (qt_key - int(Qt.Key_F1))
    # Numpad 0-9
    if int(Qt.Key_0) + 0x100000 <= qt_key <= int(Qt.Key_9) + 0x100000:
        pass
    return _QT_KEY_TO_VK.get(qt_key)

# --- Валидация ---------------------------------------------------------------

_VALID_MAIN_KEYS = (
    set(range(0x41, 0x5B)) |   # A-Z
    set(range(0x30, 0x3A)) |   # 0-9
    set(range(0x70, 0x88)) |   # F1-F24
    {0x20, 0x09, 0x0D, 0x1B,    # Space, Tab, Enter, Esc
     0x25, 0x26, 0x27, 0x28,    # стрелки
     0x24, 0x23, 0x21, 0x22,    # Home, End, PageUp, PageDown
     0x2D, 0x2E,                # Ins, Del
     0xBD, 0xBB, 0xDB, 0xDD, 0xDC, 0xBA, 0xDE, 0xBC, 0xBE, 0xBF, 0xC0}
)

def is_valid_hotkey(mods: int, key: int) -> tuple[bool, str]:
    if mods == 0:
        return False, "Нужен хотя бы один модификатор (Ctrl, Alt, Shift или Win)"
    if key not in _VALID_MAIN_KEYS:
        return False, "Эта клавиша не поддерживается для хоткеев"
    return True, ""


# --- Виджет ------------------------------------------------------------------

class HotkeyEdit(QPushButton):

    changed = Signal(int, int)  # (mods, key)

    def __init__(self, mods: int, key: int) -> None:
        super().__init__()
        self._mods = mods
        self._key = key
        self._capturing = False
        self._update_text()
        self.clicked.connect(self._on_click)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumWidth(180)

    # ---------------------------------------------------------- public

    def set_hotkey(self, mods: int, key: int) -> None:
        self._mods = mods
        self._key = key
        self._update_text()

    def get_hotkey(self) -> tuple[int, int]:
        return self._mods, self._key

    # ---------------------------------------------------------- клик / захват

    def _on_click(self) -> None:
        self._capturing = True
        self.setText("Нажмите комбинацию…")
        self.setFocus()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._capturing:
            super().keyPressEvent(event)
            return

        if event.key() == Qt.Key_Escape:
            self._capturing = False
            self._update_text()
            return

        if event.key() in (
            Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta,
            Qt.Key_AltGr, Qt.Key_unknown,
        ):
            return

        mods = _qt_mods_to_win(event.modifiers())
        key = _qt_key_to_vk(int(event.key()))

        if key is None:
            self.setText("Не поддерживается — попробуйте другую")
            return

        ok, reason = is_valid_hotkey(mods, key)
        if not ok:
            self.setText(reason)
            return

        self._mods = mods
        self._key = key
        self._capturing = False
        self._update_text()
        self.changed.emit(mods, key)

    def focusOutEvent(self, event) -> None:
        if self._capturing:
            self._capturing = False
            self._update_text()
        super().focusOutEvent(event)

    # ---------------------------------------------------------- отображение

    def _update_text(self) -> None:
        from hotkeys import vk_to_string
        self.setText(vk_to_string(self._mods, self._key))