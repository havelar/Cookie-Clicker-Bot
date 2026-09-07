"""Interface gráfica principal do Cookie Clicker Bot."""
import sys
from pathlib import Path
from typing import Callable, Optional

from PyQt5.QtCore import QThread, QTimer, pyqtSignal, QObject, Qt
from PyQt5.QtGui import QColor, QIcon, QTextCursor
from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QTextEdit, QLabel, QGroupBox, QStatusBar, QDoubleSpinBox, QSpinBox, QGridLayout, QTabWidget, QHeaderView, QTableWidget, QTableWidgetItem)

from app.bridge.js_bridge import CookieClickerBridge
from app.config.settings import app_config, automation_config, save_app_settings, save_automation_settings
from app.core.backup_manager import BackupManager
from app.core.stock_market import StockMarketAutomation
from app.models.stock_market import StockMarketAutomationResult, StockMarketSnapshot, StockTradeResult
from app.ui.backup_dialog import BackupDialog
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
        self.stock_automation = StockMarketAutomation(bridge) if bridge else None
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
        log_options = QHBoxLayout(); log_options.addWidget(QLabel("Máximo de linhas")); log_options.addStretch()
        self.log_limit_input = QSpinBox(); self.log_limit_input.setRange(1, 100000); self.log_limit_input.setValue(app_config.max_log_lines); self.log_limit_input.setToolTip("Limita apenas o histórico exibido nesta janela")
        self.log_limit_input.valueChanged.connect(self.update_log_limit); log_options.addWidget(self.log_limit_input); group_layout.addLayout(log_options)
        self.log_text = QTextEdit(); self.log_text.setReadOnly(True); self.log_text.setMinimumHeight(230); group_layout.addWidget(self.log_text); layout.addWidget(group); return tab

    def _stock_market_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setContentsMargins(14, 12, 14, 12); layout.setSpacing(8)
        toolbar = QWidget(); toolbar_layout = QHBoxLayout(toolbar); toolbar_layout.setContentsMargins(0, 0, 0, 0); toolbar_layout.setSpacing(8)
        self.stock_status_label = QLabel("Mercado: carregando")
        self.stock_status_label.setStyleSheet("color: #9aa7ba; font-weight: 600;")
        self.stock_status_label.setMinimumWidth(130)
        self.stock_hourly_label = QLabel("$/h: —")
        self.stock_hourly_label.setStyleSheet("color: #9aa7ba; font-weight: 600;")
        self.stock_hourly_label.setToolTip("Resultado do Stock Market por hora nesta sessão")
        self.stock_auto_trade_checkbox = QCheckBox("Auto")
        self.stock_auto_trade_checkbox.setToolTip(
            "Executa ordens MAX quando preço e tendência atendem às regras"
        )
        self.stock_auto_trade_checkbox.setChecked(automation_config.enable_stock_market_auto_trade)
        self.stock_auto_trade_checkbox.stateChanged.connect(self._toggle_stock_auto_trade)
        toolbar_layout.addWidget(self.stock_status_label)
        toolbar_layout.addWidget(self.stock_hourly_label)
        toolbar_layout.addSpacing(10)
        toolbar_layout.addWidget(QLabel("Comprar < $"))
        self.stock_buy_limit_input = QDoubleSpinBox(); self.stock_buy_limit_input.setRange(0.01, 1_000_000_000.0); self.stock_buy_limit_input.setDecimals(2); self.stock_buy_limit_input.setValue(automation_config.stock_market_buy_price_limit); self.stock_buy_limit_input.valueChanged.connect(self._update_stock_buy_limit)
        self.stock_buy_limit_input.setFixedWidth(86)
        toolbar_layout.addWidget(self.stock_buy_limit_input); toolbar_layout.addSpacing(6)
        toolbar_layout.addWidget(QLabel("Vender > $"))
        self.stock_sell_limit_input = QDoubleSpinBox(); self.stock_sell_limit_input.setRange(0.01, 1_000_000_000.0); self.stock_sell_limit_input.setDecimals(2); self.stock_sell_limit_input.setValue(automation_config.stock_market_sell_price_limit); self.stock_sell_limit_input.valueChanged.connect(self._update_stock_sell_limit)
        self.stock_sell_limit_input.setFixedWidth(86)
        toolbar_layout.addWidget(self.stock_sell_limit_input); toolbar_layout.addSpacing(8)
        toolbar_layout.addWidget(QLabel("Ticks"))
        self.stock_trend_ticks_input = QSpinBox()
        self.stock_trend_ticks_input.setRange(2, 180)
        self.stock_trend_ticks_input.setValue(automation_config.stock_market_trend_ticks)
        self.stock_trend_ticks_input.setToolTip("Janela usada para confirmar a tendência geral")
        self.stock_trend_ticks_input.valueChanged.connect(self._update_stock_trend_ticks)
        self.stock_trend_ticks_input.setFixedWidth(64)
        toolbar_layout.addWidget(self.stock_trend_ticks_input)
        toolbar_layout.addWidget(QLabel("Mov. ≥ %"))
        self.stock_reversal_percent_input = QDoubleSpinBox()
        self.stock_reversal_percent_input.setRange(0.01, 100.0)
        self.stock_reversal_percent_input.setDecimals(2)
        self.stock_reversal_percent_input.setValue(automation_config.stock_market_reversal_percent)
        self.stock_reversal_percent_input.setToolTip("Variação mínima em um tick para confirmar a reversão")
        self.stock_reversal_percent_input.valueChanged.connect(self._update_stock_reversal_percent)
        self.stock_reversal_percent_input.setFixedWidth(64)
        toolbar_layout.addWidget(self.stock_reversal_percent_input)
        toolbar_layout.addWidget(self.stock_auto_trade_checkbox); toolbar_layout.addStretch()
        self.stock_candidates_label = QLabel()
        self.stock_candidates_label.setStyleSheet("color: #e8b766;")
        toolbar_layout.addWidget(self.stock_candidates_label)
        layout.addWidget(toolbar)

        self.stock_table = QTableWidget(0, 4)
        self.stock_table.setHorizontalHeaderLabels(("Ativo", "Preço", "Variação", "Estoque"))
        self.stock_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.stock_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.stock_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.stock_table.verticalHeader().setVisible(False)
        header = self.stock_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
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
        self._run_stock_task(
            lambda: self.stock_automation.run_cycle(
                buy_limit,
                sell_limit,
                trend_ticks,
                reversal_percent,
                self.stock_auto_trade_checkbox.isChecked(),
            ),
            self._display_stock_automation_result,
        )

    def _toggle_stock_auto_trade(self, state: int):
        automation_config.enable_stock_market_auto_trade = bool(state)
        save_automation_settings()
        status = "ativado" if state else "desativado"
        logger.info(f"Stock Market: automação {status}")
        self._show_stock_feedback(bool(state), f"Automação {status}.")

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
        self.stock_table.setRowCount(0)
        if not snapshot.status.available:
            self.stock_hourly_label.setText("$/h: —")
            self.stock_candidates_label.setText("")
            self._show_stock_feedback(False, snapshot.status.message)
            self._update_stock_actions()
            return
        rate = self.stock_automation.profit_per_hour(snapshot) if self.stock_automation else None
        self.stock_hourly_label.setText(self._format_stock_hourly_rate(rate))
        assets_by_price = sorted(snapshot.assets, key=lambda asset: asset.price)
        self.stock_table.setRowCount(len(assets_by_price))
        buy_limit = float(self.stock_buy_limit_input.value())
        for row, asset in enumerate(assets_by_price):
            variation = self._format_variation(asset.price_change_percent)
            name = f"{asset.name} ({asset.symbol})" if asset.symbol else asset.name
            values = (name, f"${asset.price:,.2f}", variation, str(asset.owned))
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column == 0:
                    item.setData(Qt.UserRole, asset.asset_id)
                if column == 2 and asset.price_change_percent is not None:
                    item.setForeground(Qt.green if asset.price_change_percent >= 0 else Qt.red)
                if asset.price < buy_limit:
                    item.setBackground(QColor("#3a3420"))
                if column in (1, 2, 3):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.stock_table.setItem(row, column, item)
        self._update_stock_candidates()
        self._show_stock_feedback(True, f"{len(snapshot.assets)} ativos carregados (preço crescente).")
        self._update_stock_actions()
        logger.debug(f"Stock Market: snapshot carregado com {len(snapshot.assets)} ativos")

    @staticmethod
    def _format_stock_hourly_rate(rate: Optional[float]) -> str:
        if rate is None:
            return "$/h: —"
        return f"$/h: ${rate:+,.2f}"

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
        buy_limit = float(self.stock_buy_limit_input.value())
        candidates = sorted(
            (asset for asset in self._stock_snapshot.assets if asset.price < buy_limit),
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
        if not self.runner: return
        self.cookies_clicked_label.setText(f"Cookies clicados\n{self.runner.cookies_clicked}"); self.golden_clicked_label.setText(f"Golden Cookies\n{self.runner.golden_cookies_clicked}"); self.reindeer_popped_label.setText(f"Renas coletadas\n{self.runner.reindeer_popped}"); self.wrinklers_popped_label.setText(f"Wrinklers coletados\n{self.runner.wrinklers_popped}")
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
