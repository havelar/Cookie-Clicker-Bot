"""Interface gráfica principal do Cookie Clicker Bot."""
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from PyQt5.QtCore import QThread, QTimer, pyqtSignal, QObject, Qt
from PyQt5.QtGui import QColor, QIcon, QTextCursor
from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QComboBox, QTextEdit, QLabel, QGroupBox, QStatusBar, QDoubleSpinBox, QSpinBox, QGridLayout, QFormLayout, QTabWidget, QHeaderView, QTableWidget, QTableWidgetItem, QScrollArea, QMessageBox)

from app.bridge.js_bridge import CookieClickerBridge, DEFAULT_GRIMOIRE_SPELLS
from app.config.settings import app_config, automation_config, save_app_settings, save_automation_settings
from app.core.backup_manager import BackupManager
from app.core.auto_ascensao import AutoAscensao, ConfiguracaoAutoAscensao
from app.core.fazendeira import Fazendeira
from app.core.stock_market import StockMarketAutomation
from app.core.stock_policy import GASEOUS_ASSETS_TARGET, asset_limits
from app.models.stock_market import StockMarketAutomationResult, StockMarketSnapshot, StockTradeResult
from app.models.garden import GardenCycleResult
from app.models.auto_ascensao import RelatorioAutoAscensao
from app.ui.backup_dialog import BackupDialog
from app.ui.stock_limits_dialog import StockLimitsDialog
from app.ui.theme import DARK_STYLESHEET, enable_dark_title_bars, set_windows_app_id
from app.utils.logger import logger

APP_ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "cookie_clicker_bot.ico"


class LogSignalEmitter(QObject):
    log_signal = pyqtSignal(str)


class StockMarketWorker(QThread):
    """Executa uma chamada potencialmente lenta ao bridge fora do event loop."""

    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, operation: Callable[[], object], parent: Optional[QObject] = None):
        super().__init__(parent)
        self.operation = operation

    def run(self) -> None:
        try:
            self.completed.emit(self.operation())
        except Exception as error:
            self.failed.emit(str(error))


class AutoAscensaoWorker(QThread):
    """Executa a máquina de estados sem bloquear o event loop do Qt."""

    updated = pyqtSignal(object)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, automation: AutoAscensao, preview: bool, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.automation = automation
        self.preview = preview

    def run(self) -> None:
        try:
            if self.preview:
                report = self.automation.gerar_previa()
                self.updated.emit(report)
            else:
                report = self.automation.executar(self.updated.emit)
            self.completed.emit(report)
        except Exception as error:
            self.failed.emit(str(error))

    def stop(self) -> None:
        self.automation.parar()


class SortableTableWidgetItem(QTableWidgetItem):
    """Item que preserva o texto formatado, mas ordena pelo valor real."""

    def __init__(self, text: str, sort_value=None):
        super().__init__(text)
        self.sort_value = sort_value

    def __lt__(self, other):
        if isinstance(other, SortableTableWidgetItem):
            if self.sort_value is not None and other.sort_value is not None:
                return self.sort_value < other.sort_value
        return super().__lt__(other)


class MainWindow(QMainWindow):
    clicker_state_changed = pyqtSignal(bool)

    def __init__(self, bridge: Optional[CookieClickerBridge] = None):
        super().__init__()
        self.bridge = bridge
        self.log_emitter, self.runner = LogSignalEmitter(), None
        self.backup_manager, self.backup_dialog = BackupManager(), None
        self._stock_worker: Optional[StockMarketWorker] = None
        self._stock_available = False
        self._refresh_after_order = False
        self._stock_snapshot: Optional[StockMarketSnapshot] = None
        self._garden_worker: Optional[StockMarketWorker] = None
        self._garden_available = False
        self._garden_run_when_idle = False
        self._auto_ascension_worker: Optional[AutoAscensaoWorker] = None
        self._auto_ascension: Optional[AutoAscensao] = None
        self._session_started_at = time.monotonic()
        self.stock_automation = StockMarketAutomation(bridge) if bridge else None
        self.fazendeira = Fazendeira(bridge) if bridge else None
        self.setup_ui()
        self.log_emitter.log_signal.connect(self.add_log)
        self.clicker_state_changed.connect(self.set_clicker_state)

    def setup_ui(self):
        self.setWindowTitle("Cookie Clicker Bot")
        self.resize(860, 640)
        self.setMinimumSize(720, 500)
        central = QWidget(); self.setCentralWidget(central)
        layout = QVBoxLayout(central); layout.setContentsMargins(16, 12, 16, 10); layout.setSpacing(8)

        header = QHBoxLayout(); header.setContentsMargins(0, 0, 0, 0); header.setSpacing(8)
        title = QLabel("Cookie Clicker Bot"); title.setStyleSheet("font-size: 22px; font-weight: 700; color: #f4f7fc;")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #f4f7fc;")
        header.addWidget(title); header.addStretch()
        self.clicker_button = QPushButton("INICIAR CLICKER"); self.clicker_button.setObjectName("primaryButton"); self.clicker_button.setMinimumHeight(32); self.clicker_button.clicked.connect(self.toggle_clicker)
        self.backups_button = QPushButton("Gerenciar Backups"); self.backups_button.clicked.connect(self.open_backup_dialog)
        header.addWidget(self.clicker_button); header.addWidget(self.backups_button); layout.addLayout(header)

        summary = QWidget(); summary.setObjectName("sessionSummary")
        status_layout = QHBoxLayout(summary); status_layout.setContentsMargins(9, 4, 9, 4); status_layout.setSpacing(14)
        self.bridge_status, self.clicker_status = QLabel("Bridge: Desconectado"), QLabel("Clicker: Parado")
        self.session_timer_label = QLabel("Sessão: 00:00:00")
        self.session_timer_label.setStyleSheet("color: #aeb8c9;")
        self.bridge_status.setStyleSheet("color: #f07883; font-weight: 600;"); self.clicker_status.setStyleSheet("color: #9aa7ba; font-weight: 600;")
        status_layout.addWidget(self.bridge_status); status_layout.addWidget(self.clicker_status); status_layout.addWidget(self.session_timer_label); status_layout.addStretch()

        self.cookies_clicked_label = QLabel("Cliques: 0"); self.golden_clicked_label = QLabel("Golden: 0")
        self.reindeer_popped_label = QLabel("Renas: 0"); self.wrinklers_popped_label = QLabel("Wrinklers: 0")
        for label in (self.cookies_clicked_label, self.golden_clicked_label, self.reindeer_popped_label, self.wrinklers_popped_label):
            label.setStyleSheet("color: #aeb8c9;")
            status_layout.addWidget(label)
        layout.addWidget(summary)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._automation_tab(), "Automações")
        self.tabs.addTab(self._stock_market_tab(), "Stock Market")
        self.tabs.addTab(self._garden_tab(), "Garden")
        self.tabs.addTab(self._auto_ascension_tab(), "Auto Ascensão")
        self.tabs.addTab(self._activity_tab(), "Atividade")
        self.tabs.addTab(self._settings_tab(), "Configurações")
        layout.addWidget(self.tabs, 1)
        self.stats_timer = QTimer(self); self.stats_timer.timeout.connect(self.refresh_stats); self.stats_timer.start(1000)
        self.status_bar = QStatusBar(); self.setStatusBar(self.status_bar); self.status_bar.showMessage("Pronto para conectar ao Cookie Clicker")
        self.stock_refresh_timer = QTimer(self)
        self.stock_refresh_timer.timeout.connect(self._on_stock_market_timer)
        if self.bridge:
            self.stock_refresh_timer.start(5_000)
            QTimer.singleShot(0, self._on_stock_market_timer)
        self.garden_refresh_timer = QTimer(self)
        self.garden_refresh_timer.setSingleShot(True)
        self.garden_refresh_timer.timeout.connect(self._on_garden_timer)
        if self.bridge:
            QTimer.singleShot(0, self.refresh_garden)

    def _automation_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setContentsMargins(14, 16, 14, 14)
        group = QGroupBox("Ligar ou desligar"); group_layout = QVBoxLayout(group); grid = QGridLayout()
        controls = (("golden_checkbox", "Coletar Golden Cookies", "enable_golden_cookie", self.toggle_golden_detection), ("fortune_checkbox", "Coletar Fortune Cookies", "enable_fortune_cookie", self.toggle_fortune_detection), ("reindeer_checkbox", "Coletar Renas (Natal)", "enable_reindeer", self.toggle_reindeer_detection), ("wrinkler_checkbox", "Coletar Wrinklers", "enable_wrinkler_popper", self.toggle_wrinkler_detection))
        for index, (name, text, setting, handler) in enumerate(controls):
            checkbox = QCheckBox(text); checkbox.setChecked(getattr(automation_config, setting)); checkbox.stateChanged.connect(handler); setattr(self, name, checkbox); grid.addWidget(checkbox, index // 2, index % 2)
        self.grimoire_spell_spam_checkbox = QCheckBox("Spammar Skill")
        self.grimoire_spell_spam_checkbox.setToolTip(
            "Aguarda a mana chegar ao máximo e usa uma vez a skill configurada"
        )
        self.grimoire_spell_spam_checkbox.setChecked(automation_config.enable_grimoire_spell_spam)
        self.grimoire_spell_spam_checkbox.stateChanged.connect(self.toggle_grimoire_spell_spam)
        grid.addWidget(self.grimoire_spell_spam_checkbox, 2, 0)
        self.sugar_lump_checkbox = QCheckBox("Coletar Sugar Lumps maduras")
        self.sugar_lump_checkbox.setChecked(automation_config.enable_sugar_lump_harvest)
        self.sugar_lump_checkbox.stateChanged.connect(self.toggle_sugar_lump_harvest)
        grid.addWidget(self.sugar_lump_checkbox, 2, 1)
        grid.setColumnStretch(0, 1); grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(36); grid.setVerticalSpacing(10)
        group_layout.addLayout(grid); layout.addWidget(group); layout.addStretch(); return tab

    def _load_grimoire_spells(self):
        spells = self.bridge.get_grimoire_spells() if self.bridge else []
        if not spells:
            spells = [
                {"id": spell_id, "name": name, "description": ""}
                for spell_id, name in DEFAULT_GRIMOIRE_SPELLS
            ]
        self.grimoire_spell_combo.blockSignals(True)
        self.grimoire_spell_combo.clear()
        for spell in spells:
            self.grimoire_spell_combo.addItem(spell["name"], spell["id"])
            index = self.grimoire_spell_combo.count() - 1
            if spell.get("description"):
                self.grimoire_spell_combo.setItemData(index, spell["description"], Qt.ToolTipRole)
        selected = self.grimoire_spell_combo.findData(automation_config.grimoire_spell_id)
        self.grimoire_spell_combo.setCurrentIndex(selected if selected >= 0 else 0)
        if selected < 0 and self.grimoire_spell_combo.count():
            automation_config.grimoire_spell_id = int(self.grimoire_spell_combo.currentData())
            save_automation_settings()
        self.grimoire_spell_combo.blockSignals(False)

    def _activity_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setContentsMargins(14, 16, 14, 14); group = QGroupBox("Registro de atividades"); group_layout = QVBoxLayout(group)
        self.log_text = QTextEdit(); self.log_text.setReadOnly(True); self.log_text.setMinimumHeight(230); group_layout.addWidget(self.log_text); layout.addWidget(group); return tab

    def _garden_tab(self):
        """Cria a visão de progresso, planejamento e autorização do Garden."""
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setContentsMargins(14, 14, 14, 14); layout.setSpacing(10)
        toolbar = QHBoxLayout()
        self.garden_status_label = QLabel("Garden: carregando")
        self.garden_status_label.setStyleSheet("color: #9aa7ba; font-weight: 600;")
        self.garden_progress_label = QLabel("Sementes: —")
        self.garden_refresh_button = QPushButton("Atualizar snapshot")
        self.garden_refresh_button.clicked.connect(self.refresh_garden)
        self.garden_simulate_button = QPushButton("Simular próximo tick")
        self.garden_simulate_button.setObjectName("primaryButton")
        self.garden_simulate_button.clicked.connect(self.simulate_garden)
        self.garden_auto_checkbox = QCheckBox("Automação real")
        self.garden_auto_checkbox.setToolTip(
            "Uma vez por tick, preserva o que está correto, remove plantas divergentes e monta todo o layout da meta."
        )
        self.garden_auto_checkbox.setChecked(automation_config.enable_garden_automation)
        self.garden_auto_checkbox.stateChanged.connect(self._toggle_garden_automation)
        toolbar.addWidget(self.garden_status_label); toolbar.addWidget(self.garden_progress_label); toolbar.addStretch()
        toolbar.addWidget(self.garden_refresh_button); toolbar.addWidget(self.garden_simulate_button); toolbar.addWidget(self.garden_auto_checkbox)
        layout.addLayout(toolbar)

        goal_group = QGroupBox("Próxima meta prioritária"); goal_layout = QVBoxLayout(goal_group)
        self.garden_goal_label = QLabel("Aguardando snapshot do Garden.")
        self.garden_goal_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #f4f7fc;")
        self.garden_parents_label = QLabel("Pais e requisitos: —")
        self.garden_reason_label = QLabel("")
        self.garden_reason_label.setWordWrap(True); self.garden_parents_label.setWordWrap(True)
        goal_layout.addWidget(self.garden_goal_label); goal_layout.addWidget(self.garden_parents_label); goal_layout.addWidget(self.garden_reason_label)
        layout.addWidget(goal_group)

        plan_group = QGroupBox("Plano antes da execução"); plan_layout = QVBoxLayout(plan_group)
        self.garden_plan_text = QTextEdit(); self.garden_plan_text.setReadOnly(True); self.garden_plan_text.setMinimumHeight(130)
        self.garden_feedback_label = QLabel("A simulação é segura e não altera o jogo.")
        self.garden_feedback_label.setWordWrap(True); self.garden_feedback_label.setStyleSheet("color: #9aa7ba;")
        plan_layout.addWidget(self.garden_plan_text); plan_layout.addWidget(self.garden_feedback_label)
        layout.addWidget(plan_group, 1)
        return tab

    def _auto_ascension_tab(self):
        """Cria os controles e o relatório da máquina de Auto Ascensão."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        warning = QLabel(
            "A ascensão altera permanentemente o save. A execução real só começa "
            "na tela de ascensão, exige habilitação e pede confirmação a cada início."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #e8b766; font-weight: 600;")
        layout.addWidget(warning)

        config_group = QGroupBox("Configuração do ciclo")
        form = QFormLayout(config_group)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.auto_ascension_cycles_input = QSpinBox()
        self.auto_ascension_cycles_input.setRange(1, 10_000)
        self.auto_ascension_cycles_input.setValue(automation_config.auto_ascension_target_cycles)
        self.auto_ascension_cycles_input.valueChanged.connect(self._save_auto_ascension_settings)
        form.addRow("Quantidade alvo de ciclos", self.auto_ascension_cycles_input)

        self.auto_ascension_prestige_input = QDoubleSpinBox()
        self.auto_ascension_prestige_input.setRange(0.0, 1e300)
        self.auto_ascension_prestige_input.setDecimals(0)
        self.auto_ascension_prestige_input.setValue(
            automation_config.auto_ascension_minimum_prestige_gain
        )
        self.auto_ascension_prestige_input.valueChanged.connect(self._save_auto_ascension_settings)
        form.addRow("Ganho mínimo de prestígio", self.auto_ascension_prestige_input)

        self.auto_ascension_interval_input = QDoubleSpinBox()
        self.auto_ascension_interval_input.setRange(0.1, 3600.0)
        self.auto_ascension_interval_input.setDecimals(1)
        self.auto_ascension_interval_input.setSingleStep(0.1)
        self.auto_ascension_interval_input.setSuffix(" s")
        self.auto_ascension_interval_input.setValue(
            automation_config.auto_ascension_poll_interval_seconds
        )
        self.auto_ascension_interval_input.valueChanged.connect(self._save_auto_ascension_settings)
        form.addRow("Intervalo de verificação", self.auto_ascension_interval_input)

        self.auto_ascension_timeout_input = QSpinBox()
        self.auto_ascension_timeout_input.setRange(1, 31_536_000)
        self.auto_ascension_timeout_input.setSuffix(" s")
        self.auto_ascension_timeout_input.setValue(
            automation_config.auto_ascension_max_cycle_seconds
        )
        self.auto_ascension_timeout_input.valueChanged.connect(self._save_auto_ascension_settings)
        form.addRow("Tempo máximo por ciclo", self.auto_ascension_timeout_input)
        layout.addWidget(config_group)

        status_group = QGroupBox("Acompanhamento")
        status_form = QFormLayout(status_group)
        self.auto_ascension_state_label = QLabel("Não iniciada")
        self.auto_ascension_cycle_label = QLabel("0 / —")
        self.auto_ascension_last_action_label = QLabel("Nenhuma ação executada.")
        self.auto_ascension_next_step_label = QLabel("Gere uma prévia para ler o jogo.")
        self.auto_ascension_stop_reason_label = QLabel("—")
        for label in (
            self.auto_ascension_last_action_label,
            self.auto_ascension_next_step_label,
            self.auto_ascension_stop_reason_label,
        ):
            label.setWordWrap(True)
        status_form.addRow("Estado atual", self.auto_ascension_state_label)
        status_form.addRow("Ciclo atual / total", self.auto_ascension_cycle_label)
        status_form.addRow("Última ação", self.auto_ascension_last_action_label)
        status_form.addRow("Próximo passo", self.auto_ascension_next_step_label)
        status_form.addRow("Parada ou erro", self.auto_ascension_stop_reason_label)
        layout.addWidget(status_group, 1)

        controls = QHBoxLayout()
        self.auto_ascension_enable_checkbox = QCheckBox("Habilitar automação real")
        self.auto_ascension_enable_checkbox.setChecked(automation_config.enable_auto_ascension)
        self.auto_ascension_enable_checkbox.stateChanged.connect(self._toggle_auto_ascension_enabled)
        self.auto_ascension_simulation_checkbox = QCheckBox("Modo simulação")
        self.auto_ascension_simulation_checkbox.setChecked(True)
        self.auto_ascension_preview_button = QPushButton("Atualizar prévia")
        self.auto_ascension_preview_button.clicked.connect(self.refresh_auto_ascension_preview)
        self.auto_ascension_start_button = QPushButton("Iniciar")
        self.auto_ascension_start_button.setObjectName("primaryButton")
        self.auto_ascension_start_button.clicked.connect(self.start_auto_ascension)
        self.auto_ascension_stop_button = QPushButton("Parar imediatamente")
        self.auto_ascension_stop_button.setObjectName("dangerButton")
        self.auto_ascension_stop_button.setEnabled(False)
        self.auto_ascension_stop_button.clicked.connect(self.stop_auto_ascension)
        controls.addWidget(self.auto_ascension_enable_checkbox)
        controls.addWidget(self.auto_ascension_simulation_checkbox)
        controls.addStretch()
        controls.addWidget(self.auto_ascension_preview_button)
        controls.addWidget(self.auto_ascension_start_button)
        controls.addWidget(self.auto_ascension_stop_button)
        layout.addLayout(controls)
        return tab

    def _save_auto_ascension_settings(self, _value=None):
        automation_config.auto_ascension_target_cycles = self.auto_ascension_cycles_input.value()
        automation_config.auto_ascension_minimum_prestige_gain = (
            self.auto_ascension_prestige_input.value()
        )
        automation_config.auto_ascension_poll_interval_seconds = (
            self.auto_ascension_interval_input.value()
        )
        automation_config.auto_ascension_max_cycle_seconds = (
            self.auto_ascension_timeout_input.value()
        )
        save_automation_settings()

    def _toggle_auto_ascension_enabled(self, state: int):
        automation_config.enable_auto_ascension = bool(state)
        save_automation_settings()
        logger.info(
            f"Auto Ascensão: execução real {'habilitada' if state else 'desabilitada'}"
        )

    def _auto_ascension_configuration(self, simulation: bool) -> ConfiguracaoAutoAscensao:
        self._save_auto_ascension_settings()
        return ConfiguracaoAutoAscensao(
            ciclos_alvo=self.auto_ascension_cycles_input.value(),
            ganho_minimo_prestigio=self.auto_ascension_prestige_input.value(),
            intervalo_verificacao=self.auto_ascension_interval_input.value(),
            duracao_maxima_ciclo=self.auto_ascension_timeout_input.value(),
            simulacao=simulation,
        )

    def refresh_auto_ascension_preview(self, _checked: bool = False):
        """Gera uma prévia em worker, sem qualquer operação mutável."""
        if not self.bridge:
            self._auto_ascension_failed("Bridge não está disponível.")
            return
        if self._auto_ascension_worker and self._auto_ascension_worker.isRunning():
            return
        automation = AutoAscensao(
            self.bridge, self._auto_ascension_configuration(simulation=True)
        )
        self._run_auto_ascension_worker(automation, preview=True)

    def start_auto_ascension(self, _checked: bool = False):
        """Inicia uma simulação ou, após confirmação, a execução real."""
        if self.auto_ascension_simulation_checkbox.isChecked():
            self.refresh_auto_ascension_preview()
            return
        if not self.bridge:
            self._auto_ascension_failed("Bridge não está disponível.")
            return
        if not self.auto_ascension_enable_checkbox.isChecked():
            self._auto_ascension_failed(
                "Marque “Habilitar automação real” antes de iniciar."
            )
            return
        if not self.runner:
            self._auto_ascension_failed("Runner do clicker não está disponível.")
            return
        if self._auto_ascension_worker and self._auto_ascension_worker.isRunning():
            return
        answer = QMessageBox.warning(
            self,
            "Confirmar Auto Ascensão",
            "A execução real pode comprar itens, reincarnar e ascender. "
            "Ascender altera permanentemente o save.\n\n"
            "Confirma o início a partir da tela de ascensão?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            logger.info("Auto Ascensão: início real cancelado pelo usuário")
            return
        automation = AutoAscensao(
            self.bridge,
            self._auto_ascension_configuration(simulation=False),
            habilitar_producao=self.runner.ensure_clicker_running,
            desabilitar_producao=self.runner.ensure_clicker_stopped,
        )
        self._run_auto_ascension_worker(automation, preview=False)

    def _run_auto_ascension_worker(self, automation: AutoAscensao, preview: bool):
        self._auto_ascension = automation
        worker = AutoAscensaoWorker(automation, preview, self)
        self._auto_ascension_worker = worker
        worker.updated.connect(self._display_auto_ascension_report)
        worker.completed.connect(self._display_auto_ascension_report)
        worker.failed.connect(self._auto_ascension_failed)
        worker.finished.connect(self._auto_ascension_finished)
        self._set_auto_ascension_busy(True, preview)
        worker.start()

    def stop_auto_ascension(self, _checked: bool = False):
        """Solicita parada cooperativa e bloqueia o início de novas mutações."""
        if self._auto_ascension_worker and self._auto_ascension_worker.isRunning():
            self._auto_ascension_worker.stop()
            self.auto_ascension_stop_button.setEnabled(False)
            self.auto_ascension_next_step_label.setText(
                "Parada solicitada; nenhuma nova ação mutável será iniciada."
            )
            logger.warning("Auto Ascensão: parada imediata solicitada pelo usuário")

    def _display_auto_ascension_report(self, value: object):
        if not isinstance(value, RelatorioAutoAscensao):
            self._auto_ascension_failed("Relatório inválido recebido da automação.")
            return
        self.auto_ascension_state_label.setText(value.estado.value)
        self.auto_ascension_cycle_label.setText(f"{value.ciclo_atual} / {value.ciclos_alvo}")
        self.auto_ascension_last_action_label.setText(value.ultima_acao)
        self.auto_ascension_next_step_label.setText(value.proximo_passo)
        self.auto_ascension_stop_reason_label.setText(value.motivo_parada or "—")
        color = "#f07883" if value.motivo_parada and value.estado.value != "Concluído" else "#65d6a5"
        self.auto_ascension_state_label.setStyleSheet(f"color: {color}; font-weight: 700;")

    def _auto_ascension_failed(self, message: str):
        self.auto_ascension_state_label.setText("Erro seguro")
        self.auto_ascension_state_label.setStyleSheet("color: #f07883; font-weight: 700;")
        self.auto_ascension_stop_reason_label.setText(message)
        logger.error(f"Auto Ascensão: {message}")

    def _auto_ascension_finished(self):
        self._set_auto_ascension_busy(False, preview=False)
        worker = self._auto_ascension_worker
        self._auto_ascension_worker = None
        self._auto_ascension = None
        if worker:
            worker.deleteLater()

    def _set_auto_ascension_busy(self, busy: bool, preview: bool):
        for control in (
            self.auto_ascension_cycles_input,
            self.auto_ascension_prestige_input,
            self.auto_ascension_interval_input,
            self.auto_ascension_timeout_input,
            self.auto_ascension_enable_checkbox,
            self.auto_ascension_simulation_checkbox,
            self.auto_ascension_preview_button,
            self.auto_ascension_start_button,
        ):
            control.setEnabled(not busy)
        self.auto_ascension_stop_button.setEnabled(busy and not preview)

    def _settings_tab(self):
        tab = QWidget(); outer_layout = QVBoxLayout(tab); outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget(); layout = QVBoxLayout(content); layout.setContentsMargins(14, 10, 14, 14); layout.setSpacing(8)

        automation_group = QGroupBox("Automações"); automation_form = QFormLayout(automation_group)
        automation_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.wrinkler_delay_input = QDoubleSpinBox(); self.wrinkler_delay_input.setRange(0.1, 60.0); self.wrinkler_delay_input.setSingleStep(0.1); self.wrinkler_delay_input.setSuffix(" s"); self.wrinkler_delay_input.setMaximumWidth(140); self.wrinkler_delay_input.setValue(automation_config.wrinkler_pop_delay); self.wrinkler_delay_input.valueChanged.connect(self.update_wrinkler_delay); self.wrinkler_delay_input.setEnabled(automation_config.enable_wrinkler_popper)
        automation_form.addRow("Intervalo entre Wrinklers", self.wrinkler_delay_input)
        self.grimoire_spell_combo = QComboBox(); self.grimoire_spell_combo.setMinimumWidth(230)
        self._load_grimoire_spells()
        self.grimoire_spell_combo.currentIndexChanged.connect(self.update_grimoire_spell)
        self.grimoire_spell_combo.setEnabled(automation_config.enable_grimoire_spell_spam)
        automation_form.addRow("Skill do Grimoire", self.grimoire_spell_combo)
        layout.addWidget(automation_group)

        sugar_group = QGroupBox("Sugar Lumps"); sugar_form = QFormLayout(sugar_group)
        preserve_grid = QGridLayout(); entries = (("Tipo 0", 0), ("Tipo 1", 1), ("Golden", 2), ("Tipo 3", 3), ("Caramel", 4)); self._preserve_checkboxes = []
        for index, (text, number) in enumerate(entries):
            checkbox = QCheckBox(text); checkbox.setChecked(getattr(automation_config, f"preserve_sugar_lump_type_{number}")); checkbox.stateChanged.connect(lambda state, n=number: self._set_sugar_lump_type(n, state)); preserve_grid.addWidget(checkbox, index // 3, index % 3); self._preserve_checkboxes.append(checkbox)
        sugar_form.addRow("Tipos preservados", preserve_grid)
        layout.addWidget(sugar_group)
        self.set_sugar_lump_preserve_enabled(automation_config.enable_sugar_lump_harvest)

        stock_group = QGroupBox("Stock Market"); stock_form = QFormLayout(stock_group)
        stock_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.stock_buy_limit_input = QDoubleSpinBox(); self.stock_buy_limit_input.setRange(0.01, 1_000_000_000.0); self.stock_buy_limit_input.setDecimals(2); self.stock_buy_limit_input.setPrefix("$ "); self.stock_buy_limit_input.setMaximumWidth(150); self.stock_buy_limit_input.setValue(automation_config.stock_market_buy_price_limit); self.stock_buy_limit_input.valueChanged.connect(self._update_stock_buy_limit)
        stock_form.addRow("Limite geral de compra", self.stock_buy_limit_input)
        self.stock_sell_limit_input = QDoubleSpinBox(); self.stock_sell_limit_input.setRange(0.01, 1_000_000_000.0); self.stock_sell_limit_input.setDecimals(2); self.stock_sell_limit_input.setPrefix("$ "); self.stock_sell_limit_input.setMaximumWidth(150); self.stock_sell_limit_input.setValue(automation_config.stock_market_sell_price_limit); self.stock_sell_limit_input.valueChanged.connect(self._update_stock_sell_limit)
        stock_form.addRow("Limite geral de venda", self.stock_sell_limit_input)
        self.stock_trend_ticks_input = QSpinBox(); self.stock_trend_ticks_input.setRange(2, 64); self.stock_trend_ticks_input.setSuffix(" ticks"); self.stock_trend_ticks_input.setMaximumWidth(120); self.stock_trend_ticks_input.setValue(automation_config.stock_market_trend_ticks); self.stock_trend_ticks_input.setToolTip("Quantidade de ticks usada para validar a tendência"); self.stock_trend_ticks_input.valueChanged.connect(self._update_stock_trend_ticks)
        stock_form.addRow("Janela de análise", self.stock_trend_ticks_input)
        self.stock_reversal_percent_input = QDoubleSpinBox(); self.stock_reversal_percent_input.setRange(0.01, 100.0); self.stock_reversal_percent_input.setDecimals(2); self.stock_reversal_percent_input.setSuffix(" %"); self.stock_reversal_percent_input.setMaximumWidth(120); self.stock_reversal_percent_input.setValue(automation_config.stock_market_reversal_percent); self.stock_reversal_percent_input.setToolTip("Alta mínima em um tick para confirmar que uma queda terminou"); self.stock_reversal_percent_input.valueChanged.connect(self._update_stock_reversal_percent)
        stock_form.addRow("Confirmação de reversão", self.stock_reversal_percent_input)
        self.stock_owned_only_checkbox = QCheckBox("Mostrar no jogo apenas ativos em estoque")
        self.stock_owned_only_checkbox.setChecked(automation_config.enable_stock_market_owned_only_view)
        self.stock_owned_only_checkbox.stateChanged.connect(self._toggle_stock_owned_only_view)
        stock_form.addRow("Visualização no jogo", self.stock_owned_only_checkbox)
        self.stock_limits_button = QPushButton("Configurar limites por ativo")
        self.stock_limits_button.clicked.connect(self._configure_stock_limits)
        self.stock_limits_button.setEnabled(False)
        stock_form.addRow("Limites por ativo", self.stock_limits_button)
        stock_hint = QLabel("A estratégia é única: compra abaixo do limite após estabilização e vende com lucro após reversão ou queda de 10% do pico.")
        stock_hint.setWordWrap(True); stock_hint.setStyleSheet("color: #9aa7ba;")
        stock_form.addRow(stock_hint)
        layout.addWidget(stock_group)

        garden_group = QGroupBox("Garden"); garden_form = QFormLayout(garden_group)
        garden_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.garden_interval_input = QSpinBox(); self.garden_interval_input.setRange(30, 3600); self.garden_interval_input.setSuffix(" s"); self.garden_interval_input.setMaximumWidth(140)
        self.garden_interval_input.setValue(automation_config.garden_poll_interval_seconds)
        self.garden_interval_input.setToolTip("Intervalo de fallback quando o próximo tick não puder ser lido do jogo")
        self.garden_interval_input.valueChanged.connect(self._update_garden_interval)
        garden_form.addRow("Fallback de consulta", self.garden_interval_input)
        garden_hint = QLabel("A automação inicia desativada. Quando ligada, sincroniza com M.nextStep e reconcilia o layout inteiro uma vez por tick.")
        garden_hint.setWordWrap(True); garden_hint.setStyleSheet("color: #9aa7ba;")
        garden_form.addRow(garden_hint); layout.addWidget(garden_group)

        interface_group = QGroupBox("Interface"); interface_layout = QHBoxLayout(interface_group)
        interface_layout.addWidget(QLabel("Máximo de linhas no registro")); interface_layout.addStretch()
        self.log_limit_input = QSpinBox(); self.log_limit_input.setRange(1, 100000); self.log_limit_input.setValue(app_config.max_log_lines); self.log_limit_input.setToolTip("Limita apenas o histórico exibido na aba Atividade"); self.log_limit_input.valueChanged.connect(self.update_log_limit)
        interface_layout.addWidget(self.log_limit_input)
        layout.addWidget(interface_group); layout.addStretch()
        scroll.setWidget(content); outer_layout.addWidget(scroll); return tab

    def _stock_market_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setContentsMargins(14, 12, 14, 12); layout.setSpacing(8)
        toolbar = QWidget(); toolbar_layout = QHBoxLayout(toolbar); toolbar_layout.setContentsMargins(0, 0, 0, 0); toolbar_layout.setSpacing(4)
        self.stock_status_label = QLabel("Mercado: carregando")
        self.stock_status_label.setStyleSheet("color: #9aa7ba; font-weight: 600;")
        self.stock_status_label.setMinimumWidth(0)
        self.stock_total_profit_label = QLabel("Lucro total: —")
        self.stock_total_profit_label.setStyleSheet("color: #9aa7ba; font-weight: 600;")
        self.stock_total_profit_label.setToolTip("Valor atual menos o valor no início desta sessão")
        self.stock_goal_label = QLabel("Meta: —")
        self.stock_auto_trade_checkbox = QCheckBox("Automação")
        self.stock_auto_trade_checkbox.setToolTip(
            "Liga ou desliga compras e vendas automáticas em ordens MAX"
        )
        self.stock_auto_trade_checkbox.setChecked(automation_config.enable_stock_market_auto_trade)
        self.stock_auto_trade_checkbox.stateChanged.connect(self._toggle_stock_auto_trade)
        toolbar_layout.addWidget(self.stock_status_label)
        toolbar_layout.addWidget(self.stock_total_profit_label)
        toolbar_layout.addWidget(self.stock_goal_label)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.stock_auto_trade_checkbox)
        self.stock_candidates_label = QLabel()
        self.stock_candidates_label.setStyleSheet("color: #e8b766;")
        layout.addWidget(toolbar)

        self.stock_table = QTableWidget(0, 7)
        self.stock_table.setHorizontalHeaderLabels(
            ("Ativo", "Preço", "Variação", "5 ticks", "Últ. compra", "Lucro", "Estoque")
        )
        self.stock_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.stock_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.stock_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.stock_table.verticalHeader().setVisible(False)
        header = self.stock_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSortIndicator(1, Qt.AscendingOrder)
        header.setSortIndicatorShown(True)
        self.stock_table.setSortingEnabled(True)
        self.stock_table.itemSelectionChanged.connect(self._update_stock_actions)
        self.stock_table.setMinimumHeight(0)
        layout.addWidget(self.stock_table, 1)

        order_bar = QWidget(); order_bar.setObjectName("stockOrderBar")
        order_bar.setStyleSheet("#stockOrderBar { background: #1b2028; border-top: 1px solid #37404e; border-radius: 0 0 6px 6px; }")
        order_layout = QHBoxLayout(order_bar); order_layout.setContentsMargins(10, 7, 10, 7); order_layout.setSpacing(8)
        self.stock_selected_asset_label = QLabel("Selecione um ativo")
        self.stock_selected_asset_label.setStyleSheet("color: #9aa7ba;")
        order_layout.addWidget(self.stock_selected_asset_label); order_layout.addStretch()
        order_layout.addWidget(QLabel("Qtd."))
        self.stock_quantity_input = QSpinBox(); self.stock_quantity_input.setRange(1, 9_999); self.stock_quantity_input.setValue(1)
        self.stock_use_max_checkbox = QCheckBox("Usar máximo")
        self.stock_use_max_checkbox.stateChanged.connect(self._toggle_stock_maximum)
        self.stock_buy_button = QPushButton("Comprar"); self.stock_buy_button.setObjectName("primaryButton")
        self.stock_sell_button = QPushButton("Vender"); self.stock_sell_button.setObjectName("dangerButton")
        self.stock_buy_button.clicked.connect(lambda: self._submit_stock_order("buy"))
        self.stock_sell_button.clicked.connect(lambda: self._submit_stock_order("sell"))
        self.stock_buy_button.setEnabled(False); self.stock_sell_button.setEnabled(False); self.stock_use_max_checkbox.setEnabled(False)
        order_layout.addWidget(self.stock_quantity_input); order_layout.addWidget(self.stock_use_max_checkbox)
        order_layout.addWidget(self.stock_buy_button); order_layout.addWidget(self.stock_sell_button)
        self.stock_feedback_label = QLabel()
        self.stock_feedback_label.hide()
        layout.addWidget(order_bar)
        return tab

    def refresh_stock_market(self, automatic: bool = False):
        """Solicita um snapshot manual sem bloquear a thread da interface."""
        if not self.bridge:
            self._show_stock_unavailable("Bridge não está disponível")
            logger.warning("Stock Market: bridge não está disponível para atualização")
            return
        if not automatic:
            logger.info("Stock Market: atualização manual solicitada")
        operation = self.stock_automation.capture_snapshot if self.stock_automation else self.bridge.get_stock_market_snapshot
        self._run_stock_task(operation, self._display_stock_snapshot)

    def _on_stock_market_timer(self):
        """Atualiza o snapshot a cada 5 segundos e aplica a regra somente se autorizada."""
        if not self.bridge or (self._stock_worker and self._stock_worker.isRunning()):
            return
        if not self.stock_automation:
            self.refresh_stock_market(automatic=True)
            return
        buy_limit = float(self.stock_buy_limit_input.value())
        sell_limit = float(self.stock_sell_limit_input.value())
        trend_ticks = int(self.stock_trend_ticks_input.value())
        reversal_percent = float(self.stock_reversal_percent_input.value())
        execute_orders = self.stock_auto_trade_checkbox.isChecked()
        owned_only_view = self.stock_owned_only_checkbox.isChecked()
        per_asset_limits = {key: dict(value) for key, value in automation_config.stock_market_asset_limits.items()}
        use_reference_prices = automation_config.stock_market_use_reference_prices
        self._run_stock_task(
            lambda: self.stock_automation.run_cycle(
                buy_limit,
                sell_limit,
                trend_ticks,
                reversal_percent,
                execute_orders,
                owned_only_view,
                per_asset_limits=per_asset_limits,
                use_reference_prices=use_reference_prices,
            ),
            self._display_stock_automation_result,
        )

    def _configure_stock_limits(self):
        if not self._stock_snapshot or not self._stock_snapshot.status.available:
            self._show_stock_feedback(False, "Aguarde a leitura do mercado para configurar os ativos.")
            return
        dialog = StockLimitsDialog(
            self._stock_snapshot, automation_config.stock_market_asset_limits,
            automation_config.stock_market_use_reference_prices, self,
            buy_limit=self.stock_buy_limit_input.value(), sell_limit=self.stock_sell_limit_input.value(),
        )
        if dialog.exec_():
            automation_config.stock_market_asset_limits = dialog.overrides
            automation_config.stock_market_use_reference_prices = dialog.use_reference_prices
            save_automation_settings()
            self._display_stock_snapshot(self._stock_snapshot)
            logger.info("Mercado: limites por ativo atualizados.")

    def _limits_for_asset(self, asset):
        return asset_limits(
            asset, self.stock_buy_limit_input.value(), self.stock_sell_limit_input.value(),
            automation_config.stock_market_asset_limits, automation_config.stock_market_use_reference_prices,
        )

    def _toggle_stock_auto_trade(self, state: int):
        automation_config.enable_stock_market_auto_trade = bool(state)
        save_automation_settings()
        status = "ativado" if state else "desativado"
        logger.info(f"Stock Market: automação {status}")
        self._show_stock_feedback(bool(state), f"Automação {status}.")

    def _toggle_stock_owned_only_view(self, state: int):
        enabled = bool(state)
        automation_config.enable_stock_market_owned_only_view = enabled
        save_automation_settings()
        if not self.bridge:
            return
        self._run_stock_task(
            lambda: self.bridge.set_stock_market_owned_only_view(enabled),
            lambda value: self._show_stock_feedback(
                bool(value),
                "Visualização: somente ativos possuídos." if enabled else "Visualização: todos os ativos.",
            ),
        )

    def _update_stock_buy_limit(self, value: float):
        automation_config.stock_market_buy_price_limit = float(value)
        save_automation_settings()
        self._update_stock_candidates()

    def _update_stock_sell_limit(self, value: float):
        automation_config.stock_market_sell_price_limit = float(value)
        save_automation_settings()

    def _update_stock_trend_ticks(self, value: int):
        automation_config.stock_market_trend_ticks = max(2, int(value))
        save_automation_settings()
        self._update_stock_trend_variation_header()

    def _update_stock_reversal_percent(self, value: float):
        automation_config.stock_market_reversal_percent = max(0.01, float(value))
        save_automation_settings()

    def _submit_stock_order(self, side: str):
        if not self.bridge:
            self._show_stock_feedback(False, "Bridge não está disponível")
            return
        selected_rows = self.stock_table.selectionModel().selectedRows()
        if not selected_rows:
            self._show_stock_feedback(False, "Selecione um ativo antes de enviar a ordem.")
            logger.warning("Stock Market: ordem manual sem ativo selecionado")
            return
        id_item = self.stock_table.item(selected_rows[0].row(), 0)
        asset_id = id_item.data(Qt.UserRole) if id_item else None
        if isinstance(asset_id, bool) or not isinstance(asset_id, int) or asset_id < 0:
            self._show_stock_feedback(False, "Identificador do ativo selecionado é inválido.")
            logger.error("Stock Market: identificador inválido na tabela")
            return
        quantity = int(self.stock_quantity_input.value())
        is_maximum_order = self.stock_use_max_checkbox.isChecked()
        operation = (
            self.bridge.buy_stock_max if side == "buy" else self.bridge.sell_stock_max
        ) if is_maximum_order else (
            self.bridge.buy_stock if side == "buy" else self.bridge.sell_stock
        )
        order_label = "máxima" if is_maximum_order else f"quantidade={quantity}"
        logger.info(f"Stock Market: ordem manual solicitada (lado={side}, ativo={asset_id}, {order_label})")
        task = (lambda: operation(asset_id)) if is_maximum_order else (lambda: operation(asset_id, quantity))
        self._run_stock_task(task, self._display_stock_trade_result)

    def _run_stock_task(self, operation: Callable[[], object], handler: Callable[[object], None]):
        if self._stock_worker and self._stock_worker.isRunning():
            self._show_stock_feedback(False, "Aguarde a operação atual terminar.")
            return
        self._set_stock_busy(True)
        worker = StockMarketWorker(operation, self)
        self._stock_worker = worker
        worker.completed.connect(handler)
        worker.failed.connect(self._stock_task_failed)
        worker.finished.connect(self._stock_task_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _stock_task_failed(self, message: str):
        logger.error(f"Stock Market: falha inesperada no worker: {message}")
        self._show_stock_feedback(False, f"Falha inesperada: {message}")

    def _stock_task_finished(self):
        self._stock_worker = None
        self._set_stock_busy(False)
        if self._refresh_after_order:
            self._refresh_after_order = False
            QTimer.singleShot(0, self.refresh_stock_market)

    def _display_stock_snapshot(self, value: object):
        if not isinstance(value, StockMarketSnapshot):
            self._show_stock_unavailable("Resposta inesperada do bridge")
            logger.error("Stock Market: worker retornou snapshot inválido")
            return
        snapshot = value
        self._stock_snapshot = snapshot
        self._stock_available = snapshot.status.available
        self.stock_limits_button.setEnabled(snapshot.status.available)
        color = "#65d6a5" if snapshot.status.available else ("#e8b766" if snapshot.status.unlocked else "#f07883")
        status_text = "Mercado: disponível" if snapshot.status.available else (
            "Mercado: carregando" if snapshot.status.unlocked else "Mercado: indisponível"
        )
        self.stock_status_label.setVisible(not snapshot.status.available)
        self.stock_status_label.setText(status_text if not snapshot.status.available else "")
        self.stock_status_label.setToolTip(snapshot.status.message)
        self.stock_status_label.setStyleSheet(f"color: {color}; font-weight: 600;")
        self.stock_table.setSortingEnabled(False)
        self.stock_table.setRowCount(0)
        if not snapshot.status.available:
            self.stock_total_profit_label.setText("Lucro total: —")
            self.stock_goal_label.setText("Meta: —")
            self.stock_candidates_label.setText("")
            self._show_stock_feedback(False, snapshot.status.message)
            self.stock_table.setSortingEnabled(True)
            self._update_stock_actions()
            return
        total_profit = self.stock_automation.total_profit(snapshot) if self.stock_automation else None
        self.stock_total_profit_label.setText(self._format_stock_total_profit(total_profit))
        if snapshot.gaseous_assets_won:
            self.stock_goal_label.setText("Meta: concluída")
        elif snapshot.profit is not None:
            self.stock_goal_label.setText(f"Meta: {max(0, snapshot.profit) / GASEOUS_ASSETS_TARGET:.1%}")
        else:
            self.stock_goal_label.setText("Meta: —")
        self.stock_goal_label.setToolTip(
            f"Saldo do jogo: {self._format_stock_amount(snapshot.profit)} / $31,536,000.00\n"
            "O achievement considera este saldo, que já desconta compras; ações abertas não contam."
        )
        assets_by_price = sorted(snapshot.assets, key=lambda asset: asset.price)
        self.stock_table.setRowCount(len(assets_by_price))
        trend_ticks = int(self.stock_trend_ticks_input.value())
        self._update_stock_trend_variation_header()
        for row, asset in enumerate(assets_by_price):
            buy_limit, sell_limit = self._limits_for_asset(asset)
            variation = self._format_variation(asset.price_change_percent)
            trend_value = self._stock_trend_variation(asset, trend_ticks)
            trend_variation = self._format_variation(trend_value)
            purchase_price = asset.last_bought_price if asset.owned > 0 else None
            gross_profit = self._stock_gross_profit(asset)
            name = f"{asset.name} ({asset.symbol})" if asset.symbol else asset.name
            values = (
                (name, name),
                (f"${asset.price:,.2f}", asset.price),
                (variation, asset.price_change_percent),
                (trend_variation, trend_value),
                (f"${purchase_price:,.2f}" if purchase_price is not None else "—", purchase_price),
                (self._format_stock_amount(gross_profit), gross_profit),
                (str(asset.owned) if asset.owned > 0 else "—", asset.owned),
            )
            for column, (text, sort_value) in enumerate(values):
                item = SortableTableWidgetItem(text, sort_value)
                if column == 0:
                    item.setData(Qt.UserRole, asset.asset_id)
                    item.setToolTip(f"Compra < ${buy_limit:.2f} | Modo venda ≥ ${sell_limit:.2f}")
                if column == 2 and asset.price_change_percent is not None:
                    item.setForeground(Qt.green if asset.price_change_percent >= 0 else Qt.red)
                if column in (3, 5) and sort_value is not None:
                    item.setForeground(Qt.green if sort_value >= 0 else Qt.red)
                if asset.price < buy_limit:
                    item.setBackground(QColor("#3a3420"))
                if column in (1, 2, 3, 4, 5, 6):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.stock_table.setItem(row, column, item)
        self.stock_table.setSortingEnabled(True)
        self.stock_table.sortItems(
            self.stock_table.horizontalHeader().sortIndicatorSection(),
            self.stock_table.horizontalHeader().sortIndicatorOrder(),
        )
        self._update_stock_candidates()
        self._show_stock_feedback(True, f"{len(snapshot.assets)} ativos carregados (preço crescente).")
        self._update_stock_actions()
        logger.debug(f"Stock Market: snapshot carregado com {len(snapshot.assets)} ativos")

    def refresh_garden(self, _checked: bool = False):
        """Atualiza snapshot e plano sem alterar o Garden."""
        if not self.fazendeira:
            self._show_garden_feedback(False, "Bridge não está disponível.")
            return
        self._run_garden_task(
            lambda: self.fazendeira.run_cycle(dry_run=True, automation_enabled=False),
            self._display_garden_result,
        )

    def simulate_garden(self, _checked: bool = False):
        """Executa somente a leitura e o planejamento da Fazendeira."""
        if not self.fazendeira:
            self._show_garden_feedback(False, "Bridge não está disponível.")
            return
        logger.info("Garden: simulação solicitada; nenhuma ação será enviada ao jogo")
        self._run_garden_task(
            lambda: self.fazendeira.run_cycle(dry_run=True, automation_enabled=False),
            self._display_garden_result,
        )

    def _on_garden_timer(self):
        if not self.fazendeira or (self._garden_worker and self._garden_worker.isRunning()):
            return
        self._garden_run_when_idle = False
        enabled = self.garden_auto_checkbox.isChecked()
        self._run_garden_task(
            lambda: self.fazendeira.run_cycle(
                dry_run=not enabled, automation_enabled=enabled,
            ),
            self._display_garden_result,
        )

    def _run_garden_task(self, operation: Callable[[], object], handler: Callable[[object], None]):
        if self._garden_worker and self._garden_worker.isRunning():
            self._show_garden_feedback(False, "Aguarde a consulta atual do Garden terminar.")
            return
        self._set_garden_busy(True)
        worker = StockMarketWorker(operation, self)
        self._garden_worker = worker
        worker.completed.connect(handler)
        worker.failed.connect(self._garden_task_failed)
        worker.finished.connect(self._garden_task_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _garden_task_failed(self, message: str):
        logger.error(f"Garden: falha inesperada no worker: {message}")
        self._show_garden_feedback(False, f"Falha inesperada: {message}")
        self._schedule_next_garden_tick(None)

    def _garden_task_finished(self):
        self._garden_worker = None
        self._set_garden_busy(False)
        if self._garden_run_when_idle and self.garden_auto_checkbox.isChecked():
            QTimer.singleShot(0, self._on_garden_timer)

    def _display_garden_result(self, value: object):
        if not isinstance(value, GardenCycleResult):
            self._show_garden_feedback(False, "Resposta inesperada do ciclo do Garden.")
            logger.error("Garden: worker retornou resultado inválido")
            return
        snapshot, plan = value.snapshot, value.plan
        self._schedule_next_garden_tick(snapshot)
        self._garden_available = snapshot.status.available
        color = "#65d6a5" if snapshot.status.available else (
            "#e8b766" if snapshot.status.unlocked else "#f07883"
        )
        status_text = "Garden: disponível" if snapshot.status.available else (
            "Garden: carregando" if snapshot.status.unlocked else "Garden: indisponível"
        )
        self.garden_status_label.setText(status_text)
        self.garden_status_label.setToolTip(snapshot.status.message)
        self.garden_status_label.setStyleSheet(f"color: {color}; font-weight: 600;")
        unlocked = sum(seed.unlocked for seed in snapshot.seeds)
        self.garden_progress_label.setText(
            f"Sementes: {unlocked}/{len(snapshot.seeds)}" if snapshot.seeds else "Sementes: —"
        )
        if not snapshot.status.available:
            self.garden_goal_label.setText("Garden indisponível")
            self.garden_parents_label.setText("Pais e requisitos: —")
            self.garden_reason_label.setText(snapshot.status.message)
            self.garden_plan_text.setPlainText("Nenhuma ação foi planejada.")
            self._show_garden_feedback(False, snapshot.status.message)
            return
        if plan.goal is None:
            incompatible = plan.explanation.startswith("Catálogo incompatível")
            self.garden_goal_label.setText("Catálogo incompatível" if incompatible else "Coleção completa")
            self.garden_parents_label.setText(
                "A automação foi bloqueada até que as receitas sejam revisadas."
                if incompatible else "Todas as sementes foram confirmadas no snapshot do jogo."
            )
            self.garden_reason_label.setText(plan.explanation)
        else:
            goal = plan.goal
            self.garden_goal_label.setText(goal.target_name)
            parents = ", ".join(goal.parent_names) if goal.parent_names else "nenhum (condição especial)"
            self.garden_parents_label.setText(f"Pais e requisitos: {parents}")
            pending = f" Pendentes: {', '.join(goal.pending_prerequisites)}." if goal.pending_prerequisites else ""
            self.garden_reason_label.setText(
                f"{goal.reason}{pending} Condição de sucesso: {goal.success_condition}"
            )
        action_lines = [self._format_garden_action(index, action) for index, action in enumerate(plan.actions, 1)]
        plan_text = plan.explanation
        if action_lines:
            plan_text += "\n\n" + "\n".join(action_lines)
        else:
            plan_text += "\n\nNenhuma mutação será enviada neste tick."
        self.garden_plan_text.setPlainText(plan_text)
        if value.action_results:
            successes = sum(result.success for result in value.action_results)
            details = "; ".join(result.message for result in value.action_results)
            self._show_garden_feedback(
                successes == len(value.action_results),
                f"Execução real: {successes}/{len(value.action_results)} ações confirmadas. {details}",
            )
        elif value.dry_run:
            self._show_garden_feedback(True, "Simulação concluída; o estado do jogo não foi alterado.")
        else:
            self._show_garden_feedback(True, "Ciclo real concluído sem nova ação necessária.")

    @staticmethod
    def _format_garden_action(index, action) -> str:
        labels = {
            "plant": "Plantar", "harvest": "Colher", "change_soil": "Trocar solo",
            "set_freeze": "Descongelar",
        }
        if action.kind == "harvest" and not action.require_mature:
            labels["harvest"] = "Remover"
        position = f" em ({action.x}, {action.y})" if action.x is not None and action.y is not None else ""
        subject = action.seed_key or action.soil_key or "Garden"
        return f"{index}. {labels.get(action.kind, action.kind)} {subject}{position} — {action.reason}"

    def _show_garden_feedback(self, success: bool, message: str):
        self.garden_feedback_label.setText(message)
        self.garden_feedback_label.setStyleSheet(f"color: {'#65d6a5' if success else '#f07883'};")
        self.status_bar.showMessage(message, 7000)

    def _set_garden_busy(self, busy: bool):
        self.garden_refresh_button.setEnabled(not busy)
        self.garden_simulate_button.setEnabled(not busy)
        self.garden_auto_checkbox.setEnabled(not busy)
        if busy:
            self.garden_feedback_label.setText("Consultando o runtime do Garden em segundo plano...")
            self.garden_feedback_label.setStyleSheet("color: #9aa7ba;")

    def _toggle_garden_automation(self, state: int):
        enabled = bool(state)
        automation_config.enable_garden_automation = enabled
        save_automation_settings()
        status = "habilitada explicitamente" if enabled else "desativada"
        logger.info(f"Garden: automação real {status}")
        self._show_garden_feedback(
            enabled, f"Automação real {status}." if enabled else "Automação real desativada; somente leitura e simulação.",
        )
        if enabled:
            self.garden_refresh_timer.stop()
            if self._garden_worker and self._garden_worker.isRunning():
                self._garden_run_when_idle = True
            else:
                QTimer.singleShot(0, self._on_garden_timer)

    def _schedule_next_garden_tick(self, snapshot):
        """Agenda uma única leitura logo após ``M.nextStep`` avançar."""
        if not self.bridge:
            return
        fallback_ms = automation_config.garden_poll_interval_seconds * 1000
        delay_ms = fallback_ms
        if snapshot is not None and snapshot.status.available and snapshot.next_tick_at is not None:
            remaining_ms = int((snapshot.next_tick_at - time.time()) * 1000)
            if remaining_ms >= -500:
                delay_ms = max(250, remaining_ms + 250)
            elif self.garden_auto_checkbox.isChecked():
                # O jogo pode estar suspenso em segundo plano; confira sem
                # executar novamente até ``M.nextStep`` realmente avançar.
                delay_ms = 1_000
        self.garden_refresh_timer.start(delay_ms)

    def _update_garden_interval(self, value: int):
        interval = min(3600, max(30, int(value)))
        automation_config.garden_poll_interval_seconds = interval
        save_automation_settings()
        if not self.garden_auto_checkbox.isChecked():
            self.garden_refresh_timer.start(interval * 1000)

    @staticmethod
    def _format_stock_total_profit(total_profit: Optional[float]) -> str:
        if total_profit is None:
            return "Lucro total: —"
        return f"Lucro total: ${total_profit:+,.2f}"

    def _update_stock_trend_variation_header(self):
        ticks = int(self.stock_trend_ticks_input.value())
        self.stock_table.setHorizontalHeaderItem(3, QTableWidgetItem(f"{ticks} ticks"))

    def _stock_trend_variation(self, asset, ticks: int) -> Optional[float]:
        prices = (
            self.stock_automation.history_store.prices_for(asset.asset_id, asset.price_history)
            if self.stock_automation else asset.price_history
        )
        if len(prices) <= ticks or prices[ticks] <= 0:
            return None
        return ((asset.price / prices[ticks]) - 1) * 100

    @staticmethod
    def _stock_gross_profit(asset) -> Optional[float]:
        """Ganho bruto estimado ao vender todas as ações agora."""
        if asset.owned <= 0 or asset.last_bought_price is None or asset.last_bought_price <= 0:
            return None
        return (asset.price - asset.last_bought_price) * asset.owned

    @staticmethod
    def _format_stock_amount(value: Optional[float]) -> str:
        return "—" if value is None else f"${value:+,.2f}"

    def _display_stock_automation_result(self, value: object):
        if not isinstance(value, StockMarketAutomationResult):
            self._show_stock_feedback(False, "Resposta inesperada do ciclo automático.")
            logger.error("Stock Market: worker retornou ciclo automático inválido")
            return
        if value.tick_changed or self._stock_snapshot is None:
            self._display_stock_snapshot(value.snapshot)
        if not value.snapshot.status.available:
            return
        if value.tick_changed:
            entries = sum(signal.is_entry_candidate for signal in value.signals)
            exits = sum(signal.is_exit_candidate for signal in value.signals)
            self.stock_candidates_label.setText(f"{entries} compras | {exits} vendas")
        if value.orders:
            successful = sum(order.success for order in value.orders)
            self._show_stock_feedback(
                successful == len(value.orders),
                f"Automação: {successful}/{len(value.orders)} ordens MAX executadas.",
            )

    def _update_stock_candidates(self):
        if not self._stock_snapshot or not self._stock_snapshot.status.available:
            return
        candidates = sorted(
            (asset for asset in self._stock_snapshot.assets if asset.price < self._limits_for_asset(asset)[0]),
            key=lambda asset: asset.price,
        )
        if not candidates:
            self.stock_candidates_label.setText("0 oportunidades")
            return
        self.stock_candidates_label.setText(f"{len(candidates)} oportunidades")

    def _display_stock_trade_result(self, value: object):
        if not isinstance(value, StockTradeResult):
            self._show_stock_feedback(False, "Resposta inesperada da ordem.")
            logger.error("Stock Market: worker retornou resultado de ordem inválido")
            return
        action = "Compra" if value.side == "buy" else "Venda"
        requested = "máximo" if value.is_maximum_order else str(value.requested_quantity)
        details = f"{action}: {value.message}. Executada: {value.executed_quantity}/{requested}."
        self._show_stock_feedback(value.success, details)
        self._refresh_after_order = True

    def _show_stock_unavailable(self, message: str):
        self._stock_available = False
        self.stock_limits_button.setEnabled(False)
        self.stock_status_label.setText("Mercado: indisponível")
        self.stock_status_label.setToolTip(message)
        self.stock_status_label.setStyleSheet("color: #f07883; font-weight: 600;")
        self.stock_candidates_label.setText("")
        self.stock_table.setRowCount(0)
        self._show_stock_feedback(False, message)
        self._update_stock_actions()

    def _show_stock_feedback(self, success: bool, message: str):
        self.stock_feedback_label.setText(message)
        self.stock_feedback_label.setStyleSheet(f"color: {'#65d6a5' if success else '#f07883'};")
        self.status_bar.showMessage(message, 7000)

    def _set_stock_busy(self, busy: bool):
        self.stock_quantity_input.setEnabled(not busy and not self.stock_use_max_checkbox.isChecked())
        self.stock_use_max_checkbox.setEnabled(not busy and self._stock_available)
        self._update_stock_actions(busy)
        if busy:
            self.stock_feedback_label.setText("Consultando o runtime do jogo...")
            self.stock_feedback_label.setStyleSheet("color: #9aa7ba;")

    def _update_stock_actions(self, busy: Optional[bool] = None):
        if busy is None:
            busy = bool(self._stock_worker and self._stock_worker.isRunning())
        has_selection = bool(self.stock_table.selectionModel().selectedRows())
        enabled = self._stock_available and has_selection and not busy
        self.stock_buy_button.setEnabled(enabled)
        self.stock_sell_button.setEnabled(enabled)
        self.stock_use_max_checkbox.setEnabled(self._stock_available and not busy)
        if not has_selection:
            self.stock_selected_asset_label.setText("Selecione um ativo")
        else:
            self.stock_selected_asset_label.setText(f"Selecionado: {self.stock_table.item(self.stock_table.selectionModel().selectedRows()[0].row(), 0).text()}")

    def _toggle_stock_maximum(self, state: int):
        self.stock_quantity_input.setEnabled(not bool(state) and not (self._stock_worker and self._stock_worker.isRunning()))

    @staticmethod
    def _format_number(value: Optional[float]) -> str:
        if value is None:
            return "—"
        return f"{value:,.2f}" if abs(value) < 1e12 else f"{value:.3e}"

    @staticmethod
    def _format_percent(multiplier: Optional[float]) -> str:
        if multiplier is None:
            return "—"
        return f"{max(0.0, multiplier - 1.0) * 100:.2f}%"

    @staticmethod
    def _format_variation(value: Optional[float]) -> str:
        if value is None:
            return "—"
        return f"{value:+.2f}%"

    def _save(self, field, state): setattr(automation_config, field, bool(state)); save_automation_settings()
    def toggle_golden_detection(self, state): self._save("enable_golden_cookie", state)
    def toggle_fortune_detection(self, state): self._save("enable_fortune_cookie", state)
    def toggle_reindeer_detection(self, state): self._save("enable_reindeer", state)
    def toggle_wrinkler_detection(self, state): self._save("enable_wrinkler_popper", state); self.wrinkler_delay_input.setEnabled(bool(state))
    def toggle_grimoire_spell_spam(self, state):
        self._save("enable_grimoire_spell_spam", state)
        self.grimoire_spell_combo.setEnabled(bool(state))
        logger.info(f"Grimoire: spam de skill {'ativado' if state else 'desativado'}")
    def update_grimoire_spell(self, _index):
        spell_id = self.grimoire_spell_combo.currentData()
        if isinstance(spell_id, int):
            automation_config.grimoire_spell_id = spell_id
            save_automation_settings()
            logger.info(f"Grimoire: skill selecionada — {self.grimoire_spell_combo.currentText()}")
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
    def update_log_limit(self, value):
        app_config.max_log_lines = max(1, int(value)); save_app_settings(); self._trim_logs()

    def toggle_clicker(self):
        if not self.runner: logger.warning("Runner não está disponível"); return
        self.runner.toggle_clicker(); self.set_clicker_state(self.runner.is_running)
    def set_clicker_state(self, active):
        self.clicker_button.setText("PARAR CLICKER" if active else "INICIAR CLICKER"); self.clicker_button.setObjectName("dangerButton" if active else "primaryButton"); self.clicker_button.style().unpolish(self.clicker_button); self.clicker_button.style().polish(self.clicker_button)
        self.clicker_status.setText("Clicker: Ativo" if active else "Clicker: Parado"); self.clicker_status.setStyleSheet(f"color: {'#65d6a5' if active else '#9aa7ba'}; font-weight: 600;")
    def update_bridge_status(self, connected):
        self.bridge_status.setText("Bridge: Conectado" if connected else "Bridge: Desconectado"); self.bridge_status.setStyleSheet(f"color: {'#65d6a5' if connected else '#f07883'}; font-weight: 600;")
    def add_log(self, message):
        self.log_text.append(message); self._trim_logs()
        cursor = self.log_text.textCursor(); cursor.movePosition(cursor.End); self.log_text.setTextCursor(cursor)

    def _trim_logs(self):
        """Remove as linhas mais antigas para manter o histórico sob controle."""
        document = self.log_text.document()
        while document.blockCount() > app_config.max_log_lines:
            cursor = QTextCursor(document); cursor.movePosition(QTextCursor.Start)
            cursor.select(QTextCursor.BlockUnderCursor); cursor.removeSelectedText()
            if not cursor.atEnd():
                cursor.deleteChar()
    def refresh_stats(self):
        elapsed = int(time.monotonic() - self._session_started_at)
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.session_timer_label.setText(f"Sessão: {hours:02}:{minutes:02}:{seconds:02}")
        if not self.runner: return
        self.cookies_clicked_label.setText(f"Cliques: {self.runner.cookies_clicked}"); self.golden_clicked_label.setText(f"Golden: {self.runner.golden_cookies_clicked}"); self.reindeer_popped_label.setText(f"Renas: {self.runner.reindeer_popped}"); self.wrinklers_popped_label.setText(f"Wrinklers: {self.runner.wrinklers_popped}")
    def open_backup_dialog(self):
        if self.backup_dialog is None:
            self.backup_dialog = BackupDialog(self.backup_manager, self); self.backup_dialog.backup_restored.connect(self.on_backup_restored)
        self.backup_dialog.show(); self.backup_dialog.raise_(); self.backup_dialog.activateWindow()
    def on_backup_restored(self, save_data):
        if self.runner and self.runner.bridge and self.runner.bridge.load_game_save(save_data): logger.info("Save restaurado com sucesso via backup"); self.add_log("Save restaurado com sucesso!")
        else: logger.warning("Bridge não disponível ou falhou ao restaurar save"); self.add_log("ERRO: Falha ao restaurar save")

    def closeEvent(self, event):
        """Evita destruir uma thread de consulta ainda em execução."""
        if self._auto_ascension_worker and self._auto_ascension_worker.isRunning():
            self._auto_ascension_worker.stop()
            self._auto_ascension_worker.wait((app_config.connection_timeout + 1) * 1000)
        if self._stock_worker and self._stock_worker.isRunning():
            self._stock_worker.wait((app_config.connection_timeout + 1) * 1000)
        if self._garden_worker and self._garden_worker.isRunning():
            self._garden_worker.wait((app_config.connection_timeout + 1) * 1000)
        super().closeEvent(event)


def create_ui_app(bridge: Optional[CookieClickerBridge] = None):
    set_windows_app_id()
    app = QApplication(sys.argv); app.setStyleSheet(DARK_STYLESHEET); enable_dark_title_bars(app)
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    window = MainWindow(bridge); window.setWindowIcon(app.windowIcon())
    return app, window
