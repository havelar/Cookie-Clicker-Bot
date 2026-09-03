"""
Interface gráfica principal do Cookie Clicker Bot.
"""
import sys
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QTimer, pyqtSignal, QObject, Qt
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QCheckBox, QTextEdit, QLabel, QGroupBox, QStatusBar,
    QDoubleSpinBox, QGridLayout,
)

from app.config.settings import automation_config, save_automation_settings
from app.core.backup_manager import BackupManager
from app.ui.backup_dialog import BackupDialog
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
        self.backup_manager = BackupManager()
        self.backup_dialog = None
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

        # Botão backups
        self.backups_button = QPushButton("Gerenciar Backups")
        self.backups_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px;
                font-size: 12px;
                font-weight: bold;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.backups_button.clicked.connect(self.open_backup_dialog)
        controls_layout.addWidget(self.backups_button)

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

        # Sugar Lump controls
        self.sugar_lump_group = QGroupBox("Sugar Lump")
        sugar_lump_layout = QVBoxLayout()

        self.sugar_lump_checkbox = QCheckBox("Coletar Sugar Lumps")
        self.sugar_lump_checkbox.setChecked(automation_config.enable_sugar_lump_harvest)
        self.sugar_lump_checkbox.stateChanged.connect(self.toggle_sugar_lump_harvest)
        sugar_lump_layout.addWidget(self.sugar_lump_checkbox)

        preserve_grid = QGridLayout()
        self.preserve_sugar_lump_type_0_cb = QCheckBox("Preservar tipo 0")
        self.preserve_sugar_lump_type_0_cb.setChecked(automation_config.preserve_sugar_lump_type_0)
        self.preserve_sugar_lump_type_0_cb.stateChanged.connect(self.toggle_preserve_sugar_lump_type_0)
        preserve_grid.addWidget(self.preserve_sugar_lump_type_0_cb, 0, 0)

        self.preserve_sugar_lump_type_1_cb = QCheckBox("Preservar tipo 1")
        self.preserve_sugar_lump_type_1_cb.setChecked(automation_config.preserve_sugar_lump_type_1)
        self.preserve_sugar_lump_type_1_cb.stateChanged.connect(self.toggle_preserve_sugar_lump_type_1)
        preserve_grid.addWidget(self.preserve_sugar_lump_type_1_cb, 0, 1)

        self.preserve_sugar_lump_type_2_cb = QCheckBox("Preservar tipo 2 (Golden)")
        self.preserve_sugar_lump_type_2_cb.setChecked(automation_config.preserve_sugar_lump_type_2)
        self.preserve_sugar_lump_type_2_cb.stateChanged.connect(self.toggle_preserve_sugar_lump_type_2)
        preserve_grid.addWidget(self.preserve_sugar_lump_type_2_cb, 1, 0)

        self.preserve_sugar_lump_type_3_cb = QCheckBox("Preservar tipo 3")
        self.preserve_sugar_lump_type_3_cb.setChecked(automation_config.preserve_sugar_lump_type_3)
        self.preserve_sugar_lump_type_3_cb.stateChanged.connect(self.toggle_preserve_sugar_lump_type_3)
        preserve_grid.addWidget(self.preserve_sugar_lump_type_3_cb, 1, 1)

        self.preserve_sugar_lump_type_4_cb = QCheckBox("Preservar tipo 4 (Caramel)")
        self.preserve_sugar_lump_type_4_cb.setChecked(automation_config.preserve_sugar_lump_type_4)
        self.preserve_sugar_lump_type_4_cb.stateChanged.connect(self.toggle_preserve_sugar_lump_type_4)
        preserve_grid.addWidget(self.preserve_sugar_lump_type_4_cb, 2, 0, 1, 2)

        preserve_grid.setHorizontalSpacing(20)
        preserve_grid.setVerticalSpacing(5)
        sugar_lump_layout.addLayout(preserve_grid)

        self.sugar_lump_group.setLayout(sugar_lump_layout)
        controls_layout.addWidget(self.sugar_lump_group)
        self.set_sugar_lump_preserve_enabled(automation_config.enable_sugar_lump_harvest)

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

    def toggle_sugar_lump_harvest(self, state: int) -> None:
        """Ativa ou desativa a automação de Sugar Lump."""
        automation_config.enable_sugar_lump_harvest = bool(state)
        self.set_sugar_lump_preserve_enabled(bool(state))
        save_automation_settings()

    def set_sugar_lump_preserve_enabled(self, enabled: bool) -> None:
        """Habilita ou desabilita os checkboxes de preservação de Sugar Lump."""
        self.preserve_sugar_lump_type_0_cb.setEnabled(enabled)
        self.preserve_sugar_lump_type_1_cb.setEnabled(enabled)
        self.preserve_sugar_lump_type_2_cb.setEnabled(enabled)
        self.preserve_sugar_lump_type_3_cb.setEnabled(enabled)
        self.preserve_sugar_lump_type_4_cb.setEnabled(enabled)

    def toggle_preserve_sugar_lump_type_0(self, state: int) -> None:
        automation_config.preserve_sugar_lump_type_0 = bool(state)
        save_automation_settings()

    def toggle_preserve_sugar_lump_type_1(self, state: int) -> None:
        automation_config.preserve_sugar_lump_type_1 = bool(state)
        save_automation_settings()

    def toggle_preserve_sugar_lump_type_2(self, state: int) -> None:
        automation_config.preserve_sugar_lump_type_2 = bool(state)
        save_automation_settings()

    def toggle_preserve_sugar_lump_type_3(self, state: int) -> None:
        automation_config.preserve_sugar_lump_type_3 = bool(state)
        save_automation_settings()

    def toggle_preserve_sugar_lump_type_4(self, state: int) -> None:
        automation_config.preserve_sugar_lump_type_4 = bool(state)
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

    def open_backup_dialog(self):
        """Abre o dialog de gerenciamento de backups."""
        if self.backup_dialog is None:
            self.backup_dialog = BackupDialog(self.backup_manager, self)
            self.backup_dialog.backup_restored.connect(self.on_backup_restored)
        self.backup_dialog.show()
        self.backup_dialog.raise_()
        self.backup_dialog.activateWindow()

    def on_backup_restored(self, save_data: str):
        """Handle backup restoration - load save into game."""
        if self.runner and self.runner.bridge:
            success = self.runner.bridge.load_game_save(save_data)
            if success:
                logger.info("Save restaurado com sucesso via backup")
                self.add_log("Save restaurado com sucesso!")
            else:
                logger.error("Falha ao restaurar save")
                self.add_log("ERRO: Falha ao restaurar save")
        else:
            logger.warning("Bridge não disponível para restaurar save")
            self.add_log("ERRO: Bridge não conectado para restaurar save")


def create_ui_app():
    """Cria e retorna a aplicação Qt."""
    app = QApplication(sys.argv)
    window = MainWindow()
    return app, window