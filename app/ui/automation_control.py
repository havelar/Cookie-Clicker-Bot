"""Controle único de execução, compartilhado pelas automações."""
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel


class AutomationControl(QWidget):
    requested = pyqtSignal(bool)

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.running = False
        self.stopping = False
        self.name = name
        self.button = QPushButton("Ligar", self)
        self.button.setMinimumWidth(90)
        self.status = QLabel("Desligada", self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.status)
        layout.addWidget(self.button)
        self.button.clicked.connect(lambda: self.requested.emit(not self.running))
        self.set_running(False)

    def set_running(self, running: bool):
        self.running = running
        self.stopping = False
        self.button.setEnabled(True)
        self.button.setText("Desligar" if running else "Ligar")
        self.button.setAccessibleName(f"{self.button.text()} {self.name}")
        self.button.setObjectName("dangerButton" if running else "primaryButton")
        self.button.style().unpolish(self.button)
        self.button.style().polish(self.button)
        self.status.setText("Rodando" if running else "Desligada")
        self.status.setStyleSheet(f"color: {'#65d6a5' if running else '#9aa7ba'};")

    def set_stopping(self):
        self.stopping = True
        self.status.setText("Desligando…")
        self.status.setStyleSheet("color: #e8b766;")
        self.button.setEnabled(False)

    def set_paused(self, paused: bool):
        if self.running and not self.stopping:
            self.status.setText("Pausada pelo Combo" if paused else "Rodando")
            self.status.setStyleSheet(f"color: {'#e8b766' if paused else '#65d6a5'};")
