"""
Interface gráfica principal do Cookie Clicker Bot.
"""
import sys
from typing import Optional

from PyQt5.QtCore import QTimer, pyqtSignal, QObject
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QCheckBox, QTextEdit, QLabel, QGroupBox, QStatusBar
)

from app.config.settings import automation_config, save_automation_settings
from app.utils.logger import logger


class LogSignalEmitter(QObject):
    """Emissor de sinais para logs."""
    log_signal = pyqtSignal(str)


class MainWindow(QMainWindow):
    """Janela principal da aplicação."""

    clicker_state_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.log_emitter = LogSignalEmitter()
        self.runner = None  # Será definido pelo Application
        self.setup_ui()
        self.connect_signals()
        self.clicker_state_changed.connect(self.set_clicker_state)

    def setup_ui(self):
        """Configura a interface gráfica."""
        self.setWindowTitle("Cookie Clicker Bot v1.0.0")
        self.setGeometry(100, 100, 600, 500)

        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Layout principal
        layout = QVBoxLayout(central_widget)

        # Grupo de controles
        controls_group = QGroupBox("Controles de Automação")
        controls_layout = QVBoxLayout()

        # Botão toggle clicker
        self.clicker_button = QPushButton("INICIAR CLICKER")
        self.clicker_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.clicker_button.clicked.connect(self.toggle_clicker)
        controls_layout.addWidget(self.clicker_button)

        # Checkboxes para automações
        self.golden_checkbox = QCheckBox("Detectar Golden Cookies")
        self.golden_checkbox.setChecked(automation_config.enable_golden_cookie)
        self.golden_checkbox.stateChanged.connect(self.toggle_golden_detection)
        controls_layout.addWidget(self.golden_checkbox)

        self.fortune_checkbox = QCheckBox("Detectar Fortune Cookies")
        self.fortune_checkbox.setChecked(automation_config.enable_fortune_cookie)
        self.fortune_checkbox.stateChanged.connect(self.toggle_fortune_detection)
        controls_layout.addWidget(self.fortune_checkbox)

        self.wrinkler_checkbox = QCheckBox("Detectar/Popar Wrinklers")
        self.wrinkler_checkbox.setChecked(automation_config.enable_wrinkler_popper)
        self.wrinkler_checkbox.stateChanged.connect(self.toggle_wrinkler_detection)
        controls_layout.addWidget(self.wrinkler_checkbox)

        # Placeholder para futuras automações
        self.reindeer_checkbox = QCheckBox("Detectar Reindeers (Natal)")
        self.reindeer_checkbox.setChecked(automation_config.enable_reindeer)
        self.reindeer_checkbox.setEnabled(True)
        self.reindeer_checkbox.stateChanged.connect(self.toggle_reindeer_detection)
        controls_layout.addWidget(self.reindeer_checkbox)

        controls_group.setLayout(controls_layout)
        layout.addWidget(controls_group)

        # Grupo de status
        status_group = QGroupBox("Status")
        status_layout = QHBoxLayout()

        self.bridge_status = QLabel("Bridge: Desconectado")
        self.bridge_status.setStyleSheet("color: red;")
        status_layout.addWidget(self.bridge_status)

        self.clicker_status = QLabel("Clicker: Parado")
        self.clicker_status.setStyleSheet("color: gray;")
        status_layout.addWidget(self.clicker_status)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Logs
        logs_group = QGroupBox("Logs")
        logs_layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        logs_layout.addWidget(self.log_text)

        logs_group.setLayout(logs_layout)
        layout.addWidget(logs_group)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        # self.status_bar.showMessage("Pronto")

    def connect_signals(self):
        """Conecta sinais da interface."""
        self.log_emitter.log_signal.connect(self.add_log)

    def toggle_golden_detection(self, state: int) -> None:
        """Ativa ou desativa a detecção de golden cookies."""
        automation_config.enable_golden_cookie = bool(state)
        save_automation_settings()

    def toggle_fortune_detection(self, state: int) -> None:
        """Ativa ou desativa a detecção de fortune cookies."""
        automation_config.enable_fortune_cookie = bool(state)
        save_automation_settings()

    def toggle_wrinkler_detection(self, state: int) -> None:
        """Ativa ou desativa o popador de wrinklers."""
        automation_config.enable_wrinkler_popper = bool(state)
        save_automation_settings()

    def toggle_reindeer_detection(self, state: int) -> None:
        """Ativa ou desativa a detecção de renas."""
        automation_config.enable_reindeer = bool(state)
        save_automation_settings()

    def toggle_clicker(self):
        """Alterna o estado do clicker."""
        if not self.runner:
            logger.warning("Runner não está disponível")
            return

        self.runner.toggle_clicker()
        self.set_clicker_state(self.runner.is_running)

    def set_clicker_state(self, active: bool):
        """Atualiza o botão e o status do clicker com base no estado."""
        if active:
            self.clicker_button.setText("PARAR CLICKER")
            self.clicker_button.setStyleSheet("""
                QPushButton {
                    background-color: #f44336;
                    color: white;
                    padding: 10px;
                    font-size: 14px;
                    font-weight: bold;
                    border: none;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #da190b;
                }
            """)
            self.clicker_status.setText("Clicker: Ativo")
            self.clicker_status.setStyleSheet("color: green;")
        else:
            self.clicker_button.setText("INICIAR CLICKER")
            self.clicker_button.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    padding: 10px;
                    font-size: 14px;
                    font-weight: bold;
                    border: none;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
            """)
            self.clicker_status.setText("Clicker: Parado")
            self.clicker_status.setStyleSheet("color: gray;")

    def add_log(self, message: str):
        """Adiciona uma mensagem aos logs."""
        self.log_text.append(message)
        # Auto-scroll para o final
        cursor = self.log_text.textCursor()
        cursor.movePosition(cursor.End)
        self.log_text.setTextCursor(cursor)

    def update_bridge_status(self, connected: bool):
        """Atualiza o status do bridge."""
        if connected:
            self.bridge_status.setText("Bridge: Conectado")
            self.bridge_status.setStyleSheet("color: green;")
        else:
            self.bridge_status.setText("Bridge: Desconectado")
            self.bridge_status.setStyleSheet("color: red;")


def create_ui_app():
    """Cria e retorna a aplicação Qt."""
    app = QApplication(sys.argv)
    window = MainWindow()
    return app, window