"""Interface gráfica principal do Cookie Clicker Bot."""
import sys
import time
import ctypes
import threading
from pathlib import Path
from typing import Callable, Optional

from PyQt5.QtCore import QThread, QTimer, pyqtSignal, QObject, Qt
from PyQt5.QtGui import QColor, QIcon, QTextCursor
from PyQt5.QtWidgets import (QDoubleSpinBox, QSpinBox, QAbstractItemView, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QComboBox, QTextEdit, QLabel, QGroupBox, QStatusBar, QGridLayout, QFormLayout, QTabWidget, QHeaderView, QTableWidget, QTableWidgetItem, QScrollArea, QMessageBox)

from app.bridge.js_bridge import CookieClickerBridge, DEFAULT_GRIMOIRE_SPELLS
from app.config.settings import app_config, automation_config, save_app_settings, save_automation_settings
from app.core.backup_manager import BackupManager
from app.core.auto_ascensao import AutoAscensao, ConfiguracaoAutoAscensao
from app.core.combo import ComboAutomation
from app.core.simple_farm import SimpleFarmAutomation
from app.core.fazendeira import Fazendeira
from app.core.stock_market import StockMarketAutomation
from app.core.stock_policy import GASEOUS_ASSETS_TARGET, asset_limits
from app.models.stock_market import StockMarketAutomationResult, StockMarketSnapshot, StockTradeResult
from app.models.garden import GardenCycleResult
from app.models.auto_ascensao import RelatorioAutoAscensao
from app.models.combo import ConfiguracaoCombo, EstadoCombo, RelatorioCombo
from app.models.simple_farm import ConfiguracaoSimpleFarm, RelatorioSimpleFarm
from app.ui.backup_dialog import BackupDialog
from app.ui.automation_control import AutomationControl
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


class ComboWorker(QThread):
    """Mantém o looper de combo fora do event loop do Qt."""

    updated = pyqtSignal(object)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, automation, preview: bool, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.automation = automation
        self.preview = preview

    def run(self) -> None:
        try:
            report = (
                self.automation.gerar_previa()
                if self.preview else self.automation.executar(self.updated.emit)
            )
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
        self._stock_stop = threading.Event()
        self._stock_stop.set()
        self._stock_available = False
        self._refresh_after_order = False
        self._stock_snapshot: Optional[StockMarketSnapshot] = None
        self._garden_worker: Optional[StockMarketWorker] = None
        self._garden_stop = threading.Event()
        self._garden_stop.set()
        self._garden_available = False
        self._garden_run_when_idle = False
        self._auto_ascension_worker: Optional[AutoAscensaoWorker] = None
        self._auto_ascension: Optional[AutoAscensao] = None
        self._combo_worker: Optional[ComboWorker] = None
        self._combo_automation: Optional[ComboAutomation] = None
        self._simple_farm_automation: Optional[SimpleFarmAutomation] = None
        self._combo_exclusive = False
        self._combo_keep_awake = False
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
        self.tabs.addTab(self._combo_tab(), "Combo")
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
        """Cria a visão de progresso, planejamento e execução do Garden."""
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
        self.garden_toggle = AutomationControl("Garden")
        self.garden_toggle.setToolTip("Ligar inicia o Garden. Desligar encerra após a ação em andamento. A prévia não executa ações.")
        self.garden_toggle.requested.connect(self._toggle_garden_automation)
        self.garden_thumbcorn_checkbox = QCheckBox("Green, aching thumb")
        self.garden_thumbcorn_checkbox.setToolTip(
            "Prioriza Thumbcorn até obter a conquista de colher 1.000 plantas maduras. "
            "Use Ligar para executar esta estratégia; desligada, ela aparece apenas na prévia."
        )
        self.garden_thumbcorn_checkbox.setChecked(automation_config.enable_green_aching_thumb)
        self.garden_thumbcorn_checkbox.stateChanged.connect(self._toggle_green_aching_thumb)
        toolbar.addWidget(self.garden_status_label)
        toolbar.addWidget(self.garden_progress_label)
        toolbar.addStretch()
        toolbar.addWidget(self.garden_toggle)
        layout.addLayout(toolbar)
        actions = QHBoxLayout()
        actions.addWidget(self.garden_refresh_button)
        actions.addWidget(self.garden_simulate_button)
        actions.addWidget(self.garden_thumbcorn_checkbox)
        actions.addStretch()
        layout.addLayout(actions)

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

    def _combo_tab(self):
        """Cria o painel do planejador e executor autônomo de combo."""
        tab = QWidget()
        outer_layout = QVBoxLayout(tab)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        warning = QLabel(
            "Ao iniciar, o modo Combo pausa as demais automações, recalcula a seed continuamente "
            "e pode vender/recomprar prédios e gastar Sugar Lumps. Ele para em estado seguro se "
            "qualquer precondição mudar."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #e8b766; font-weight: 600;")
        layout.addWidget(warning)

        config_group = QGroupBox("Planejamento on-the-go")
        form = QFormLayout(config_group)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.combo_search_input = QSpinBox()
        self.combo_search_input.setRange(4, 100_000)
        self.combo_search_input.setValue(automation_config.combo_max_search_ahead)
        self.combo_search_input.setSuffix(" spells")
        self.combo_search_input.valueChanged.connect(self._save_combo_settings)
        form.addRow("Alcance do forecast", self.combo_search_input)

        self.combo_lumps_input = QSpinBox()
        self.combo_lumps_input.setRange(0, 10_000)
        self.combo_lumps_input.setValue(automation_config.combo_max_skip_lumps)
        self.combo_lumps_input.setSuffix(" lumps")
        self.combo_lumps_input.valueChanged.connect(self._save_combo_settings)
        form.addRow("Orçamento para alinhamento", self.combo_lumps_input)

        self.combo_bs_input = QSpinBox()
        self.combo_bs_input.setRange(1, 6)
        self.combo_bs_input.setValue(automation_config.combo_required_building_specials)
        self.combo_bs_input.valueChanged.connect(self._save_combo_settings)
        form.addRow("Building Specials totais", self.combo_bs_input)

        self.combo_interval_input = QDoubleSpinBox()
        self.combo_interval_input.setRange(0.1, 60.0)
        self.combo_interval_input.setDecimals(1)
        self.combo_interval_input.setValue(automation_config.combo_poll_interval_seconds)
        self.combo_interval_input.setSuffix(" s")
        self.combo_interval_input.valueChanged.connect(self._save_combo_settings)
        form.addRow("Intervalo do looper", self.combo_interval_input)

        self.combo_min_buff_input = QDoubleSpinBox()
        self.combo_min_buff_input.setRange(5.0, 120.0)
        self.combo_min_buff_input.setDecimals(1)
        self.combo_min_buff_input.setValue(automation_config.combo_minimum_buff_seconds)
        self.combo_min_buff_input.setSuffix(" s")
        self.combo_min_buff_input.valueChanged.connect(self._save_combo_settings)
        form.addRow("Duração mínima dos buffs", self.combo_min_buff_input)

        self.combo_wait_input = QSpinBox()
        self.combo_wait_input.setRange(1, 1440)
        self.combo_wait_input.setValue(automation_config.combo_max_wait_minutes)
        self.combo_wait_input.setSuffix(" min")
        self.combo_wait_input.setToolTip(
            "Inclui preparação e busca. Ao vencer o prazo, para sem disparar o Quadcast."
        )
        self.combo_wait_input.valueChanged.connect(self._save_combo_settings)
        form.addRow("Limite de espera", self.combo_wait_input)

        # Em algumas escalas de DPI do Windows, o sizeHint nativo dos spinboxes
        # ignora o padding do tema e recorta todo o texto do valor.
        for field in (
            self.combo_search_input,
            self.combo_lumps_input,
            self.combo_bs_input,
            self.combo_interval_input,
            self.combo_min_buff_input,
            self.combo_wait_input,
        ):
            field.setMinimumHeight(32)

        boosts = QHBoxLayout()
        self.combo_sugar_checkbox = QCheckBox("Usar Sugar Frenzy na tentativa final")
        self.combo_sugar_checkbox.setChecked(automation_config.combo_use_sugar_frenzy)
        self.combo_sugar_checkbox.stateChanged.connect(self._save_combo_settings)
        self.combo_loans_checkbox = QCheckBox("Usar os três loans")
        self.combo_loans_checkbox.setChecked(automation_config.combo_use_loans)
        self.combo_loans_checkbox.stateChanged.connect(self._save_combo_settings)
        boosts.addWidget(self.combo_sugar_checkbox)
        boosts.addWidget(self.combo_loans_checkbox)
        boosts.addStretch()
        form.addRow("Multiplicadores finais", boosts)
        self.combo_pause_checkbox = QCheckBox("Pausar quando faltarem 3 skips e aguardar Retomar")
        self.combo_pause_checkbox.setChecked(automation_config.combo_pause_before_last_skips)
        self.combo_pause_checkbox.setToolTip(
            "Pausa uma vez por execução, antes dos últimos 3 skips (ou menos). "
            "Enquanto aguarda, nenhuma ação no jogo é executada pelo bot."
        )
        self.combo_pause_checkbox.stateChanged.connect(self._save_combo_settings)
        form.addRow("Acompanhar tentativa", self.combo_pause_checkbox)
        layout.addWidget(config_group)

        status_group = QGroupBox("Acompanhamento")
        status_form = QFormLayout(status_group)
        self.combo_state_label = QLabel("Não iniciado")
        self.combo_plan_label = QLabel("Atualize a prévia para ler a seed atual.")
        self.combo_progress_label = QLabel("Spells: — | Mana: — | Lumps: —")
        self.combo_buffs_label = QLabel("Buffs: —")
        self.combo_garden_label = QLabel("Garden: —")
        self.combo_message_label = QLabel("Nenhuma ação executada.")
        self.combo_error_label = QLabel("—")
        for label in (
            self.combo_plan_label, self.combo_buffs_label, self.combo_message_label,
            self.combo_error_label,
        ):
            label.setWordWrap(True)
        status_form.addRow("Estado", self.combo_state_label)
        status_form.addRow("Plano vivo", self.combo_plan_label)
        status_form.addRow("Recursos", self.combo_progress_label)
        status_form.addRow("Buffs", self.combo_buffs_label)
        status_form.addRow("Garden", self.combo_garden_label)
        status_form.addRow("Última atualização", self.combo_message_label)
        status_form.addRow("Bloqueio/erro", self.combo_error_label)
        layout.addWidget(status_group, 1)

        controls = QHBoxLayout()
        self.combo_toggle = AutomationControl("Combo Endgame")
        self.combo_toggle.requested.connect(lambda enabled: self.start_combo() if enabled else self.stop_combo())
        self.combo_preview_button = QPushButton("Atualizar prévia")
        self.combo_preview_button.clicked.connect(self.refresh_combo_preview)
        self.combo_resume_button = QPushButton("Retomar combo")
        self.combo_resume_button.setEnabled(False)
        self.combo_resume_button.clicked.connect(self.resume_combo)
        controls.addStretch()
        controls.addWidget(self.combo_preview_button)
        controls.addWidget(self.combo_toggle)
        controls.addWidget(self.combo_resume_button)
        layout.addLayout(controls)
        scroll.setWidget(content)
        self.combo_scroll_area = scroll
        self.combo_mode_tabs = QTabWidget()
        self.combo_mode_tabs.addTab(self._simple_farm_panel(), "Simple Farm")
        self.combo_mode_tabs.addTab(scroll, "Endgame 1e72")
        outer_layout.addWidget(self.combo_mode_tabs)
        return tab

    def _simple_farm_panel(self):
        """Cria o farm paralelo com compras econômicas e magias oportunistas."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        guarantee = QLabel(
            "Farm de apoio: Garden e Banco continuam ativos. Preserva a maior parte do caixa, "
            "prioriza upgrades de produção em % e compra construções por retorno de CpS. "
            "Usa Dual Cast quando a recompra das torres cabe no orçamento, sem gastar Sugar Lumps, usar loans "
            "ou alterar Garden e Pantheon. Passe o mouse nas opções para ver a explicação."
        )
        guarantee.setWordWrap(True)
        guarantee.setStyleSheet("color: #65d6a5; font-weight: 600;")
        layout.addWidget(guarantee)

        config_group = QGroupBox("Estratégia automática")
        form = QFormLayout(config_group)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.simple_farm_search_input = QSpinBox()
        self.simple_farm_search_input.setRange(2, 10_000)
        self.simple_farm_search_input.setValue(automation_config.simple_farm_max_search_ahead)
        self.simple_farm_search_input.setSuffix(" spells")
        self.simple_farm_search_input.valueChanged.connect(self._save_simple_farm_settings)
        form.addRow("Magias futuras analisadas", self.simple_farm_search_input)
        self.simple_farm_interval_input = QDoubleSpinBox()
        self.simple_farm_interval_input.setRange(0.1, 10.0)
        self.simple_farm_interval_input.setDecimals(1)
        self.simple_farm_interval_input.setSingleStep(0.1)
        self.simple_farm_interval_input.setValue(automation_config.simple_farm_poll_interval_seconds)
        self.simple_farm_interval_input.setSuffix(" s")
        self.simple_farm_interval_input.valueChanged.connect(self._save_simple_farm_settings)
        form.addRow("Intervalo de verificação", self.simple_farm_interval_input)
        self.simple_farm_min_buff_input = QDoubleSpinBox()
        self.simple_farm_min_buff_input.setRange(3.0, 60.0)
        self.simple_farm_min_buff_input.setDecimals(1)
        self.simple_farm_min_buff_input.setValue(automation_config.simple_farm_minimum_buff_seconds)
        self.simple_farm_min_buff_input.setSuffix(" s")
        self.simple_farm_min_buff_input.valueChanged.connect(self._save_simple_farm_settings)
        form.addRow("Tempo mínimo restante do buff", self.simple_farm_min_buff_input)
        self.simple_farm_reserve_input = QDoubleSpinBox()
        self.simple_farm_reserve_input.setRange(15.0, 99.0)
        self.simple_farm_reserve_input.setDecimals(0)
        self.simple_farm_reserve_input.setValue(automation_config.simple_farm_cash_reserve_percent)
        self.simple_farm_reserve_input.setSuffix(" %")
        self.simple_farm_reserve_input.valueChanged.connect(self._save_simple_farm_settings)
        form.addRow("Reserva mínima de caixa", self.simple_farm_reserve_input)
        self.simple_farm_investment_input = QDoubleSpinBox()
        self.simple_farm_investment_input.setRange(1.0, 20.0)
        self.simple_farm_investment_input.setDecimals(0)
        self.simple_farm_investment_input.setValue(automation_config.simple_farm_investment_percent)
        self.simple_farm_investment_input.setSuffix(" %")
        self.simple_farm_investment_input.valueChanged.connect(self._save_simple_farm_settings)
        form.addRow("Compra máxima a cada 15 s", self.simple_farm_investment_input)
        tips = {
            self.simple_farm_search_input: "Quantas magias futuras prever sem gastar recursos. Prioriza Click Frenzy junto de outro multiplicador e só usa Click Frenzy isolado quando não encontra um par viável. Dual Cast vende só as torres necessárias e recompra todas antes de abrir os cookies; não repete Click Frenzy. Para avançar até o par, usa Haggler's Charm só com mana cheia e fora dos buffs. Sem previsão, o farm segue coletando e comprando.",
            self.simple_farm_interval_input: "Frequência de leitura do jogo, em segundos. 0,2 s reage rápido aos Golden Cookies. Compras têm intervalo separado de 15 s; esta opção não aumenta o orçamento.",
            self.simple_farm_min_buff_input: "Tempo que um multiplicador de produção natural ainda precisa durar para receber um Click Frenzy de magia. Não lança outro se Click Frenzy ou Dragonflight já estiver ativo.",
            self.simple_farm_reserve_input: "Parte do maior saldo observado nesta execução que o Simple Farm não gasta (padrão: 80%; mínimo: 15%). Garden e Banco podem usar essa reserva. Se gastarem, o farm espera o caixa se recuperar. Também preserva 6.000 vezes o CpS para Lucky. O valor escolhido é salvo automaticamente.",
            self.simple_farm_investment_input: "Limite de gasto a cada 15 segundos para upgrades e construções (padrão: 5% do saldo atual), sempre abaixo do excedente da reserva. Até metade vai para um upgrade; o restante pode comprar até 25 construções. Não é uma meta de gasto; durante buffs, compras de produção aguardam. A recompra de torres do Dual Cast tem regra própria: pode usar o excedente inteiro, mas precisa manter toda a reserva de caixa e o valor de Lucky.",
        }
        for field, tip in tips.items():
            field.setToolTip(tip)
            form.labelForField(field).setToolTip(tip)
        for field in (
            self.simple_farm_search_input,
            self.simple_farm_interval_input,
            self.simple_farm_min_buff_input,
            self.simple_farm_reserve_input,
            self.simple_farm_investment_input,
        ):
            field.setMinimumHeight(32)
        layout.addWidget(config_group)

        status_group = QGroupBox("Acompanhamento")
        status_form = QFormLayout(status_group)
        self.simple_farm_state_label = QLabel("Não iniciado")
        self.simple_farm_plan_label = QLabel("Atualize a prévia para ler a seed atual.")
        self.simple_farm_resources_label = QLabel("Spells: — | Mana: — | Cookies: —")
        self.simple_farm_buffs_label = QLabel("Buffs: —")
        self.simple_farm_counter_label = QLabel("GC naturais: 0 | Magias: 0")
        self.simple_farm_pantheon_label = QLabel("Pantheon: será apenas lido")
        self.simple_farm_message_label = QLabel("Nenhuma ação executada.")
        self.simple_farm_error_label = QLabel("—")
        for label in (
            self.simple_farm_plan_label,
            self.simple_farm_buffs_label,
            self.simple_farm_message_label,
            self.simple_farm_error_label,
        ):
            label.setWordWrap(True)
        status_form.addRow("Estado", self.simple_farm_state_label)
        status_form.addRow("Próxima oportunidade", self.simple_farm_plan_label)
        status_form.addRow("Recursos", self.simple_farm_resources_label)
        status_form.addRow("Buffs", self.simple_farm_buffs_label)
        status_form.addRow("Contadores", self.simple_farm_counter_label)
        status_form.addRow("Pantheon", self.simple_farm_pantheon_label)
        status_form.addRow("Última atualização", self.simple_farm_message_label)
        status_form.addRow("Bloqueio/erro", self.simple_farm_error_label)
        layout.addWidget(status_group, 1)

        controls = QHBoxLayout()
        self.simple_farm_toggle = AutomationControl("Simple Farm")
        self.simple_farm_toggle.requested.connect(lambda enabled: self.start_simple_farm() if enabled else self.stop_simple_farm())
        self.simple_farm_preview_button = QPushButton("Atualizar prévia")
        self.simple_farm_preview_button.clicked.connect(self.refresh_simple_farm_preview)
        controls.addStretch()
        controls.addWidget(self.simple_farm_preview_button)
        controls.addWidget(self.simple_farm_toggle)
        layout.addLayout(controls)
        scroll.setWidget(content)
        self.simple_farm_scroll_area = scroll
        return scroll

    def _save_combo_settings(self, _value=None):
        automation_config.combo_max_search_ahead = self.combo_search_input.value()
        automation_config.combo_max_skip_lumps = self.combo_lumps_input.value()
        automation_config.combo_required_building_specials = self.combo_bs_input.value()
        automation_config.combo_poll_interval_seconds = self.combo_interval_input.value()
        automation_config.combo_minimum_buff_seconds = self.combo_min_buff_input.value()
        automation_config.combo_max_wait_minutes = self.combo_wait_input.value()
        automation_config.combo_use_sugar_frenzy = self.combo_sugar_checkbox.isChecked()
        automation_config.combo_use_loans = self.combo_loans_checkbox.isChecked()
        automation_config.combo_pause_before_last_skips = self.combo_pause_checkbox.isChecked()
        save_automation_settings()

    def _save_simple_farm_settings(self, _value=None):
        automation_config.simple_farm_max_search_ahead = self.simple_farm_search_input.value()
        automation_config.simple_farm_poll_interval_seconds = self.simple_farm_interval_input.value()
        automation_config.simple_farm_minimum_buff_seconds = self.simple_farm_min_buff_input.value()
        automation_config.simple_farm_cash_reserve_percent = self.simple_farm_reserve_input.value()
        automation_config.simple_farm_investment_percent = self.simple_farm_investment_input.value()
        save_automation_settings()

    def _simple_farm_configuration(self) -> ConfiguracaoSimpleFarm:
        self._save_simple_farm_settings()
        return ConfiguracaoSimpleFarm(
            busca_maxima_spells=self.simple_farm_search_input.value(),
            intervalo_verificacao=self.simple_farm_interval_input.value(),
            duracao_minima_buff=self.simple_farm_min_buff_input.value(),
            reserva_caixa=self.simple_farm_reserve_input.value() / 100.0,
            investimento_por_ciclo=self.simple_farm_investment_input.value() / 100.0,
        )

    def refresh_simple_farm_preview(self, _checked: bool = False):
        if not self.bridge:
            self._simple_farm_failed("Bridge não está disponível.")
            return
        if self._combo_worker and self._combo_worker.isRunning():
            return
        automation = SimpleFarmAutomation(self.bridge, self._simple_farm_configuration())
        self._run_simple_farm_worker(automation, preview=True)

    def start_simple_farm(self, _checked: bool = False):
        if not self.bridge or not self.runner:
            self._simple_farm_failed("Bridge ou runner não está disponível.")
            return
        if self._combo_worker and self._combo_worker.isRunning():
            return
        if self._auto_ascension_worker and self._auto_ascension_worker.isRunning():
            self._simple_farm_failed("Aguarde a Auto Ascensão terminar antes de iniciar o farm.")
            return
        if not self.runner.acquire_simple_farm():
            self._simple_farm_failed("Outra automação controla o Grimoire ou está em modo exclusivo.")
            return
        try:
            save_data = self.bridge.get_game_save()
            if not save_data:
                self._abort_simple_farm_start("Não foi possível exportar o save de segurança.")
                return
            backup = self.backup_manager.create_backup(save_data, "antes-do-simple-farm")
            self.add_log(f"Backup automático criado: {backup.display_name}")
        except Exception as error:
            self._abort_simple_farm_start(f"Falha ao criar backup automático: {error}")
            return
        automation = SimpleFarmAutomation(
            self.bridge,
            self._simple_farm_configuration(),
            habilitar_clicker=lambda: self.runner.set_simple_farm_clicker(True),
            desabilitar_clicker=lambda: self.runner.set_simple_farm_clicker(False),
        )
        self._set_combo_keep_awake(True)
        self._run_simple_farm_worker(automation, preview=False)

    def _abort_simple_farm_start(self, message: str):
        if self.runner:
            self.runner.release_simple_farm()
        self._set_combo_keep_awake(False)
        self._simple_farm_failed(message)

    def stop_simple_farm(self, _checked: bool = False):
        if self._combo_worker and self._combo_worker.isRunning():
            self.simple_farm_toggle.set_stopping()
            self._combo_worker.stop()
            self.simple_farm_message_label.setText(
                "Parada solicitada; aguardando a ação atômica atual terminar."
            )

    def _run_simple_farm_worker(self, automation: SimpleFarmAutomation, preview: bool):
        self._simple_farm_automation = automation
        worker = ComboWorker(automation, preview, self)
        self._combo_worker = worker
        worker.updated.connect(self._display_simple_farm_report)
        worker.completed.connect(self._display_simple_farm_report)
        worker.failed.connect(self._simple_farm_failed)
        worker.finished.connect(lambda: self._simple_farm_finished(preview))
        self._set_simple_farm_busy(True, preview)
        worker.start()

    def _display_simple_farm_report(self, value: object):
        if not isinstance(value, RelatorioSimpleFarm):
            return
        self.simple_farm_state_label.setText(value.estado.value)
        opportunity = value.plano.resumo if value.plano else "—"
        if value.plano and value.plano.decisao:
            opportunity += f" — {value.plano.decisao}"
        self.simple_farm_plan_label.setText(opportunity)
        self.simple_farm_plan_label.setToolTip(value.plano.decisao if value.plano else "")
        mana = "—" if value.mana is None else f"{value.mana:.1f}/{value.mana_maxima:.1f}"
        self.simple_farm_resources_label.setText(
            f"Spells: {value.cast_atual if value.cast_atual is not None else '—'} | "
            f"Mana: {mana} | Banco: {self._format_number(value.cookies_no_banco)} | "
            f"Caixa protegido: {self._format_number(value.caixa_reservado)}"
        )
        self.simple_farm_buffs_label.setText(
            ", ".join(value.buffs_ativos) if value.buffs_ativos else "nenhum"
        )
        self.simple_farm_counter_label.setText(
            f"GC naturais: {value.golden_cookies_coletados} | Magias: {value.magias_executadas} | "
            f"Upgrades: {value.upgrades_comprados} | Construções: {value.construcoes_compradas}"
        )
        slots = value.pantheon_slots
        pantheon = "Godzamok / Mokalsium / Muridal" if slots == (2, 8, 6) else str(slots or "—")
        self.simple_farm_pantheon_label.setText(f"{pantheon} (somente leitura)")
        self.simple_farm_message_label.setText(
            value.mensagem + (f" Próximo: {value.proximo_passo}" if value.proximo_passo else "")
        )
        self.simple_farm_error_label.setText(value.erro or "—")
        self.simple_farm_error_label.setStyleSheet(
            f"color: {'#f07883' if value.erro else '#9aa7ba'};"
        )

    def _simple_farm_failed(self, message: str):
        self.simple_farm_state_label.setText("erro seguro")
        self.simple_farm_error_label.setText(message)
        self.simple_farm_error_label.setStyleSheet("color: #f07883;")
        logger.error("Simple Farm: %s", message)

    def _simple_farm_finished(self, preview: bool):
        worker = self._combo_worker
        self._set_simple_farm_busy(False, preview)
        if not preview and self.runner:
            self.runner.release_simple_farm()
        if not preview:
            self._set_combo_keep_awake(False)
        self._combo_worker = None
        self._simple_farm_automation = None
        if worker is not None:
            worker.deleteLater()

    def _set_simple_farm_busy(self, busy: bool, preview: bool):
        for widget in (
            self.simple_farm_search_input, self.simple_farm_interval_input,
            self.simple_farm_min_buff_input, self.simple_farm_reserve_input,
            self.simple_farm_investment_input,
            self.simple_farm_preview_button, self.simple_farm_toggle,
            self.combo_preview_button, self.combo_toggle,
        ):
            widget.setEnabled(not busy)
        self.simple_farm_toggle.set_running(busy and not preview)
        self.simple_farm_toggle.setEnabled(not (busy and preview))
        if not preview:
            # A ascensão é incompatível com um farm paralelo.
            self.auto_ascension_toggle.setEnabled(not busy)

    def _combo_configuration(self) -> ConfiguracaoCombo:
        self._save_combo_settings()
        return ConfiguracaoCombo(
            alvo_cookies=automation_config.combo_target_cookies,
            busca_maxima_spells=self.combo_search_input.value(),
            maximo_lumps_alinhamento=self.combo_lumps_input.value(),
            building_specials_totais=self.combo_bs_input.value(),
            intervalo_verificacao=self.combo_interval_input.value(),
            duracao_minima_buff=self.combo_min_buff_input.value(),
            tempo_maximo_espera=self.combo_wait_input.value() * 60,
            usar_sugar_frenzy=self.combo_sugar_checkbox.isChecked(),
            usar_loans=self.combo_loans_checkbox.isChecked(),
            pausar_antes_ultimos_skips=self.combo_pause_checkbox.isChecked(),
        )

    def refresh_combo_preview(self, _checked: bool = False):
        if not self.bridge:
            self._combo_failed("Bridge não está disponível.")
            return
        if self._combo_worker and self._combo_worker.isRunning():
            return
        automation = ComboAutomation(self.bridge, self._combo_configuration())
        self._run_combo_worker(automation, preview=True)

    def start_combo(self, _checked: bool = False):
        if not self.bridge or not self.runner:
            self._combo_failed("Bridge ou runner não está disponível.")
            return
        if self._combo_worker and self._combo_worker.isRunning():
            return
        answer = QMessageBox.question(
            self,
            "Iniciar modo Combo",
            "O modo Combo pausará as outras automações e poderá gastar até "
            f"{self.combo_lumps_input.value()} lumps no alinhamento, mais o Quadcast/Sugar Frenzy. "
            "Também venderá e recomprará prédios. Continuar?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        if self._auto_ascension_worker and self._auto_ascension_worker.isRunning():
            self._auto_ascension_worker.stop()
            self._auto_ascension_worker.wait((app_config.connection_timeout + 1) * 1000)
            if self._auto_ascension_worker.isRunning():
                self._combo_failed("Auto Ascensão não parou a tempo.")
                return
        if not self.runner.acquire_exclusive("combo"):
            self._combo_failed(
                f"Outra automação exclusiva está ativa: {self.runner.exclusive_owner or 'desconhecida'}."
            )
            return
        self._combo_exclusive = True
        self.stock_refresh_timer.stop()
        self.garden_refresh_timer.stop()
        timeout_ms = (app_config.connection_timeout + 1) * 1000
        for name, worker in (("Stock Market", self._stock_worker), ("Garden", self._garden_worker)):
            if worker and worker.isRunning():
                worker.wait(timeout_ms)
                if worker.isRunning():
                    self._abort_combo_start(f"{name} não encerrou a operação em andamento a tempo.")
                    return
        try:
            save_data = self.bridge.get_game_save()
            if not save_data:
                self._abort_combo_start("Não foi possível exportar o save de segurança.")
                return
            backup = self.backup_manager.create_backup(save_data, "antes-do-combo")
            self.add_log(f"Backup automático criado: {backup.display_name}")
        except Exception as error:
            self._abort_combo_start(f"Falha ao criar backup automático: {error}")
            return
        automation = ComboAutomation(
            self.bridge,
            self._combo_configuration(),
            habilitar_clicker=self.runner.ensure_clicker_running,
            desabilitar_clicker=self.runner.ensure_clicker_stopped,
        )
        self._set_combo_keep_awake(True)
        self._run_combo_worker(automation, preview=False)

    def _abort_combo_start(self, message: str):
        """Desfaz a exclusividade quando a preparação da thread não pode terminar."""
        if self._combo_exclusive and self.runner:
            self.runner.release_exclusive("combo")
        self._combo_exclusive = False
        self._set_combo_keep_awake(False)
        if self.bridge:
            self.stock_refresh_timer.start(5_000)
            QTimer.singleShot(0, self._on_stock_market_timer)
            QTimer.singleShot(0, self.refresh_garden)
        self._combo_failed(message)

    def _set_combo_keep_awake(self, enabled: bool):
        """Impede suspensão do Windows enquanto o modo noturno está ativo."""
        if sys.platform != "win32":
            self._combo_keep_awake = enabled
            return
        try:
            es_continuous = 0x80000000
            es_system_required = 0x00000001
            flags = es_continuous | es_system_required if enabled else es_continuous
            result = ctypes.windll.kernel32.SetThreadExecutionState(flags)
            if not result:
                raise OSError("SetThreadExecutionState retornou zero")
            self._combo_keep_awake = enabled
        except Exception as error:
            logger.warning("Combo: não foi possível alterar o modo de suspensão: %s", error)

    def stop_combo(self, _checked: bool = False):
        if self._combo_worker and self._combo_worker.isRunning():
            self.combo_toggle.set_stopping()
            self.combo_resume_button.setEnabled(False)
            self._combo_worker.stop()
            self.combo_message_label.setText("Parada solicitada; aguardando a ação atômica atual terminar.")

    def resume_combo(self, _checked: bool = False):
        if self._combo_automation and self._combo_worker and self._combo_worker.isRunning():
            self.combo_resume_button.setEnabled(False)
            self._combo_automation.retomar()
            self.combo_message_label.setText("Retomada solicitada; revalidando o jogo e o plano antes de continuar.")

    def _run_combo_worker(self, automation: ComboAutomation, preview: bool):
        self._combo_automation = automation
        worker = ComboWorker(automation, preview, self)
        self._combo_worker = worker
        worker.updated.connect(self._display_combo_report)
        worker.completed.connect(self._display_combo_report)
        worker.failed.connect(self._combo_failed)
        worker.finished.connect(lambda: self._combo_finished(preview))
        self._set_combo_busy(True, preview)
        worker.start()

    def _display_combo_report(self, value: object):
        if not isinstance(value, RelatorioCombo):
            return
        self.combo_state_label.setText(value.estado.value)
        self.combo_resume_button.setEnabled(
            value.estado == EstadoCombo.PAUSADO
            and self._combo_worker is not None
            and self._combo_worker.isRunning()
        )
        self.combo_plan_label.setText(value.plano.resumo if value.plano else "—")
        mana = "—" if value.mana is None else f"{value.mana:.1f}/{value.mana_maxima:.1f}"
        self.combo_progress_label.setText(
            f"Spells: {value.cast_atual if value.cast_atual is not None else '—'} | "
            f"Mana: {mana} | Lumps: {value.lumps if value.lumps is not None else '—'} "
            f"(gastos: {value.lumps_gastos}) | Cookies: {self._format_number(value.cookies_assados)}"
        )
        self.combo_buffs_label.setText(
            "Buffs: " + (", ".join(value.buffs_ativos) if value.buffs_ativos else "nenhum")
            + f" | BS: {value.building_specials_ativos}"
        )
        self.combo_garden_label.setText(
            f"Maduras na última leitura: {value.garden_maduras}/{value.garden_total} | Garden opcional para o combo"
            if value.garden_total else "Garden opcional: não bloqueia o disparo do combo."
        )
        self.combo_message_label.setText(
            value.mensagem + (f" Próximo: {value.proximo_passo}" if value.proximo_passo else "")
        )
        self.combo_error_label.setText(value.erro or "—")
        self.combo_error_label.setStyleSheet(
            f"color: {'#f07883' if value.erro else '#9aa7ba'};"
        )

    def _combo_failed(self, message: str):
        self.combo_resume_button.setEnabled(False)
        self.combo_state_label.setText("erro seguro")
        self.combo_error_label.setText(message)
        self.combo_error_label.setStyleSheet("color: #f07883;")
        logger.error("Combo: %s", message)

    def _combo_finished(self, preview: bool):
        worker = self._combo_worker
        self._set_combo_busy(False, preview)
        if not preview and self._combo_exclusive and self.runner:
            self.runner.release_exclusive("combo")
            self._combo_exclusive = False
            self.stock_refresh_timer.start(5_000)
            QTimer.singleShot(0, self._on_stock_market_timer)
            QTimer.singleShot(0, self.refresh_garden)
        if not preview:
            self._set_combo_keep_awake(False)
        self._combo_worker = None
        self._combo_automation = None
        if worker is not None:
            worker.deleteLater()

    def _set_combo_busy(self, busy: bool, preview: bool):
        for widget in (
            self.combo_search_input, self.combo_lumps_input, self.combo_bs_input,
            self.combo_interval_input, self.combo_min_buff_input, self.combo_wait_input,
            self.combo_sugar_checkbox, self.combo_loans_checkbox, self.combo_pause_checkbox,
            self.combo_preview_button, self.combo_toggle,
            self.simple_farm_search_input, self.simple_farm_interval_input,
            self.simple_farm_min_buff_input, self.simple_farm_reserve_input,
            self.simple_farm_investment_input,
            self.simple_farm_preview_button, self.simple_farm_toggle,
        ):
            widget.setEnabled(not busy)
        self.combo_toggle.set_running(busy and not preview)
        self.combo_toggle.setEnabled(not (busy and preview))
        if not preview:
            self.stock_toggle.set_paused(busy)
            self.garden_toggle.set_paused(busy)
        self.combo_resume_button.setEnabled(False)
        if not preview:
            for widget in (
                self.clicker_button, self.golden_checkbox, self.fortune_checkbox,
                self.reindeer_checkbox, self.wrinkler_checkbox,
                self.grimoire_spell_spam_checkbox, self.sugar_lump_checkbox,
                self.garden_thumbcorn_checkbox,
                self.auto_ascension_toggle,
            ):
                widget.setEnabled(not busy)

    def _auto_ascension_tab(self):
        """Cria os controles e o relatório da máquina de Auto Ascensão."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        warning = QLabel(
            "A ascensão altera permanentemente o save. A execução real só começa "
            "na tela de ascensão. Use Ligar para começar e Desligar para encerrar."
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
        self.auto_ascension_toggle = AutomationControl("Auto Ascensão")
        self.auto_ascension_toggle.requested.connect(lambda enabled: self.start_auto_ascension() if enabled else self.stop_auto_ascension())
        self.auto_ascension_preview_button = QPushButton("Atualizar prévia")
        self.auto_ascension_preview_button.clicked.connect(self.refresh_auto_ascension_preview)
        controls.addStretch()
        controls.addWidget(self.auto_ascension_preview_button)
        controls.addWidget(self.auto_ascension_toggle)
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
        """Liga a automação; a prévia tem um botão independente."""
        if self._combo_exclusive or self._simple_farm_automation is not None:
            self._auto_ascension_failed("Pare o farm/Combo antes de iniciar a Auto Ascensão.")
            return
        if not self.bridge:
            self._auto_ascension_failed("Bridge não está disponível.")
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
            self.auto_ascension_toggle.set_stopping()
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
            self.auto_ascension_preview_button,
            self.auto_ascension_toggle,
        ):
            control.setEnabled(not busy)
        self.auto_ascension_toggle.set_running(busy and not preview)
        self.auto_ascension_toggle.setEnabled(not (busy and preview))

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
        self.stock_toggle = AutomationControl("Stock Market")
        self.stock_toggle.setToolTip("Ligar negocia automaticamente. Desligar impede novas ordens; a leitura do mercado continua.")
        self.stock_toggle.requested.connect(self._toggle_stock_auto_trade)
        toolbar_layout.addWidget(self.stock_status_label)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.stock_toggle)
        self.stock_candidates_label = QLabel()
        self.stock_candidates_label.setStyleSheet("color: #e8b766;")
        layout.addWidget(toolbar)
        totals = QHBoxLayout()
        totals.addWidget(self.stock_total_profit_label)
        totals.addWidget(self.stock_goal_label)
        totals.addStretch()
        layout.addLayout(totals)

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
        if self._combo_exclusive:
            return
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
        if self._combo_exclusive:
            return
        if not self.bridge or (self._stock_worker and self._stock_worker.isRunning()):
            return
        if not self.stock_automation:
            self.refresh_stock_market(automatic=True)
            return
        buy_limit = float(self.stock_buy_limit_input.value())
        sell_limit = float(self.stock_sell_limit_input.value())
        trend_ticks = int(self.stock_trend_ticks_input.value())
        reversal_percent = float(self.stock_reversal_percent_input.value())
        stop_event = self._stock_stop
        execute_orders = self.stock_toggle.running and not stop_event.is_set()
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
                should_stop=stop_event.is_set,
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

    def _toggle_stock_auto_trade(self, enabled: bool):
        if enabled:
            if self._combo_exclusive or not self.bridge or not self.stock_automation:
                self._show_stock_feedback(False, "Não foi possível ligar: conecte a bridge e aguarde o Combo terminar.")
                return
            self._stock_stop = threading.Event()
            self.stock_toggle.set_running(True)
            QTimer.singleShot(0, self._on_stock_market_timer)
        else:
            self._stock_stop.set()
            if self._stock_worker and self._stock_worker.isRunning():
                self.stock_toggle.set_stopping()
            else:
                self.stock_toggle.set_running(False)
        logger.info("Stock Market: %s", "ligada" if enabled else "desligamento solicitado")
        self._show_stock_feedback(True, "Automação ligada." if enabled else "Novas ordens automáticas interrompidas.")

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
        if self._combo_exclusive:
            self._show_stock_feedback(False, "Modo Combo está ativo; ordens estão pausadas.")
            return
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
        if self.stock_toggle.running:
            self._toggle_stock_auto_trade(False)
        logger.error(f"Stock Market: falha inesperada no worker: {message}")
        self._show_stock_feedback(False, f"Falha inesperada: {message}")

    def _stock_task_finished(self):
        self._stock_worker = None
        if self.stock_toggle.stopping:
            self.stock_toggle.set_running(False)
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
        if self._combo_exclusive:
            return
        if not self.fazendeira:
            self._show_garden_feedback(False, "Bridge não está disponível.")
            return
        green_aching_thumb_enabled = self.garden_thumbcorn_checkbox.isChecked()
        self._run_garden_task(
            lambda: self.fazendeira.run_cycle(
                dry_run=True,
                automation_enabled=False,
                green_aching_thumb_enabled=green_aching_thumb_enabled,
            ),
            self._display_garden_result,
        )

    def simulate_garden(self, _checked: bool = False):
        """Executa somente a leitura e o planejamento da Fazendeira."""
        if self._combo_exclusive:
            return
        if not self.fazendeira:
            self._show_garden_feedback(False, "Bridge não está disponível.")
            return
        logger.info("Garden: simulação solicitada; nenhuma ação será enviada ao jogo")
        green_aching_thumb_enabled = self.garden_thumbcorn_checkbox.isChecked()
        self._run_garden_task(
            lambda: self.fazendeira.run_cycle(
                dry_run=True,
                automation_enabled=False,
                green_aching_thumb_enabled=green_aching_thumb_enabled,
            ),
            self._display_garden_result,
        )

    def _on_garden_timer(self):
        if self._combo_exclusive:
            return
        if not self.fazendeira or (self._garden_worker and self._garden_worker.isRunning()):
            return
        self._garden_run_when_idle = False
        stop_event = self._garden_stop
        enabled = self.garden_toggle.running and not stop_event.is_set()
        green_aching_thumb_enabled = self.garden_thumbcorn_checkbox.isChecked()
        self._run_garden_task(
            lambda: self.fazendeira.run_cycle(
                dry_run=not enabled, automation_enabled=enabled,
                green_aching_thumb_enabled=green_aching_thumb_enabled,
                should_stop=stop_event.is_set,
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
        if self.garden_toggle.running:
            self._toggle_garden_automation(False)
        logger.error(f"Garden: falha inesperada no worker: {message}")
        self._show_garden_feedback(False, f"Falha inesperada: {message}")
        self._schedule_next_garden_tick(None)

    def _garden_task_finished(self):
        self._garden_worker = None
        if self.garden_toggle.stopping:
            self.garden_toggle.set_running(False)
        self._set_garden_busy(False)
        if self._garden_run_when_idle and self.garden_toggle.running:
            QTimer.singleShot(0, self._on_garden_timer)

    def _display_garden_result(self, value: object):
        if not isinstance(value, GardenCycleResult):
            self._show_garden_feedback(False, "Resposta inesperada do ciclo do Garden.")
            logger.error("Garden: worker retornou resultado inválido")
            return
        snapshot, plan = value.snapshot, value.plan
        achievement_completed = plan.mode == "green_aching_thumb" and plan.completed
        if achievement_completed and self.garden_thumbcorn_checkbox.isChecked():
            self.garden_thumbcorn_checkbox.blockSignals(True)
            self.garden_thumbcorn_checkbox.setChecked(False)
            self.garden_thumbcorn_checkbox.blockSignals(False)
            automation_config.enable_green_aching_thumb = False
            save_automation_settings()
            logger.info("Garden: conquista Green, aching thumb obtida; modo Thumbcorn desativado")
            # O próximo ciclo real continua a coleção normal. A prévia abaixo
            # também a mostra imediatamente, sem nova chamada à bridge.
            if self.fazendeira:
                plan = self.fazendeira.build_plan(snapshot)
            if self.garden_toggle.running:
                self._garden_run_when_idle = True
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
        if achievement_completed:
            self._show_garden_feedback(
                True,
                "Conquista Green, aching thumb obtida no runtime; modo Thumbcorn desativado e coleção normal retomada.",
            )
        elif value.action_results:
            successes = sum(result.success for result in value.action_results)
            waits = [result for result in value.action_results if result.waiting]
            errors = [result for result in value.action_results if not result.success and not result.waiting]
            if waits and not errors:
                waiting = waits[0]
                message = waiting.message
                if waiting.required_cookies is not None and waiting.available_cookies is not None:
                    missing = max(0.0, waiting.required_cookies - waiting.available_cookies)
                    message += (f" Custo: {self._format_number(waiting.required_cookies)}; "
                                f"saldo: {self._format_number(waiting.available_cookies)}; "
                                f"faltam: {self._format_number(missing)} cookies.")
                message += " Tentará novamente no próximo tick."
                self.garden_status_label.setText("Garden: aguardando dinheiro")
                self.garden_status_label.setStyleSheet("color: #e8b766; font-weight: 600;")
                self.garden_feedback_label.setText(message)
                self.garden_feedback_label.setStyleSheet("color: #e8b766;")
                self.status_bar.showMessage(message, 7000)
            else:
                details = "; ".join(result.message for result in value.action_results)
                self._show_garden_feedback(
                    not errors and not waits,
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
        self.garden_thumbcorn_checkbox.setEnabled(not busy)
        if busy:
            self.garden_feedback_label.setText("Consultando o runtime do Garden em segundo plano...")
            self.garden_feedback_label.setStyleSheet("color: #9aa7ba;")

    def _toggle_garden_automation(self, enabled: bool):
        if enabled:
            if self._combo_exclusive or not self.bridge or not self.fazendeira:
                self._show_garden_feedback(False, "Não foi possível ligar: conecte a bridge e aguarde o Combo terminar.")
                return
            self._garden_stop = threading.Event()
            self.garden_toggle.set_running(True)
            self.garden_refresh_timer.stop()
            if self._garden_worker and self._garden_worker.isRunning():
                self._garden_run_when_idle = True
            else:
                QTimer.singleShot(0, self._on_garden_timer)
        else:
            self._garden_stop.set()
            self._garden_run_when_idle = False
            if self._garden_worker and self._garden_worker.isRunning():
                self.garden_toggle.set_stopping()
            else:
                self.garden_toggle.set_running(False)
        logger.info("Garden: %s", "ligada" if enabled else "desligamento solicitado")
        self._show_garden_feedback(True, "Automação ligada." if enabled else "Novas ações interrompidas; aguardando o lote em andamento terminar.")

    def _toggle_green_aching_thumb(self, state: int):
        enabled = bool(state)
        automation_config.enable_green_aching_thumb = enabled
        save_automation_settings()
        logger.info(
            f"Garden: modo Green, aching thumb {'habilitado' if enabled else 'desativado'}"
        )
        if enabled and not self.garden_toggle.running:
            message = "Estratégia Thumbcorn selecionada; use Ligar para executar."
        else:
            message = (
                "Modo Green, aching thumb habilitado."
                if enabled else "Modo Green, aching thumb desativado."
            )
        self._show_garden_feedback(enabled, message)
        if enabled and not (self._garden_worker and self._garden_worker.isRunning()):
            QTimer.singleShot(0, self.refresh_garden)

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
            elif self.garden_toggle.running:
                # O jogo pode estar suspenso em segundo plano; confira sem
                # executar novamente até ``M.nextStep`` realmente avançar.
                delay_ms = 1_000
        self.garden_refresh_timer.start(delay_ms)

    def _update_garden_interval(self, value: int):
        interval = min(3600, max(30, int(value)))
        automation_config.garden_poll_interval_seconds = interval
        save_automation_settings()
        if not self.garden_toggle.running:
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
        self._stock_stop.set()
        self._garden_stop.set()
        if self._combo_worker and self._combo_worker.isRunning():
            self._combo_worker.stop()
            self._combo_worker.wait((app_config.connection_timeout + 2) * 1000)
        if self.runner and self._simple_farm_automation is not None:
            self.runner.release_simple_farm()
        if self._combo_exclusive and self.runner:
            self.runner.release_exclusive("combo")
            self._combo_exclusive = False
        if self._combo_keep_awake:
            self._set_combo_keep_awake(False)
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
