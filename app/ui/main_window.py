"""
Interface gráfica principal do Cookie Clicker Bot.
"""
import sys
from typing import Optional

from PyQt5.QtCore import QTimer, pyqtSignal, QObject, Qt
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QCheckBox, QTextEdit, QLabel, QGroupBox, QStatusBar,
    QDoubleSpinBox, QGridLayout,
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
        self.setGeometry(100, 100, 600, 400)

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

        # Checkboxes para automações em duas colunas
        checkbox_grid = QGridLayout()

        self.golden_checkbox = QCheckBox("Coletar Golden Cookies")
        self.golden_checkbox.setChecked(automation_config.enable_golden_cookie)
        self.golden_checkbox.stateChanged.connect(self.toggle_golden_detection)
        checkbox_grid.addWidget(self.golden_checkbox, 0, 0)

        self.fortune_checkbox = QCheckBox("Coletar Fortune Cookies")
        self.fortune_checkbox.setChecked(automation_config.enable_fortune_cookie)
        self.fortune_checkbox.stateChanged.connect(self.toggle_fortune_detection)
        checkbox_grid.addWidget(self.fortune_checkbox, 0, 1)

        self.reindeer_checkbox = QCheckBox("Coletar Reindeers (Natal)")
        self.reindeer_checkbox.setChecked(automation_config.enable_reindeer)
        self.reindeer_checkbox.stateChanged.connect(self.toggle_reindeer_detection)
        checkbox_grid.addWidget(self.reindeer_checkbox, 1, 0)

        self.wrinkler_checkbox = QCheckBox("Coletar Wrinklers")
        self.wrinkler_checkbox.setChecked(automation_config.enable_wrinkler_popper)
        self.wrinkler_checkbox.stateChanged.connect(self.toggle_wrinkler_detection)
        checkbox_grid.addWidget(self.wrinkler_checkbox, 1, 1)

        checkbox_grid.setHorizontalSpacing(20)
        checkbox_grid.setVerticalSpacing(10)
        controls_layout.addLayout(checkbox_grid)

        delay_layout = QHBoxLayout()
        self.wrinkler_delay_label = QLabel("Delay de Wrinklers (s):")
        delay_layout.addWidget(self.wrinkler_delay_label)

        self.wrinkler_delay_input = QDoubleSpinBox()
        self.wrinkler_delay_input.setRange(0.1, 60.0)
        self.wrinkler_delay_input.setSingleStep(0.1)
        self.wrinkler_delay_input.setValue(automation_config.wrinkler_pop_delay)
        self.wrinkler_delay_input.valueChanged.connect(self.update_wrinkler_delay)
        delay_layout.addWidget(self.wrinkler_delay_input)

        controls_layout.addLayout(delay_layout)
        self.wrinkler_delay_input.setEnabled(automation_config.enable_wrinkler_popper)

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

        self.stats_timer = QTimer(self)
        self.stats_timer.timeout.connect(self.refresh_stats)
        self.stats_timer.start(1000)

        # Grupo de contadores
        counters_group = QGroupBox("Contadores")
        counters_layout = QGridLayout()

        self.cookies_clicked_label = QLabel("Cookies Clickados:\n0")
        self.golden_clicked_label = QLabel("Golden Cookies Clicados:\n0")
        self.reindeer_popped_label = QLabel("Renas Poppadas:\n0")
        self.wrinklers_popped_label = QLabel("Wrinklers Poppados:\n0")

        self.cookies_clicked_label.setStyleSheet(
            "background-color: #FFF3B0; border: 2px solid #E2B007; border-radius: 10px;"
            "font-weight: bold; font-size: 13px; padding: 12px;"
        )
        self.golden_clicked_label.setStyleSheet(
            "background-color: #FFE3B8; border: 2px solid #D98F3F; border-radius: 10px;"
            "font-weight: bold; font-size: 13px; padding: 12px;"
        )
        self.reindeer_popped_label.setStyleSheet(
            "background-color: #D6F5E6; border: 2px solid #3EA18C; border-radius: 10px;"
            "font-weight: bold; font-size: 13px; padding: 12px;"
        )
        self.wrinklers_popped_label.setStyleSheet(
            "background-color: #E8D6FF; border: 2px solid #7B50C6; border-radius: 10px;"
            "font-weight: bold; font-size: 13px; padding: 12px;"
        )

        for label in [
            self.cookies_clicked_label,
            self.golden_clicked_label,
            self.reindeer_popped_label,
            self.wrinklers_popped_label,
        ]:
            label.setAlignment(Qt.AlignCenter)
            label.setMinimumSize(220, 70)

        counters_layout.setHorizontalSpacing(20)
        counters_layout.setVerticalSpacing(20)
        counters_layout.setAlignment(Qt.AlignCenter)

        counters_layout.addWidget(self.cookies_clicked_label, 0, 0)
        counters_layout.addWidget(self.golden_clicked_label, 0, 1)
        counters_layout.addWidget(self.reindeer_popped_label, 1, 0)
        counters_layout.addWidget(self.wrinklers_popped_label, 1, 1)
        counters_group.setLayout(counters_layout)
        layout.addWidget(counters_group, alignment=Qt.AlignCenter)

        # Logs
        logs_group = QGroupBox("Logs")
        logs_layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(180)
        logs_layout.addWidget(self.log_text)

        logs_group.setLayout(logs_layout)
        layout.addWidget(logs_group, stretch=1)

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
        self.wrinkler_delay_input.setEnabled(automation_config.enable_wrinkler_popper)
        save_automation_settings()

    def update_wrinkler_delay(self, value: float) -> None:
        """Atualiza o delay de popagem dos wrinklers."""
        automation_config.wrinkler_pop_delay = value
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

    def refresh_stats(self):
        """Atualiza os contadores da UI a partir do runner."""
        if not self.runner:
            return

        self.cookies_clicked_label.setText(f"Cookies Clickados:\n{self.runner.cookies_clicked}")
        self.golden_clicked_label.setText(f"Golden Cookies Clicados:\n{self.runner.golden_cookies_clicked}")
        self.reindeer_popped_label.setText(f"Renas Poppadas:\n{self.runner.reindeer_popped}")
        self.wrinklers_popped_label.setText(f"Wrinklers Poppados:\n{self.runner.wrinklers_popped}")


def create_ui_app():
    """Cria e retorna a aplicação Qt."""
    app = QApplication(sys.argv)
    window = MainWindow()
    return app, window