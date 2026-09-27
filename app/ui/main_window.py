"""Interface gráfica principal do Cookie Clicker Bot."""
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from PyQt5.QtCore import QThread, QTimer, pyqtSignal, QObject, Qt
from PyQt5.QtGui import QColor, QIcon, QTextCursor
from PyQt5.QtWidgets import (QAbstractItemView, QAbstractSpinBox, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QComboBox, QTextEdit, QLabel, QGroupBox, QStatusBar, QDoubleSpinBox, QSpinBox, QGridLayout, QTabWidget, QHeaderView, QTableWidget, QTableWidgetItem)

from app.bridge.js_bridge import CookieClickerBridge, DEFAULT_GRIMOIRE_SPELLS
from app.config.settings import app_config, automation_config, save_app_settings, save_automation_settings
from app.core.backup_manager import BackupManager
from app.core.stock_market import StockMarketAutomation
from app.core.stock_policy import GASEOUS_ASSETS_TARGET, asset_limits
from app.models.stock_market import StockMarketAutomationResult, StockMarketSnapshot, StockTradeResult
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
        self._session_started_at = time.monotonic()
        self.stock_automation = StockMarketAutomation(bridge) if bridge else None
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

        tabs = QTabWidget(); tabs.addTab(self._automation_tab(), "Automações"); tabs.addTab(self._sugar_tab(), "Sugar Lumps"); tabs.addTab(self._stock_market_tab(), "Stock Market"); tabs.addTab(self._activity_tab(), "Atividade"); layout.addWidget(tabs, 1)
        self.stats_timer = QTimer(self); self.stats_timer.timeout.connect(self.refresh_stats); self.stats_timer.start(1000)
        self.status_bar = QStatusBar(); self.setStatusBar(self.status_bar); self.status_bar.showMessage("Pronto para conectar ao Cookie Clicker")
        self.stock_refresh_timer = QTimer(self)
        self.stock_refresh_timer.timeout.connect(self._on_stock_market_timer)
        if self.bridge:
            self.stock_refresh_timer.start(5_000)
            QTimer.singleShot(0, self._on_stock_market_timer)

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
        group_layout.addLayout(grid); layout.addWidget(group)

        grimoire_group = QGroupBox("Grimoire"); grimoire_layout = QHBoxLayout(grimoire_group)
        self.grimoire_spell_spam_checkbox = QCheckBox("Spammar Skill")
        self.grimoire_spell_spam_checkbox.setToolTip(
            "Aguarda a mana chegar ao máximo e usa uma vez a skill selecionada"
        )
        self.grimoire_spell_spam_checkbox.setChecked(automation_config.enable_grimoire_spell_spam)
        self.grimoire_spell_spam_checkbox.stateChanged.connect(self.toggle_grimoire_spell_spam)
        grimoire_layout.addWidget(self.grimoire_spell_spam_checkbox)
        grimoire_layout.addStretch()
        grimoire_layout.addWidget(QLabel("Skill"))
        self.grimoire_spell_combo = QComboBox(); self.grimoire_spell_combo.setMinimumWidth(230)
        self._load_grimoire_spells()
        self.grimoire_spell_combo.currentIndexChanged.connect(self.update_grimoire_spell)
        self.grimoire_spell_combo.setEnabled(automation_config.enable_grimoire_spell_spam)
        grimoire_layout.addWidget(self.grimoire_spell_combo)
        layout.addWidget(grimoire_group); layout.addStretch(); return tab

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
        log_options = QHBoxLayout(); log_options.addWidget(QLabel("Máximo de linhas")); log_options.addStretch()
        self.log_limit_input = QSpinBox(); self.log_limit_input.setRange(1, 100000); self.log_limit_input.setValue(app_config.max_log_lines); self.log_limit_input.setToolTip("Limita apenas o histórico exibido nesta janela")
        self.log_limit_input.valueChanged.connect(self.update_log_limit); log_options.addWidget(self.log_limit_input); group_layout.addLayout(log_options)
        self.log_text = QTextEdit(); self.log_text.setReadOnly(True); self.log_text.setMinimumHeight(230); group_layout.addWidget(self.log_text); layout.addWidget(group); return tab

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
        self.stock_auto_trade_checkbox = QCheckBox("Auto")
        self.stock_auto_trade_checkbox.setToolTip(
            "Executa ordens MAX com os limites por ativo; novas compras param ao atingir Gaseous assets"
        )
        self.stock_auto_trade_checkbox.setChecked(automation_config.enable_stock_market_auto_trade)
        self.stock_auto_trade_checkbox.stateChanged.connect(self._toggle_stock_auto_trade)
        self.stock_owned_only_checkbox = QCheckBox("Só meus")
        self.stock_owned_only_checkbox.setToolTip(
            "No jogo, mostra somente cards de ativos com ações em estoque"
        )
        self.stock_owned_only_checkbox.setChecked(automation_config.enable_stock_market_owned_only_view)
        self.stock_owned_only_checkbox.stateChanged.connect(self._toggle_stock_owned_only_view)
        toolbar_layout.addWidget(self.stock_status_label)
        toolbar_layout.addWidget(self.stock_total_profit_label)
        toolbar_layout.addWidget(self.stock_goal_label)
        self.stock_limits_button = QPushButton("Limites por ativo")
        self.stock_limits_button.clicked.connect(self._configure_stock_limits)
        toolbar_layout.addWidget(self.stock_limits_button)
        toolbar_layout.addSpacing(4)
        buy_label = QLabel("Compra < $")
        buy_label.setToolTip("Compra abaixo deste preço")
        toolbar_layout.addWidget(buy_label)
        self.stock_buy_limit_input = QDoubleSpinBox(); self.stock_buy_limit_input.setRange(0.01, 1_000_000_000.0); self.stock_buy_limit_input.setDecimals(2); self.stock_buy_limit_input.setValue(automation_config.stock_market_buy_price_limit); self.stock_buy_limit_input.valueChanged.connect(self._update_stock_buy_limit)
        self.stock_buy_limit_input.setButtonSymbols(QAbstractSpinBox.NoButtons); self.stock_buy_limit_input.setFixedWidth(66)
        toolbar_layout.addWidget(self.stock_buy_limit_input)
        sell_label = QLabel("Venda > $")
        sell_label.setToolTip("Vende acima deste preço")
        toolbar_layout.addWidget(sell_label)
        self.stock_sell_limit_input = QDoubleSpinBox(); self.stock_sell_limit_input.setRange(0.01, 1_000_000_000.0); self.stock_sell_limit_input.setDecimals(2); self.stock_sell_limit_input.setValue(automation_config.stock_market_sell_price_limit); self.stock_sell_limit_input.valueChanged.connect(self._update_stock_sell_limit)
        self.stock_sell_limit_input.setButtonSymbols(QAbstractSpinBox.NoButtons); self.stock_sell_limit_input.setFixedWidth(66)
        toolbar_layout.addWidget(self.stock_sell_limit_input)
        # Os limites gerais são o fallback; a edição individual fica no diálogo.
        for control in (buy_label, self.stock_buy_limit_input, sell_label, self.stock_sell_limit_input):
            control.hide()
        ticks_label = QLabel("T")
        ticks_label.setToolTip("Quantidade de ticks usada para validar a tendência")
        toolbar_layout.addWidget(ticks_label)
        self.stock_trend_ticks_input = QSpinBox()
        self.stock_trend_ticks_input.setRange(2, 64)
        self.stock_trend_ticks_input.setValue(automation_config.stock_market_trend_ticks)
        self.stock_trend_ticks_input.setToolTip("Janela usada para confirmar a tendência geral")
        self.stock_trend_ticks_input.valueChanged.connect(self._update_stock_trend_ticks)
        self.stock_trend_ticks_input.setButtonSymbols(QAbstractSpinBox.NoButtons); self.stock_trend_ticks_input.setFixedWidth(42)
        toolbar_layout.addWidget(self.stock_trend_ticks_input)
        movement_label = QLabel("Δ ≥ %")
        movement_label.setToolTip("Variação mínima em um tick para confirmar a reversão")
        toolbar_layout.addWidget(movement_label)
        self.stock_reversal_percent_input = QDoubleSpinBox()
        self.stock_reversal_percent_input.setRange(0.01, 100.0)
        self.stock_reversal_percent_input.setDecimals(2)
        self.stock_reversal_percent_input.setValue(automation_config.stock_market_reversal_percent)
        self.stock_reversal_percent_input.setToolTip("Variação mínima em um tick para confirmar a reversão")
        self.stock_reversal_percent_input.valueChanged.connect(self._update_stock_reversal_percent)
        self.stock_reversal_percent_input.setButtonSymbols(QAbstractSpinBox.NoButtons); self.stock_reversal_percent_input.setFixedWidth(58)
        toolbar_layout.addWidget(self.stock_reversal_percent_input)
        toolbar_layout.addWidget(self.stock_auto_trade_checkbox)
        toolbar_layout.addWidget(self.stock_owned_only_checkbox); toolbar_layout.addStretch()
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
        buy_on_discount = automation_config.stock_market_buy_on_discount
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
                buy_on_discount=buy_on_discount,
            ),
            self._display_stock_automation_result,
        )

    def _configure_stock_limits(self):
        if not self._stock_snapshot or not self._stock_snapshot.status.available:
            self._show_stock_feedback(False, "Aguarde a leitura do mercado para configurar os ativos.")
            return
        dialog = StockLimitsDialog(
            self._stock_snapshot, automation_config.stock_market_asset_limits,
            automation_config.stock_market_use_reference_prices,
            automation_config.stock_market_buy_on_discount, self,
            buy_limit=self.stock_buy_limit_input.value(), sell_limit=self.stock_sell_limit_input.value(),
        )
        if dialog.exec_():
            automation_config.stock_market_asset_limits = dialog.overrides
            automation_config.stock_market_use_reference_prices = dialog.use_reference_prices
            automation_config.stock_market_buy_on_discount = dialog.buy_on_discount
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
        if self._stock_worker and self._stock_worker.isRunning():
            self._stock_worker.wait((app_config.connection_timeout + 1) * 1000)
        super().closeEvent(event)


def create_ui_app(bridge: Optional[CookieClickerBridge] = None):
    set_windows_app_id()
    app = QApplication(sys.argv); app.setStyleSheet(DARK_STYLESHEET); enable_dark_title_bars(app)
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    window = MainWindow(bridge); window.setWindowIcon(app.windowIcon())
    return app, window
