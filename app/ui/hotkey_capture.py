"""Captura de uma tecla ou botão adicional, sem precisar procurar em uma lista."""
from PyQt5.QtCore import Qt,QTimer,pyqtSignal
from PyQt5.QtWidgets import QWidget,QHBoxLayout,QPushButton,QLabel
from app.automation.input import InputHandler
from app.automation.hotkeys import HOTKEY_CODES,hotkey_name

class HotkeyCapture(QWidget):
    changed = pyqtSignal(str)
    capturing_changed = pyqtSignal(bool)

    def __init__(self,key,parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.key=key
        self.is_capturing=False
        self.blocked=set()
        self.value_label=QLabel(hotkey_name(key))
        self.value_label.setMinimumWidth(68)
        self.value_label.setWordWrap(True)
        self.button=QPushButton("Apertar para detectar")
        self.button.setFixedWidth(165)
        self.button.setMinimumHeight(32)
        self.setMinimumHeight(32)
        self.button.setFocusPolicy(Qt.NoFocus)
        self.button.clicked.connect(self.toggle_capture)
        layout=QHBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.value_label)
        layout.addWidget(self.button)
        self.timer=QTimer(self)
        self.timer.setInterval(15)
        self.timer.timeout.connect(self.poll)
        self.setToolTip("Clique para detectar e pressione uma tecla ou um botão lateral do mouse. Esc cancela. Os atalhos e cliques ficam suspensos durante a captura.")

    def sizeHint(self):
        size = super().sizeHint()
        size.setHeight(max(32, size.height()))
        return size

    def keyPressEvent(self,event):
        if self.is_capturing:event.accept()
        else:super().keyPressEvent(event)

    def pressed_keys(self):
        keys = {key for key in HOTKEY_CODES if InputHandler.is_key_pressed(key)}
        for base in ("SHIFT", "CTRL", "ALT"):
            if base in keys:
                keys.discard("L" + base)
                keys.discard("R" + base)
        return keys

    def toggle_capture(self):
        if self.is_capturing:
            self.cancel()
            return
        self.blocked=self.pressed_keys()
        self.is_capturing=True
        self.setFocus(Qt.OtherFocusReason)
        self.value_label.setText("Pressione…")
        self.button.setText("Cancelar")
        self.capturing_changed.emit(True)
        self.timer.start()

    def poll(self):
        if not self.is_capturing:return
        pressed=self.pressed_keys()
        self.blocked.intersection_update(pressed)
        fresh=pressed-self.blocked
        if "ESC" in fresh:
            self.cancel()
            return
        if len(fresh)!=1:return
        key=next(iter(fresh))
        self.timer.stop()
        self.set_key(key)
        # Mantém a captura suspensa até soltar a tecla escolhida.
        self.changed.emit(key)
        self.blocked=set(pressed)
        self.timer.timeout.disconnect(self.poll)
        self.timer.timeout.connect(self.wait_release)
        self.timer.start()

    def wait_release(self):
        if not self.pressed_keys():self.cancel()

    def set_key(self,key):
        self.key=key
        self.value_label.setText(hotkey_name(key))

    def cancel(self):
        self.timer.stop()
        self.timer.timeout.disconnect()
        self.timer.timeout.connect(self.poll)
        self.is_capturing=False
        self.value_label.setText(hotkey_name(self.key))
        self.button.setText("Apertar para detectar")
        self.capturing_changed.emit(False)
