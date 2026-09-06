"""Interface gráfica principal do Cookie Clicker Bot."""
import sys
from pathlib import Path
from PyQt5.QtCore import QTimer, pyqtSignal, QObject, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QTextEdit, QLabel, QGroupBox, QStatusBar, QDoubleSpinBox, QGridLayout, QTabWidget)

from app.config.settings import automation_config, save_automation_settings
from app.core.backup_manager import BackupManager
from app.ui.backup_dialog import BackupDialog
from app.ui.theme import DARK_STYLESHEET, enable_dark_title_bars, set_windows_app_id
from app.utils.logger import logger

APP_ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "cookie_clicker_bot.ico"


class LogSignalEmitter(QObject):
    log_signal = pyqtSignal(str)


class MainWindow(QMainWindow):
    clicker_state_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.log_emitter, self.runner = LogSignalEmitter(), None
        self.backup_manager, self.backup_dialog = BackupManager(), None
        self.setup_ui()
        self.log_emitter.log_signal.connect(self.add_log)
        self.clicker_state_changed.connect(self.set_clicker_state)

    def setup_ui(self):
        self.setWindowTitle("Cookie Clicker Bot")
        self.resize(860, 720)
        self.setMinimumSize(720, 580)
        central = QWidget(); self.setCentralWidget(central)
        layout = QVBoxLayout(central); layout.setContentsMargins(22, 20, 22, 16); layout.setSpacing(14)

        header = QHBoxLayout(); title_block = QVBoxLayout()
        title = QLabel("Cookie Clicker Bot"); title.setStyleSheet("font-size: 22px; font-weight: 700; color: #f4f7fc;")
        subtitle = QLabel("Automação, monitoramento e backups em um só lugar"); subtitle.setStyleSheet("color: #9aa7ba;")
        title_block.addWidget(title); title_block.addWidget(subtitle)
        header.addLayout(title_block); header.addStretch()
        self.clicker_button = QPushButton("INICIAR CLICKER"); self.clicker_button.setObjectName("primaryButton"); self.clicker_button.setMinimumHeight(42); self.clicker_button.clicked.connect(self.toggle_clicker)
        self.backups_button = QPushButton("Gerenciar Backups"); self.backups_button.clicked.connect(self.open_backup_dialog)
        header.addWidget(self.clicker_button); header.addWidget(self.backups_button); layout.addLayout(header)

        status_group = QGroupBox("Conexão"); status_layout = QHBoxLayout(status_group)
        self.bridge_status, self.clicker_status = QLabel("Bridge: Desconectado"), QLabel("Clicker: Parado")
        self.bridge_status.setStyleSheet("color: #f07883; font-weight: 600;"); self.clicker_status.setStyleSheet("color: #9aa7ba; font-weight: 600;")
        status_layout.addWidget(self.bridge_status); status_layout.addSpacing(26); status_layout.addWidget(self.clicker_status); status_layout.addStretch(); layout.addWidget(status_group)

        counters_group = QGroupBox("Atividade da sessão"); counters = QGridLayout(counters_group); counters.setSpacing(10)
        self.cookies_clicked_label = QLabel("Cookies clicados\n0"); self.golden_clicked_label = QLabel("Golden Cookies\n0")
        self.reindeer_popped_label = QLabel("Renas coletadas\n0"); self.wrinklers_popped_label = QLabel("Wrinklers coletados\n0")
        for column, label in enumerate((self.cookies_clicked_label, self.golden_clicked_label, self.reindeer_popped_label, self.wrinklers_popped_label)):
            label.setObjectName("metricCard"); label.setAlignment(Qt.AlignCenter); label.setMinimumHeight(62); counters.addWidget(label, 0, column)
        layout.addWidget(counters_group)

        tabs = QTabWidget(); tabs.addTab(self._automation_tab(), "Automações"); tabs.addTab(self._sugar_tab(), "Sugar Lumps"); tabs.addTab(self._activity_tab(), "Atividade"); layout.addWidget(tabs, 1)
        self.stats_timer = QTimer(self); self.stats_timer.timeout.connect(self.refresh_stats); self.stats_timer.start(1000)
        self.status_bar = QStatusBar(); self.setStatusBar(self.status_bar); self.status_bar.showMessage("Pronto para conectar ao Cookie Clicker")

    def _automation_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setContentsMargins(14, 16, 14, 14)
        group = QGroupBox("Coletas automáticas"); group_layout = QVBoxLayout(group); grid = QGridLayout()
        controls = (("golden_checkbox", "Coletar Golden Cookies", "enable_golden_cookie", self.toggle_golden_detection), ("fortune_checkbox", "Coletar Fortune Cookies", "enable_fortune_cookie", self.toggle_fortune_detection), ("reindeer_checkbox", "Coletar Renas (Natal)", "enable_reindeer", self.toggle_reindeer_detection), ("wrinkler_checkbox", "Coletar Wrinklers", "enable_wrinkler_popper", self.toggle_wrinkler_detection))
        for index, (name, text, setting, handler) in enumerate(controls):
            checkbox = QCheckBox(text); checkbox.setChecked(getattr(automation_config, setting)); checkbox.stateChanged.connect(handler); setattr(self, name, checkbox); grid.addWidget(checkbox, index // 2, index % 2)
        grid.setColumnStretch(0, 1); grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(36); grid.setVerticalSpacing(10)
        delay = QHBoxLayout(); delay.setContentsMargins(0, 2, 0, 0)
        delay.addWidget(QLabel("Intervalo entre wrinklers")); delay.addStretch(); delay.addSpacing(8)
        self.wrinkler_delay_input = QDoubleSpinBox(); self.wrinkler_delay_input.setFixedWidth(96); self.wrinkler_delay_input.setRange(0.1, 60.0); self.wrinkler_delay_input.setSingleStep(0.1); self.wrinkler_delay_input.setValue(automation_config.wrinkler_pop_delay); self.wrinkler_delay_input.valueChanged.connect(self.update_wrinkler_delay); self.wrinkler_delay_input.setEnabled(automation_config.enable_wrinkler_popper)
        delay.addWidget(self.wrinkler_delay_input); grid.addLayout(delay, 2, 1)
        group_layout.addLayout(grid); layout.addWidget(group); layout.addStretch(); return tab

    def _sugar_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setContentsMargins(14, 16, 14, 14)
        group = QGroupBox("Coleta e preservação"); self.sugar_lump_group = group; group_layout = QVBoxLayout(group)
        self.sugar_lump_checkbox = QCheckBox("Coletar Sugar Lumps maduras"); self.sugar_lump_checkbox.setChecked(automation_config.enable_sugar_lump_harvest); self.sugar_lump_checkbox.stateChanged.connect(self.toggle_sugar_lump_harvest); group_layout.addWidget(self.sugar_lump_checkbox); group_layout.addWidget(QLabel("Tipos a preservar"))
        grid = QGridLayout(); entries = (("Preservar tipo 0", 0), ("Preservar tipo 1", 1), ("Preservar tipo 2 (Golden)", 2), ("Preservar tipo 3", 3), ("Preservar tipo 4 (Caramel)", 4)); self._preserve_checkboxes = []
        for index, (text, number) in enumerate(entries):
            checkbox = QCheckBox(text); checkbox.setChecked(getattr(automation_config, f"preserve_sugar_lump_type_{number}")); checkbox.stateChanged.connect(lambda state, n=number: self._set_sugar_lump_type(n, state)); grid.addWidget(checkbox, index // 2, index % 2); self._preserve_checkboxes.append(checkbox)
        group_layout.addLayout(grid); layout.addWidget(group); layout.addStretch(); self.set_sugar_lump_preserve_enabled(automation_config.enable_sugar_lump_harvest); return tab

    def _activity_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setContentsMargins(14, 16, 14, 14); group = QGroupBox("Registro de atividades"); group_layout = QVBoxLayout(group)
        self.log_text = QTextEdit(); self.log_text.setReadOnly(True); self.log_text.setMinimumHeight(230); group_layout.addWidget(self.log_text); layout.addWidget(group); return tab

    def _save(self, field, state): setattr(automation_config, field, bool(state)); save_automation_settings()
    def toggle_golden_detection(self, state): self._save("enable_golden_cookie", state)
    def toggle_fortune_detection(self, state): self._save("enable_fortune_cookie", state)
    def toggle_reindeer_detection(self, state): self._save("enable_reindeer", state)
    def toggle_wrinkler_detection(self, state): self._save("enable_wrinkler_popper", state); self.wrinkler_delay_input.setEnabled(bool(state))
    def toggle_sugar_lump_harvest(self, state): self._save("enable_sugar_lump_harvest", state); self.set_sugar_lump_preserve_enabled(bool(state))
    def _set_sugar_lump_type(self, number, state): self._save(f"preserve_sugar_lump_type_{number}", state)
    def toggle_preserve_sugar_lump_type_0(self, state): self._set_sugar_lump_type(0, state)
    def toggle_preserve_sugar_lump_type_1(self, state): self._set_sugar_lump_type(1, state)
    def toggle_preserve_sugar_lump_type_2(self, state): self._set_sugar_lump_type(2, state)
    def toggle_preserve_sugar_lump_type_3(self, state): self._set_sugar_lump_type(3, state)
    def toggle_preserve_sugar_lump_type_4(self, state): self._set_sugar_lump_type(4, state)
    def set_sugar_lump_preserve_enabled(self, enabled):
        for checkbox in self._preserve_checkboxes: checkbox.setEnabled(enabled)
    def update_wrinkler_delay(self, value): automation_config.wrinkler_pop_delay = value; save_automation_settings()

    def toggle_clicker(self):
        if not self.runner: logger.warning("Runner não está disponível"); return
        self.runner.toggle_clicker(); self.set_clicker_state(self.runner.is_running)
    def set_clicker_state(self, active):
        self.clicker_button.setText("PARAR CLICKER" if active else "INICIAR CLICKER"); self.clicker_button.setObjectName("dangerButton" if active else "primaryButton"); self.clicker_button.style().unpolish(self.clicker_button); self.clicker_button.style().polish(self.clicker_button)
        self.clicker_status.setText("Clicker: Ativo" if active else "Clicker: Parado"); self.clicker_status.setStyleSheet(f"color: {'#65d6a5' if active else '#9aa7ba'}; font-weight: 600;")
    def update_bridge_status(self, connected):
        self.bridge_status.setText("Bridge: Conectado" if connected else "Bridge: Desconectado"); self.bridge_status.setStyleSheet(f"color: {'#65d6a5' if connected else '#f07883'}; font-weight: 600;")
    def add_log(self, message):
        self.log_text.append(message); cursor = self.log_text.textCursor(); cursor.movePosition(cursor.End); self.log_text.setTextCursor(cursor)
    def refresh_stats(self):
        if not self.runner: return
        self.cookies_clicked_label.setText(f"Cookies clicados\n{self.runner.cookies_clicked}"); self.golden_clicked_label.setText(f"Golden Cookies\n{self.runner.golden_cookies_clicked}"); self.reindeer_popped_label.setText(f"Renas coletadas\n{self.runner.reindeer_popped}"); self.wrinklers_popped_label.setText(f"Wrinklers coletados\n{self.runner.wrinklers_popped}")
    def open_backup_dialog(self):
        if self.backup_dialog is None:
            self.backup_dialog = BackupDialog(self.backup_manager, self); self.backup_dialog.backup_restored.connect(self.on_backup_restored)
        self.backup_dialog.show(); self.backup_dialog.raise_(); self.backup_dialog.activateWindow()
    def on_backup_restored(self, save_data):
        if self.runner and self.runner.bridge and self.runner.bridge.load_game_save(save_data): logger.info("Save restaurado com sucesso via backup"); self.add_log("Save restaurado com sucesso!")
        else: logger.warning("Bridge não disponível ou falhou ao restaurar save"); self.add_log("ERRO: Falha ao restaurar save")


def create_ui_app():
    set_windows_app_id()
    app = QApplication(sys.argv); app.setStyleSheet(DARK_STYLESHEET); enable_dark_title_bars(app)
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    window = MainWindow(); window.setWindowIcon(app.windowIcon())
    return app, window
