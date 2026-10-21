"""Interface gráfica principal do Cookie Clicker Bot."""
import sys
import re
import time
import ctypes
import threading
from pathlib import Path
from typing import Callable, Optional

from PyQt5.QtCore import QThread, QTimer, pyqtSignal, QObject, Qt
from PyQt5.QtGui import QColor, QIcon, QTextCursor
from PyQt5.QtWidgets import (QAbstractItemView, QSizePolicy, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QComboBox, QTextEdit, QLabel, QGroupBox, QStatusBar, QGridLayout, QFormLayout, QTabWidget, QHeaderView, QTableWidget, QTableWidgetItem, QScrollArea, QMessageBox)

from app.bridge.js_bridge import CookieClickerBridge, DEFAULT_GRIMOIRE_SPELLS
from app.config.settings import CLICKER_HOTKEYS, app_config, automation_config, save_app_settings, save_automation_settings
from app.core.backup_manager import BackupManager
from app.core.auto_ascensao import AutoAscensao, ConfiguracaoAutoAscensao
from app.core.combo import ComboAutomation
from app.core.simple_farm import SimpleFarmAutomation
from app.core.fazendeira import Fazendeira
from app.core.garden_strategies import GARDEN_STRATEGIES
from app.core.seasons import SEASONS
from app.core.stock_market import StockMarketAutomation
from app.core.stock_policy import asset_limits
from app.models.stock_market import StockMarketAutomationResult, StockMarketSnapshot, StockTradeResult
from app.models.garden import GardenCycleResult
from app.models.auto_ascensao import RelatorioAutoAscensao
from app.models.combo import ConfiguracaoCombo, EstadoCombo, RelatorioCombo
from app.models.simple_farm import ConfiguracaoSimpleFarm, RelatorioSimpleFarm
from app.ui.backup_dialog import BackupDialog
from app.ui.combo_planner import ComboPlanner
from app.ui.save_scum_tab import SaveScumTab
from app.ui.automation_control import AutomationControl
from app.ui.hotkey_capture import HotkeyCapture
from app.ui.garden_presentation import current_state, grouped_actions, pending_actions, result_summary, short_message
from app.ui.number_inputs import ScrollSafeComboBox, ScrollSafeDoubleSpinBox, ScrollSafeSpinBox
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
    open_game_requested = pyqtSignal()

    def __init__(self, bridge: Optional[CookieClickerBridge] = None):
        super().__init__()
        self._bot_enabled = False
        self._game_open = bool(bridge)
        self._connection_busy = False
        self._connection_recovering = False
        self._connection_resume_pending = False
        self._bot_stopping = False
        self._resume_clicker = False
        self._resume_mouse_clicker = False
        self.bridge = bridge
        self.log_emitter, self.runner = LogSignalEmitter(), None
        self.backup_manager, self.backup_dialog = BackupManager(), None
        self._sugar_lump_worker: Optional[StockMarketWorker] = None
        self._sugar_lump_connected = bool(bridge)
        self._sugar_lump_connection_epoch = 0
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
        self._save_scum_exclusive = False
        self._save_scum_disabled_widgets = []
        self._save_scum_resume_clicker = False
        self._combo_keep_awake = False
        self._session_started_at = time.monotonic()
        self.stock_automation = StockMarketAutomation(bridge) if bridge else None
        self.fazendeira = Fazendeira(bridge) if bridge else None
        self.setup_ui()
        self._configure_user_tooltips()
        self.log_emitter.log_signal.connect(self.add_log)
        self.clicker_state_changed.connect(self.set_clicker_state)
        self.refresh_bot_control()

    @staticmethod
    def _automation_state_text(state):
        names = {"ocioso": "Desligada", "erro seguro": "Parada por segurança",
                 "alinhando FtHoF": "Preparando sequência de magias",
                 "alinhando spells": "Preparando sequência de magias",
                 "aguardando buff natural": "Aguardando bônus natural",
                 "aguardando buffs naturais": "Aguardando bônus naturais",
                 "executando Quadcast": "Usando as quatro magias do combo",
                 "janela de cliques": "Aproveitando os bônus de clique"}
        return names.get(state, state[:1].upper() + state[1:])

    def _configure_user_tooltips(self):
        tips = {
            "clicker_hotkey_input": "Clique em Apertar para detectar e pressione a tecla ou o botão lateral desejado. Esc cancela. O atalho funciona com o bot ligado no topo.",
            "mouse_clicker_hotkey_input": "Clique em Apertar para detectar e pressione uma tecla ou botão lateral. Esc cancela. Escolha um atalho diferente do cookie principal.",
            "mouse_clicker_speed_input": "Quantidade desejada de cliques por segundo na posição do mouse. A configuração fica salva.",
            "mouse_clicker_button": "Repete cliques na posição do cursor, apenas sobre a janela do jogo. Usa a quantidade e o modo Comprar/Vender escolhidos no jogo. As compras podem consumir o dinheiro reservado para Garden e Banco.",
            "clicker_speed_input": "Quantidade desejada de cliques por segundo. O ritmo real depende do jogo e do computador. A alteração vale imediatamente e fica salva.",
            "clicker_button": "Liga ou desliga os cliques no cookie principal. As outras automações seguem a seleção de cada aba.",
            "golden_checkbox": "Coleta os Golden Cookies assim que aparecem, incluindo os cookies de ira.",
            "fortune_checkbox": "Clica nas notícias de fortuna quando aparecem no topo do jogo.",
            "reindeer_checkbox": "Coleta as renas que aparecem durante a temporada de Natal.",
            "grimoire_spell_spam_checkbox": "Usa a magia escolhida em Configurações quando a mana estiver cheia. Aguarda a recarga para usar novamente.",
            "garden_refresh_button": "Atualiza as plantas, sementes e próximas ações sem alterar o Garden.",
            "garden_simulate_button": "Mostra o que a automação faria com as plantas atuais, sem executar as ações.",
            "garden_toggle": "Busca sementes e ajusta o plantio dos pais para ficarem maduros juntos. As esperas aparecem na prévia e são recalculadas conforme o crescimento. Se faltarem cookies, aguarda antes de remover plantas.",
            "combo_search_input": "Quantidade de resultados futuros de magia a considerar ao buscar um combo. Valores maiores podem aumentar o tempo de análise.",
            "combo_lumps_input": "Máximo de Sugar Lumps usados para preparar as magias. O Sugar Frenzy, se ativado, tem um gasto separado.",
            "combo_bs_input": "Quantidade de bônus de construções que precisam estar ativos juntos para iniciar o combo.",
            "combo_interval_input": "Tempo entre verificações de mana, bônus e oportunidades de combo.",
            "combo_min_buff_input": "Tempo que os bônus ainda precisam durar para o bot tentar completar o combo.",
            "combo_sugar_checkbox": "Gasta 1 Sugar Lump para ativar Sugar Frenzy no combo final, quando disponível.",
            "combo_loans_checkbox": "Ativa os três empréstimos no combo final. Eles aumentam a produção por um período e depois aplicam penalidades.",
            "combo_toggle": "Prepara e executa o combo avançado. Pausa as outras automações durante a tentativa.",
            "combo_preview_button": "Mostra a oportunidade de combo prevista para o jogo atual, sem gastar recursos.",
            "combo_resume_button": "Continua a preparação do combo após a pausa para acompanhamento.",
            "simple_farm_toggle": "Coleta Golden Cookies, combina bônus e compra melhorias dentro do orçamento. Garden e Banco podem continuar funcionando.",
            "simple_farm_preview_button": "Mostra a próxima oportunidade de magia e os recursos disponíveis, sem gastar cookies ou mana.",
            "simple_farm_search_input": "Quantas magias futuras analisar. Prioriza Click Frenzy junto de outro bônus; usa Haggler's Charm para preparar a sequência fora dos bônus ativos.",
            "simple_farm_interval_input": "Tempo entre verificações do jogo. As compras têm um intervalo separado de 15 segundos.",
            "simple_farm_min_buff_input": "Tempo que o bônus natural ainda precisa durar para valer a pena adicionar uma magia de Click Frenzy.",
            "simple_farm_reserve_input": "Percentual do maior saldo visto nesta execução reservado para Garden e Banco. O farm espera se o saldo cair abaixo da reserva e também mantém cookies para Lucky.",
            "simple_farm_investment_input": "Gasto máximo em upgrades e construções a cada 15 segundos, sem usar a reserva. A recompra de torres para duas magias também precisa preservar essa reserva.",
            "simple_farm_resources_label": "Magias já usadas no Grimoire, mana disponível, cookies no saldo e reserva mantida pelo farm.",
            "simple_farm_plan_label": "Bônus previstos e magias necessárias para preparar a próxima oportunidade. Duas magias podem exigir vender e recomprar torres, dentro do orçamento.",
            "combo_progress_label": "Magias já usadas, mana disponível e Sugar Lumps restantes. Gastos indica quantos Sugar Lumps foram usados nesta tentativa.",
            "combo_garden_label": "Quantidade de plantas maduras na última leitura. O combo pode iniciar mesmo sem um Garden preparado.",
            "simple_farm_pantheon_label": "Espíritos equipados no Pantheon. O Simple Farm mantém essa escolha.",
            "auto_ascension_cycles_input": "Quantidade de ascensões a completar antes de desligar a automação.",
            "auto_ascension_prestige_input": "Prestígio mínimo a ganhar antes de iniciar a próxima ascensão.",
            "auto_ascension_interval_input": "Tempo entre verificações de progresso e compras durante cada ascensão.",
            "auto_ascension_timeout_input": "Tempo máximo para completar uma ascensão. Ao atingir o limite, a automação desliga.",
            "auto_ascension_toggle": "Começa a sequência a partir da tela de ascensão. Desligar impede novas etapas após a ação em andamento.",
            "auto_ascension_preview_button": "Mostra a próxima etapa e as compras previstas sem alterar o jogo.",
            "grimoire_spell_combo": "Magia usada pela opção Usar magia com mana cheia. O modo Combo controla suas próprias magias.",
            "stock_buy_limit_input": "Preço máximo usado para buscar compras quando não há um limite personalizado ou uma referência por ativo.",
            "stock_sell_limit_input": "Preço a partir do qual a automação busca uma venda lucrativa, quando não há um limite personalizado ou uma referência por ativo.",
            "stock_owned_only_checkbox": "No jogo, mostra apenas os ativos que você possui. Não altera a estratégia de compra e venda.",
            "stock_quantity_input": "Quantidade de unidades para a compra ou venda manual.",
            "stock_use_max_checkbox": "Compra o máximo permitido pelo saldo e pela capacidade, ou vende todo o estoque do ativo selecionado.",
            "stock_buy_button": "Compra o ativo selecionado na quantidade escolhida, usando cookies do jogo.",
            "stock_sell_button": "Vende o ativo selecionado na quantidade escolhida. Esta é uma ordem manual.",
            "stock_total_profit_label": "Variação do resultado das negociações mais o valor do estoque desde o início desta sessão, em dólares do mercado.",
            "log_text": "Histórico das ações e avisos. Coletas repetidas são agrupadas. Role até o fim para acompanhar as novas mensagens.",
        }
        for name, tip in tips.items():
            getattr(self, name).setToolTip(tip)
        for form in self.findChildren(QFormLayout):
            for row in range(form.rowCount()):
                field = form.itemAt(row, QFormLayout.FieldRole)
                label = form.itemAt(row, QFormLayout.LabelRole)
                if field and label and field.widget() and label.widget():
                    label.widget().setToolTip(field.widget().toolTip())

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
        self.open_game_button = QPushButton("Abrir jogo")
        self.open_game_button.setObjectName("primaryButton")
        self.open_game_button.setMinimumSize(140, 36)
        self.bot_status = QLabel("Jogo fechado")
        self.bot_status.setStyleSheet("color: #aeb8c9;")
        self.open_game_button.setToolTip("Abre o jogo e conecta o bot automaticamente. Deixe a Steam aberta.")
        self.open_game_button.clicked.connect(lambda: self.open_game_requested.emit())
        self.clicker_button = QPushButton("Ligar"); self.clicker_button.setObjectName("clickerButton"); self.clicker_button.setCheckable(True); self.clicker_button.setFixedWidth(110); self.clicker_button.setMinimumHeight(32); self.clicker_button.clicked.connect(self.toggle_clicker)
        self.backups_button = QPushButton("Backups"); self.backups_button.setToolTip("Salvar, carregar e gerenciar backups do jogo"); self.backups_button.clicked.connect(self.open_backup_dialog)
        header.addWidget(self.bot_status); header.addWidget(self.open_game_button); header.addWidget(self.backups_button); layout.addLayout(header)

        summary = QWidget(); summary.setObjectName("sessionSummary")
        status_layout = QHBoxLayout(summary); status_layout.setContentsMargins(9, 4, 9, 4); status_layout.setSpacing(10)
        self.bridge_status, self.clicker_status = QLabel("Jogo: desconectado"), QLabel("Clicker: Parado")
        self.session_timer_label = QLabel("Sessão: 00:00:00")
        self.session_timer_label.setStyleSheet("color: #aeb8c9;")
        self.bridge_status.setStyleSheet("color: #f07883; font-weight: 600;"); self.clicker_status.setStyleSheet("color: #9aa7ba; font-weight: 600;")
        status_layout.addWidget(self.bridge_status); status_layout.addWidget(self.clicker_status); status_layout.addWidget(self.session_timer_label); status_layout.addStretch()

        self.cookies_clicked_label = QLabel("Cliques: 0"); self.golden_clicked_label = QLabel("Golden: 0")
        self.reindeer_popped_label = QLabel("Renas: 0"); self.wrinklers_popped_label = QLabel("Wrinklers: 0")
        metrics = QHBoxLayout(); metrics.setContentsMargins(9, 0, 9, 0); metrics.setSpacing(18)
        for label in (self.cookies_clicked_label, self.golden_clicked_label, self.reindeer_popped_label, self.wrinklers_popped_label):
            label.setStyleSheet("color: #aeb8c9;")
            metrics.addWidget(label)
        metrics.addStretch()
        self.sugar_lump_type_label = QLabel("Sugar Lump: —")
        self.sugar_lump_type_label.setStyleSheet("color: #aeb8c9;")
        self.sugar_lump_type_label.setToolTip("Tipo do Sugar Lump que está crescendo atualmente no jogo.")
        metrics.addWidget(self.sugar_lump_type_label)
        layout.addWidget(summary)
        layout.addLayout(metrics)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._automation_tab(), "Automações")
        self.tabs.addTab(self._stock_market_tab(), "Stock Market")
        self.tabs.addTab(self._garden_tab(), "Garden")
        self.tabs.addTab(self._combo_tab(), "Combo")
        self.tabs.addTab(self._auto_ascension_tab(), "Auto Ascensão")
        self.save_scum_tab = SaveScumTab(self)
        self.tabs.addTab(self.save_scum_tab, "Save Scum")
        self.tabs.addTab(self._activity_tab(), "Atividade")
        self.tabs.addTab(self._settings_tab(), "Configurações")
        layout.addWidget(self.tabs, 1)
        self.stats_timer = QTimer(self); self.stats_timer.timeout.connect(self.refresh_stats); self.stats_timer.start(1000)
        self.clicker_status_timer = QTimer(self)
        self.clicker_status_timer.timeout.connect(self.refresh_clicker_states)
        self.clicker_status_timer.start(50)
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

    def _bot_workers_running(self):
        return any(worker and worker.isRunning() for worker in
                   (self._combo_worker, self._auto_ascension_worker,
                    self.save_scum_tab.worker, self._stock_worker, self._garden_worker))

    def refresh_bot_control(self):
        """Um único botão representa o próximo passo, sem ligar ações por conexão."""
        self.automation_gate_label.setVisible(not self._bot_enabled)
        if not self._bot_enabled:
            for widget in (self.clicker_button, self.mouse_clicker_button, self.stock_toggle, self.garden_toggle,
                           self.simple_farm_toggle, self.combo_toggle, self.combo_resume_button,
                           self.auto_ascension_toggle, self.save_scum_tab.toggle):
                widget.setEnabled(False)
            self.stock_toggle.set_paused(True, "bot")
            self.garden_toggle.set_paused(True, "bot")
        self.automation_gate_label.setText(
            "Ações pausadas enquanto a conexão é recuperada." if self._connection_recovering else
            "Bot pausado. Ligue no topo para liberar as automações.")
        if self._connection_busy:
            return
        stopping = self._bot_stopping and self._bot_workers_running()
        if not stopping:
            self._bot_stopping = False
        if self._connection_recovering and self._game_open:
            self.open_game_button.setText("Manter pausado" if self._connection_resume_pending else "Reconectando…")
            self.open_game_button.setEnabled(self._connection_resume_pending)
            self.open_game_button.setToolTip("Cancela a retomada automática. A conexão continuará sendo recuperada.")
            self.bot_status.setText("Reconectando ao jogo")
            self.bot_status.setStyleSheet("color: #e8b766;")
            return
        self.open_game_button.setText("Desligar bot" if self._bot_enabled else
                                      "Pausando…" if stopping else
                                      "Ligar bot" if self._game_open else "Abrir jogo")
        self.open_game_button.setEnabled(not stopping)
        self.bot_status.setText("Bot ligado" if self._bot_enabled else
                               "Pausando automações" if stopping else
                               "Bot pausado" if self._game_open else "Jogo fechado")
        self.bot_status.setStyleSheet("color: " + ("#65d6a5" if self._bot_enabled else "#aeb8c9") + ";")
        self.open_game_button.setObjectName("dangerButton" if self._bot_enabled else "primaryButton")
        self.open_game_button.style().unpolish(self.open_game_button)
        self.open_game_button.style().polish(self.open_game_button)
        self.open_game_button.setToolTip(
            "Pausa todas as automações após a ação em andamento. O jogo continua aberto." if self._bot_enabled else
            "Libera as automações configuradas. Banco e Garden retomam a seleção; inicie os modos especiais nas abas." if self._game_open else
            "Abre o jogo e conecta o bot automaticamente. Deixe a Steam aberta.")

    def set_bot_enabled(self, enabled):
        if enabled and (self._connection_recovering or not self.bridge or not self.runner or self._bot_stopping
                        or self._save_scum_exclusive or self._combo_exclusive):
            self.add_log("Aguarde a conexão e o encerramento/recuperação das ações antes de ligar o bot.")
            return
        self._bot_enabled = enabled
        self._bot_stopping = not enabled and self._bot_workers_running()
        if self.runner:
            if not enabled:
                self._resume_clicker = self.runner.is_running
                self._resume_mouse_clicker = bool(self.runner.mouse_clicker_running)
            self.runner.set_paused(not enabled)
        if enabled:
            # Substitui os tokens só depois que os workers antigos terminaram.
            self._stock_stop = threading.Event()
            self._garden_stop = threading.Event()
            if not self.stock_toggle.running:
                self._stock_stop.set()
            if not self.garden_toggle.running:
                self._garden_stop.set()
            for widget in (self.clicker_button, self.mouse_clicker_button, self.stock_toggle, self.garden_toggle,
                           self.simple_farm_toggle, self.combo_toggle,
                           self.auto_ascension_toggle, self.save_scum_tab.toggle):
                widget.setEnabled(True)
            self.stock_toggle.set_paused(False)
            self.garden_toggle.set_paused(False)
            if self._resume_clicker:
                self.runner.ensure_clicker_running()
            if self._resume_mouse_clicker and not self.runner.mouse_clicker_running:
                self.runner.toggle_mouse_clicker()
            QTimer.singleShot(0, self._on_stock_market_timer)
            QTimer.singleShot(0, self._on_garden_timer)
        else:
            self._stock_stop.set()
            self._garden_stop.set()
            self._garden_run_when_idle = False
            self.stop_simple_farm()
            self.stop_combo()
            self.stop_auto_ascension()
            self.save_scum_tab.request(False)
        self.add_log("Bot ligado. Automações liberadas." if enabled else
                     "Bot pausado. Novas ações bloqueadas; modos especiais encerram com segurança.")
        self.refresh_bot_control()

    def attach_game(self, bridge, runner):
        """Conecta todos os recursos quando o jogo fica pronto após abrir a UI."""
        self.bridge, self.runner = bridge, runner
        if self.clicker_hotkey_input.is_capturing or self.mouse_clicker_hotkey_input.is_capturing:
            runner.hotkey_capture_active.set()
        self._game_open = True
        self._resume_mouse_clicker = False
        self._resume_clicker = False
        self._bot_enabled = False
        runner.set_paused(True)
        self.stock_automation = StockMarketAutomation(bridge)
        self.fazendeira = Fazendeira(bridge)
        self._stock_snapshot = None
        self.update_bridge_status(True)
        self.set_clicker_state(False)
        self._load_grimoire_spells()
        self.stock_refresh_timer.start(5000)
        QTimer.singleShot(0, self._on_stock_market_timer)
        QTimer.singleShot(0, self.refresh_garden)

    def set_connection_recovery(self, active, resume=False):
        self._connection_recovering = active
        self._connection_resume_pending = active and resume
        if active:
            self._stock_stop.set()
            self._garden_stop.set()
            self.stock_refresh_timer.stop()
            self.garden_refresh_timer.stop()
            self.bridge_status.setText("Jogo: reconectando" if self._game_open else "Jogo: desconectado")
            self.bridge_status.setStyleSheet("color: #e8b766; font-weight: 600;")
        self.refresh_bot_control()

    def _automation_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setContentsMargins(14, 16, 14, 14)
        group = QGroupBox("Ligar ou desligar"); group_layout = QVBoxLayout(group); grid = QGridLayout()
        controls = (("golden_checkbox", "Coletar Golden Cookies", "enable_golden_cookie", self.toggle_golden_detection), ("fortune_checkbox", "Coletar Fortune Cookies", "enable_fortune_cookie", self.toggle_fortune_detection), ("reindeer_checkbox", "Coletar Renas (Natal)", "enable_reindeer", self.toggle_reindeer_detection), ("wrinkler_checkbox", "Wrinklers inteligentes", "enable_wrinkler_popper", self.toggle_wrinkler_detection))
        for index, (name, text, setting, handler) in enumerate(controls):
            checkbox = QCheckBox(text); checkbox.setChecked(getattr(automation_config, setting)); checkbox.stateChanged.connect(handler); setattr(self, name, checkbox); grid.addWidget(checkbox, index // 2, index % 2)
        self.wrinkler_checkbox.setToolTip(
            "Mantém vagas para procurar Shiny, preserva os Shiny e os normais mais rentáveis. "
            "Pode liberar caixa para ações do Garden/Banco bloqueadas por falta de cookies. "
            "A quantidade de vagas pode ser ajustada em Configurações.")
        self.grimoire_spell_spam_checkbox = QCheckBox("Usar magia com mana cheia")
        self.grimoire_spell_spam_checkbox.setToolTip(
            "Aguarda a mana chegar ao máximo e usa uma vez a skill configurada"
        )
        self.grimoire_spell_spam_checkbox.setChecked(automation_config.enable_grimoire_spell_spam)
        self.grimoire_spell_spam_checkbox.stateChanged.connect(self.toggle_grimoire_spell_spam)
        grid.addWidget(self.grimoire_spell_spam_checkbox, 2, 0)
        self.sugar_lump_checkbox = QCheckBox("Coletar Sugar Lumps ao maturar")
        self.sugar_lump_checkbox.setToolTip("Colhe assim que matura, com 50% de chance de render zero. Os tipos preservados nas Configurações aguardam a fase de colheita garantida.")
        self.sugar_lump_checkbox.setChecked(automation_config.enable_sugar_lump_harvest)
        self.sugar_lump_checkbox.stateChanged.connect(self.toggle_sugar_lump_harvest)
        grid.addWidget(self.sugar_lump_checkbox, 2, 1)
        self.krumblor_checkbox = QCheckBox("Coletar Krumblor Upgrades")
        self.krumblor_checkbox.setToolTip("Faz carinho até liberar o upgrade dos 15 minutos atuais. Depois aguarda a próxima faixa. Requer Pet the dragon e Krumblor nível 8. Os upgrades são liberados, mas não comprados.")
        self.krumblor_checkbox.setChecked(automation_config.enable_krumblor_upgrades)
        self.krumblor_checkbox.stateChanged.connect(self.toggle_krumblor_upgrades)
        grid.addWidget(self.krumblor_checkbox, 3, 0, 1, 2)
        self.auto_season_checkbox = QCheckBox("Manter temporada ativa")
        self.auto_season_checkbox.setToolTip("Ativa a temporada escolhida nas Configurações e renova quando terminar. Compra o biscoito da temporada com cookies; o preço aumenta a cada ativação. Requer Season switcher.")
        self.auto_season_checkbox.setChecked(automation_config.enable_auto_season)
        self.auto_season_checkbox.stateChanged.connect(self.toggle_auto_season)
        grid.addWidget(self.auto_season_checkbox, 4, 0, 1, 2)
        grid.setColumnStretch(0, 1); grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(36); grid.setVerticalSpacing(3)
        self.automation_gate_label = QLabel("Bot pausado. Ligue no topo para liberar as automações.")
        self.automation_gate_label.setWordWrap(True)
        self.automation_gate_label.setStyleSheet("color: #e8b766;")
        group_layout.addWidget(self.automation_gate_label)
        group_layout.addLayout(grid)
        layout.addWidget(group)

        self.clicker_group = QGroupBox("Clickers")
        self.clicker_group.setMinimumHeight(240)
        clicker_layout = QHBoxLayout(self.clicker_group)
        self.clicker_run_status = QLabel("Desligado")
        self.mouse_clicker_run_status = QLabel("Desligado")
        self.mouse_clicker_button = QPushButton("Ligar")
        self.mouse_clicker_button.setCheckable(True)
        self.mouse_clicker_button.setFixedWidth(90)
        self.mouse_clicker_button.clicked.connect(self.toggle_mouse_clicker)
        self.clicker_button.setFixedWidth(90)
        for mode, title, button, status, key, interval in (
            ("clicker", "Cookie principal", self.clicker_button, self.clicker_run_status,
             app_config.toggle_key, app_config.click_interval),
            ("mouse_clicker", "Na posição do mouse", self.mouse_clicker_button, self.mouse_clicker_run_status,
             app_config.mouse_toggle_key, app_config.mouse_click_interval),
        ):
            card = QGroupBox(title)
            card_layout = QVBoxLayout(card)
            header = QHBoxLayout()
            status.setStyleSheet("color: #9aa7ba;")
            header.addWidget(status)
            header.addStretch()
            header.addWidget(button)
            card_layout.addLayout(header)
            form = QFormLayout()
            form.setHorizontalSpacing(10)
            activation = ScrollSafeComboBox()
            activation.addItem("Alternar (Toggle)", "toggle")
            activation.addItem("Segurar (Hold)", "hold")
            activation.setCurrentIndex(activation.findData(getattr(app_config, mode + "_mode")))
            activation.setToolTip("Alternar: aperte o atalho para ligar e novamente para desligar. Segurar: clica enquanto o atalho estiver pressionado e para ao soltar. Cada clicker tem seu próprio modo, que fica salvo.")
            setattr(self, mode + "_mode_input", activation)
            activation.currentIndexChanged.connect(lambda index, name=mode: self.update_clicker_mode(name))
            form.addRow("Acionamento", activation)
            hotkey = HotkeyCapture(key)
            setattr(self, mode + "_hotkey_input", hotkey)
            hotkey.changed.connect(self.update_clicker_hotkey if mode == "clicker" else self.update_mouse_clicker_hotkey)
            hotkey.capturing_changed.connect(self._hotkey_capture_changed)
            form.addRow("Atalho", hotkey)
            speed = ScrollSafeSpinBox()
            speed.setRange(1, 1000)
            speed.setSuffix(" cliques/s")
            speed.setMaximumWidth(180)
            speed.setValue(round(1.0 / interval))
            speed.valueChanged.connect(self.update_clicker_speed if mode == "clicker" else self.update_mouse_clicker_speed)
            setattr(self, mode + "_speed_input", speed)
            form.addRow("Velocidade", speed)
            card_layout.addLayout(form)
            clicker_layout.addWidget(card, 1)
        layout.addWidget(self.clicker_group)
        self.set_clicker_state(False)
        self.set_mouse_clicker_state(False)
        layout.addStretch()
        return tab

    def _load_grimoire_spells(self):
        magias = self.bridge.get_grimoire_spells() if self.bridge else []
        if not magias:
            magias = [
                {"id": spell_id, "name": name, "description": ""}
                for spell_id, name in DEFAULT_GRIMOIRE_SPELLS
            ]
        self.grimoire_spell_combo.blockSignals(True)
        self.grimoire_spell_combo.clear()
        for spell in magias:
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
        self.log_text = QTextEdit(); self.log_text.setReadOnly(True); self.log_text.setMinimumHeight(230); hint = QLabel("Acompanhe as ações e os avisos do bot."); hint.setWordWrap(True); hint.setStyleSheet("color: #aeb8c9;"); group_layout.addWidget(hint); group_layout.addWidget(self.log_text); layout.addWidget(group); return tab

    def _garden_tab(self):
        """Cria a visão de progresso, planejamento e execução do Garden."""
        tab = QWidget()
        outer_layout = QVBoxLayout(tab)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self.garden_scroll = QScrollArea()
        self.garden_scroll.setWidgetResizable(True)
        self.garden_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.garden_scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        toolbar = QHBoxLayout()
        self.garden_status_label = QLabel("Garden: carregando")
        self.garden_status_label.setStyleSheet("color: #9aa7ba; font-weight: 600;")
        self.garden_progress_label = QLabel("Sementes: —")
        self.garden_refresh_button = QPushButton("Atualizar Garden")
        self.garden_refresh_button.clicked.connect(self.refresh_garden)
        self.garden_simulate_button = QPushButton("Ver próximas ações")
        self.garden_simulate_button.setObjectName("primaryButton")
        self.garden_simulate_button.clicked.connect(self.simulate_garden)
        self.garden_toggle = AutomationControl("Garden")
        self.garden_toggle.set_running(automation_config.enable_garden_automation)
        self.garden_toggle.setToolTip("Ligar inicia o Garden. Desligar encerra após a ação em andamento. A prévia não executa ações.")
        self.garden_toggle.requested.connect(self._toggle_garden_automation)
        self.garden_strategy_combo = ScrollSafeComboBox()
        self.garden_strategy_combo.setMinimumWidth(240)
        self.garden_strategy_combo.setMinimumHeight(34)
        self.garden_strategy_combo.setStyleSheet(
            "QComboBox { background: #202731; color: #e3e8ef; border: 1px solid #394759; "
            "border-radius: 5px; padding: 5px 10px; } "
            "QComboBox:disabled { color: #8792a2; } "
            "QComboBox QAbstractItemView { background: #202731; color: #e3e8ef; "
            "selection-background-color: #327bdb; }"
        )
        for key,label in GARDEN_STRATEGIES.items():
            self.garden_strategy_combo.addItem(label,key)
        index = self.garden_strategy_combo.findData(automation_config.garden_strategy)
        self.garden_strategy_combo.setCurrentIndex(max(0,index))
        self._update_garden_strategy_tooltip()
        self.garden_strategy_combo.currentIndexChanged.connect(self._change_garden_strategy)
        toolbar.addWidget(self.garden_status_label)
        toolbar.addWidget(self.garden_progress_label)
        toolbar.addStretch()
        toolbar.addWidget(self.garden_toggle)
        layout.addLayout(toolbar)
        actions = QHBoxLayout()
        actions.addWidget(self.garden_refresh_button)
        actions.addWidget(self.garden_simulate_button)
        actions.addStretch()
        layout.addLayout(actions)
        modes = QHBoxLayout()
        modes.addWidget(QLabel("Estratégia:"))
        modes.addWidget(self.garden_strategy_combo)
        modes.addStretch()
        layout.addLayout(modes)

        goal_group = QGroupBox("Objetivo atual"); goal_layout = QVBoxLayout(goal_group)
        self.garden_goal_label = QLabel("Aguardando leitura do Garden.")
        self.garden_goal_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #f4f7fc;")
        self.garden_parents_label = QLabel("Plantas necessárias: —")
        self.garden_reason_label = QLabel("")
        self.garden_reason_label.setStyleSheet("color: #9aa7ba;")
        goal_layout.addWidget(self.garden_goal_label)
        goal_layout.addWidget(self.garden_parents_label)
        self.garden_reason_label.hide()
        layout.addWidget(goal_group)

        state_group = QGroupBox("Agora"); state_layout = QVBoxLayout(state_group)
        self.garden_state_label = QLabel("Aguardando leitura")
        self.garden_state_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        self.garden_state_detail = QLabel("Consulte o Garden para acompanhar o plantio.")
        self.garden_feedback_label = QLabel("")
        self.garden_feedback_label.setStyleSheet("color: #9aa7ba;")
        state_layout.addWidget(self.garden_state_label)
        state_layout.addWidget(self.garden_state_detail)
        state_layout.addWidget(self.garden_feedback_label)
        layout.addWidget(state_group)

        self.garden_plan_group = QGroupBox("Próximas ações")
        plan_layout = QVBoxLayout(self.garden_plan_group)
        self.garden_plan_text = QTextEdit()
        self.garden_plan_text.setReadOnly(True)
        self.garden_plan_text.setFixedHeight(72)
        self.garden_plan_text.setStyleSheet("font-family: 'Segoe UI'; font-size: 12px;")
        self.garden_plan_text.setPlainText("Aguardando leitura do Garden.")
        self.garden_plan_text.setToolTip("Ações agrupadas por planta. Ações já confirmadas não aparecem como próximas.")
        self.garden_details_toggle = QCheckBox("Mostrar detalhes do último ciclo")
        self.garden_details_toggle.setToolTip("Mostra o motivo do plano, as posições e o resultado completo de cada ação.")
        self.garden_details_text = QTextEdit()
        self.garden_details_text.setReadOnly(True)
        self.garden_details_text.setMinimumHeight(180)
        self.garden_details_text.setMaximumHeight(240)
        self.garden_details_text.hide()
        self.garden_details_toggle.toggled.connect(self._toggle_garden_details)
        plan_layout.addWidget(self.garden_plan_text)
        plan_layout.addWidget(self.garden_details_toggle)
        plan_layout.addWidget(self.garden_details_text)
        layout.addWidget(self.garden_plan_group)
        for label in (self.garden_goal_label, self.garden_parents_label, self.garden_reason_label,
                      self.garden_state_label, self.garden_state_detail, self.garden_feedback_label):
            label.setWordWrap(True)
            label.setTextFormat(Qt.PlainText)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addStretch()
        self.garden_scroll.setWidget(content)
        outer_layout.addWidget(self.garden_scroll)
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
            "Farm contínuo: prepara e repete combos até você desligar ou atingir o limite de gastos. "
            "Pausa as outras automações e vende/recompra construções."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #e8b766; font-weight: 600;")
        layout.addWidget(warning)

        config_group = QGroupBox("Limites do farm")
        form = QFormLayout(config_group)
        self.combo_lumps_input = ScrollSafeSpinBox()
        self.combo_lumps_input.setRange(0, 10_000)
        self.combo_lumps_input.setValue(automation_config.combo_max_total_lumps)
        self.combo_lumps_input.setSuffix(" torrões")
        self.combo_lumps_input.setMaximumWidth(180)
        self.combo_lumps_input.setToolTip("Limite total desde que você liga o Combo. Inclui alinhamento, recargas finais e frenesi de açúcar. Não reinicia entre combos. Zero impede gastos e encerra a execução. Cada tentativa precisa de pelo menos um torrão.")
        self.combo_lumps_input.valueChanged.connect(self._save_combo_settings)
        form.addRow("Gastar no máximo nesta sessão", self.combo_lumps_input)
        self.combo_reserve_input = ScrollSafeDoubleSpinBox()
        self.combo_reserve_input.setRange(0, 99)
        self.combo_reserve_input.setDecimals(0)
        self.combo_reserve_input.setSuffix(" %")
        self.combo_reserve_input.setMaximumWidth(180)
        self.combo_reserve_input.setValue(automation_config.combo_cash_reserve_percent)
        self.combo_reserve_input.setToolTip("Parte do saldo protegida das compras do Combo. A reserva é calculada ao iniciar e aumenta a cada combo concluído. Se uma compra não couber, aguarda. Vendas e sacrifícios de construções continuam fazendo parte do combo.")
        self.combo_reserve_input.valueChanged.connect(self._save_combo_settings)
        form.addRow("Manter reservado em biscoitos", self.combo_reserve_input)
        self.combo_garden_checkbox = QCheckBox("Permitir preparar o Garden para o combo")
        self.combo_garden_checkbox.setChecked(automation_config.combo_convert_garden)
        self.combo_garden_checkbox.setToolTip("Desmarcado: não planta, não colhe e não troca o solo. Marcado: pode substituir culturas desbloqueadas por trevos e tulipas, ajustar o solo e retirar tulipas na finalização. Descobertas bloqueadas e plantas fora do catálogo nunca são removidas.")
        self.combo_garden_checkbox.toggled.connect(self._save_combo_settings)
        form.addRow("Garden", self.combo_garden_checkbox)
        layout.addWidget(config_group)

        self.combo_advanced_group = QGroupBox("Opções avançadas")
        self.combo_advanced_group.setCheckable(True)
        self.combo_advanced_group.setChecked(False)
        advanced_layout = QVBoxLayout(self.combo_advanced_group)
        self.combo_advanced_body = QWidget()
        form = QFormLayout(self.combo_advanced_body)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.combo_search_input = ScrollSafeSpinBox()
        self.combo_search_input.setRange(4, 100_000)
        self.combo_search_input.setValue(automation_config.combo_max_search_ahead)
        self.combo_search_input.setSuffix(" magias")
        self.combo_search_input.valueChanged.connect(self._save_combo_settings)
        form.addRow("Magias futuras analisadas", self.combo_search_input)

        self.combo_bs_input = ScrollSafeSpinBox()
        self.combo_bs_input.setRange(1, 6)
        self.combo_bs_input.setValue(automation_config.combo_required_building_specials)
        self.combo_bs_input.valueChanged.connect(self._save_combo_settings)
        form.addRow("Bônus de construções desejados", self.combo_bs_input)

        self.combo_interval_input = ScrollSafeDoubleSpinBox()
        self.combo_interval_input.setRange(0.1, 60.0)
        self.combo_interval_input.setDecimals(1)
        self.combo_interval_input.setValue(automation_config.combo_poll_interval_seconds)
        self.combo_interval_input.setSuffix(" s")
        self.combo_interval_input.valueChanged.connect(self._save_combo_settings)
        form.addRow("Intervalo de verificação", self.combo_interval_input)

        self.combo_min_buff_input = ScrollSafeDoubleSpinBox()
        self.combo_min_buff_input.setRange(5.0, 120.0)
        self.combo_min_buff_input.setDecimals(1)
        self.combo_min_buff_input.setValue(automation_config.combo_minimum_buff_seconds)
        self.combo_min_buff_input.setSuffix(" s")
        self.combo_min_buff_input.valueChanged.connect(self._save_combo_settings)
        form.addRow("Tempo mínimo restante dos bônus", self.combo_min_buff_input)

        self.combo_wait_input = ScrollSafeSpinBox()
        self.combo_wait_input.setRange(1, 1440)
        self.combo_wait_input.setValue(automation_config.combo_max_wait_minutes)
        self.combo_wait_input.setSuffix(" min")
        self.combo_wait_input.setToolTip(
            "Intervalo para renovar a busca quando não aparece uma oportunidade. O farm continua ligado, preservando o orçamento."
        )
        self.combo_wait_input.valueChanged.connect(self._save_combo_settings)
        form.addRow("Renovar busca a cada", self.combo_wait_input)

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

        self.combo_final_garden_checkbox = QCheckBox("Retirar penalidades das tulipas na finalização")
        self.combo_final_garden_checkbox.setChecked(automation_config.combo_optimize_final_garden)
        self.combo_final_garden_checkbox.setToolTip("Só se o Garden estiver autorizado e todo o canteiro contiver trevos e tulipas desbloqueados. Não remove outras culturas.")
        self.combo_final_garden_checkbox.toggled.connect(self._save_combo_settings)
        form.addRow("Garden na finalização", self.combo_final_garden_checkbox)
        boosts = QHBoxLayout()
        self.combo_sugar_checkbox = QCheckBox("Usar frenesi de açúcar quando disponível")
        self.combo_sugar_checkbox.setChecked(automation_config.combo_use_sugar_frenzy)
        self.combo_sugar_checkbox.stateChanged.connect(self._save_combo_settings)
        self.combo_loans_checkbox = QCheckBox("Usar os três empréstimos")
        self.combo_loans_checkbox.setChecked(automation_config.combo_use_loans)
        self.combo_loans_checkbox.stateChanged.connect(self._save_combo_settings)
        boosts.addWidget(self.combo_sugar_checkbox)
        boosts.addWidget(self.combo_loans_checkbox)
        boosts.addStretch()
        form.addRow("Multiplicadores finais", boosts)
        self.combo_pause_checkbox = QCheckBox("Pausar antes das últimas magias de preparação")
        self.combo_pause_checkbox.setChecked(automation_config.combo_pause_before_last_skips)
        self.combo_pause_checkbox.setToolTip(
            "Pausa antes dos últimos 3 avanços de cada combo (ou menos). "
            "Enquanto aguarda, nenhuma ação no jogo é executada pelo bot."
        )
        self.combo_pause_checkbox.stateChanged.connect(self._save_combo_settings)
        form.addRow("Acompanhar tentativa", self.combo_pause_checkbox)
        advanced_layout.addWidget(self.combo_advanced_body)
        self.combo_advanced_body.setVisible(False)
        self.combo_advanced_group.toggled.connect(self.combo_advanced_body.setVisible)
        layout.addWidget(self.combo_advanced_group)

        status_group = QGroupBox("Acompanhamento")
        status_form = QFormLayout(status_group)
        self.combo_state_label = QLabel("Não iniciado")
        self.combo_plan_label = QLabel("Atualize a prévia para ver a próxima oportunidade.")
        self.combo_progress_label = QLabel("Magias usadas: — | Mana: — | Sugar Lumps: —")
        self.combo_buffs_label = QLabel("—")
        self.combo_garden_label = QLabel("Garden: —")
        self.combo_message_label = QLabel("Nenhuma ação executada.")
        self.combo_error_label = QLabel("—")
        for label in (
            self.combo_plan_label, self.combo_buffs_label, self.combo_message_label,
            self.combo_error_label,
        ):
            label.setWordWrap(True)
        status_form.addRow("Estado", self.combo_state_label)
        status_form.addRow("Combo previsto", self.combo_plan_label)
        status_form.addRow("Recursos", self.combo_progress_label)
        status_form.addRow("Bônus ativos", self.combo_buffs_label)
        status_form.addRow("Garden", self.combo_garden_label)
        status_form.addRow("Mensagem", self.combo_message_label)
        status_form.addRow("Aviso", self.combo_error_label)
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
        self.combo_mode_tabs.addTab(scroll, "Combo avançado")
        self.combo_planner = ComboPlanner(
            lambda: self.bridge if not self._save_scum_exclusive and not self._connection_recovering else None,
            self,
        )
        self.combo_mode_tabs.addTab(self.combo_planner, "Planejador")
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
            "Acumula cookies junto com Garden e Banco, respeitando a reserva de caixa escolhida."
        )
        guarantee.setWordWrap(True)
        guarantee.setStyleSheet("color: #65d6a5; font-weight: 600;")
        layout.addWidget(guarantee)

        config_group = QGroupBox("Estratégia automática")
        form = QFormLayout(config_group)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.simple_farm_search_input = ScrollSafeSpinBox()
        self.simple_farm_search_input.setRange(2, 10_000)
        self.simple_farm_search_input.setValue(automation_config.simple_farm_max_search_ahead)
        self.simple_farm_search_input.setSuffix(" magias")
        self.simple_farm_search_input.valueChanged.connect(self._save_simple_farm_settings)
        form.addRow("Magias futuras analisadas", self.simple_farm_search_input)
        self.simple_farm_interval_input = ScrollSafeDoubleSpinBox()
        self.simple_farm_interval_input.setRange(0.1, 10.0)
        self.simple_farm_interval_input.setDecimals(1)
        self.simple_farm_interval_input.setSingleStep(0.1)
        self.simple_farm_interval_input.setValue(automation_config.simple_farm_poll_interval_seconds)
        self.simple_farm_interval_input.setSuffix(" s")
        self.simple_farm_interval_input.valueChanged.connect(self._save_simple_farm_settings)
        form.addRow("Intervalo de verificação", self.simple_farm_interval_input)
        self.simple_farm_min_buff_input = ScrollSafeDoubleSpinBox()
        self.simple_farm_min_buff_input.setRange(3.0, 60.0)
        self.simple_farm_min_buff_input.setDecimals(1)
        self.simple_farm_min_buff_input.setValue(automation_config.simple_farm_minimum_buff_seconds)
        self.simple_farm_min_buff_input.setSuffix(" s")
        self.simple_farm_min_buff_input.valueChanged.connect(self._save_simple_farm_settings)
        form.addRow("Tempo mínimo restante do bônus", self.simple_farm_min_buff_input)
        self.simple_farm_reserve_input = ScrollSafeDoubleSpinBox()
        self.simple_farm_reserve_input.setRange(15.0, 99.0)
        self.simple_farm_reserve_input.setDecimals(0)
        self.simple_farm_reserve_input.setValue(automation_config.simple_farm_cash_reserve_percent)
        self.simple_farm_reserve_input.setSuffix(" %")
        self.simple_farm_reserve_input.valueChanged.connect(self._save_simple_farm_settings)
        form.addRow("Reserva mínima de caixa", self.simple_farm_reserve_input)
        self.simple_farm_investment_input = ScrollSafeDoubleSpinBox()
        self.simple_farm_investment_input.setRange(1.0, 20.0)
        self.simple_farm_investment_input.setDecimals(0)
        self.simple_farm_investment_input.setValue(automation_config.simple_farm_investment_percent)
        self.simple_farm_investment_input.setSuffix(" %")
        self.simple_farm_investment_input.valueChanged.connect(self._save_simple_farm_settings)
        form.addRow("Compra máxima a cada 15 s", self.simple_farm_investment_input)
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
        self.simple_farm_plan_label = QLabel("Atualize a prévia para ver a próxima oportunidade.")
        self.simple_farm_resources_label = QLabel("Magias usadas: — | Mana: — | Cookies: —")
        self.simple_farm_buffs_label = QLabel("—")
        self.simple_farm_counter_label = QLabel("Golden Cookies: 0 | Magias: 0")
        self.simple_farm_pantheon_label = QLabel("—")
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
        status_form.addRow("Bônus ativos", self.simple_farm_buffs_label)
        status_form.addRow("Contadores", self.simple_farm_counter_label)
        status_form.addRow("Pantheon", self.simple_farm_pantheon_label)
        status_form.addRow("Mensagem", self.simple_farm_message_label)
        status_form.addRow("Aviso", self.simple_farm_error_label)
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
        automation_config.combo_convert_garden = self.combo_garden_checkbox.isChecked()
        automation_config.combo_optimize_final_garden = self.combo_final_garden_checkbox.isChecked()
        automation_config.combo_cash_reserve_percent = self.combo_reserve_input.value()
        automation_config.combo_max_total_lumps = self.combo_lumps_input.value()
        automation_config.combo_max_search_ahead = self.combo_search_input.value()
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
        if not self._bot_enabled:
            self.add_log("Ligue o bot no topo antes de iniciar automações.")
            return
        if not self.bridge or not self.runner:
            self._simple_farm_failed("Bridge ou runner não está disponível.")
            return
        if self._combo_worker and self._combo_worker.isRunning():
            return
        if self._auto_ascension_worker and self._auto_ascension_worker.isRunning():
            self._simple_farm_failed("Aguarde a Auto Ascensão terminar antes de iniciar o farm.")
            return
        if not self.runner.acquire_simple_farm():
            self._simple_farm_failed("Outra automação controla o Grimoire ou está em automação em andamento.")
            return
        try:
            save_data = self.bridge.get_game_save()
            if not save_data:
                self._abort_simple_farm_start("Não foi possível exportar o save de segurança.")
                return
            backup = self.backup_manager.create_backup(save_data, "antes-do-simple-farm")
            logger.debug("Backup de segurança preparado: %s", backup.display_name)
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
        self.simple_farm_state_label.setText(self._automation_state_text(value.estado.value))
        opportunity = value.plano.resumo if value.plano else "—"
        self.simple_farm_plan_label.setText(opportunity)
        self.simple_farm_plan_label.setToolTip(value.plano.decisao if value.plano else "")
        mana = "—" if value.mana is None else f"{value.mana:.1f}/{value.mana_maxima:.1f}"
        self.simple_farm_resources_label.setText(
            f"Combos: {value.ciclos_concluidos} | Magias usadas: {value.cast_atual if value.cast_atual is not None else '—'} | "
            f"Mana: {mana} | Cookies: {self._format_number(value.cookies_no_banco)} | "
            f"Caixa protegido: {self._format_number(value.caixa_reservado)}"
        )
        self.simple_farm_buffs_label.setText(
            ", ".join(value.buffs_ativos) if value.buffs_ativos else "nenhum"
        )
        self.simple_farm_counter_label.setText(
            f"Golden Cookies: {value.golden_cookies_coletados} | Magias: {value.magias_executadas} | "
            f"Upgrades: {value.upgrades_comprados} | Construções: {value.construcoes_compradas}"
        )
        slots = value.pantheon_slots
        gods = ("Holobore", "Vomitrax", "Godzamok", "Cyclius", "Selebrak", "Dotjeiess",
                "Muridal", "Jeremy", "Mokalsium", "Skruuia", "Rigidel")
        pantheon = " / ".join(gods[slot] if 0 <= slot < len(gods) else "Vazio" for slot in slots) if slots else "—"
        self.simple_farm_pantheon_label.setText(pantheon)
        self.simple_farm_message_label.setText(
            value.mensagem + (f" Próximo: {value.proximo_passo}" if value.proximo_passo else "")
        )
        self.simple_farm_error_label.setText(value.erro or "—")
        self.simple_farm_error_label.setStyleSheet(
            f"color: {'#f07883' if value.erro else '#9aa7ba'};"
        )

    def _simple_farm_failed(self, message: str):
        self.simple_farm_state_label.setText("Parada por segurança")
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

        self.refresh_bot_control()

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
            permitir_converter_garden=automation_config.combo_convert_garden,
            otimizar_garden_final=automation_config.combo_optimize_final_garden,
            cliques_por_segundo=min(1000, max(1, 1 / app_config.click_interval)),
            busca_maxima_spells=self.combo_search_input.value(),
            maximo_lumps_total=self.combo_lumps_input.value(),
            reserva_caixa_percentual=self.combo_reserve_input.value(),
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
        if not self._bot_enabled:
            self.add_log("Ligue o bot no topo antes de iniciar automações.")
            return
        if not self.bridge or not self.runner:
            self._combo_failed("Bridge ou runner não está disponível.")
            return
        if self._combo_worker and self._combo_worker.isRunning():
            return
        answer = QMessageBox.question(
            self,
            "Iniciar modo Combo",
            "O modo Combo pausará as outras automações e poderá gastar até "
            f"{self.combo_lumps_input.value()} torrões no total desta sessão. "
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
        if not self._bot_enabled:
            self.add_log("Ligue o bot no topo antes de iniciar automações.")
            return
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
        self.combo_state_label.setText(self._automation_state_text(value.estado.value))
        self.combo_resume_button.setEnabled(
            value.estado == EstadoCombo.PAUSADO
            and self._combo_worker is not None
            and self._combo_worker.isRunning()
        )
        self.combo_plan_label.setText(value.plano.resumo if value.plano else "—")
        mana = "—" if value.mana is None else f"{value.mana:.1f}/{value.mana_maxima:.1f}"
        self.combo_progress_label.setText(
            f"Combos: {value.ciclos_concluidos} | Magias usadas: {value.cast_atual if value.cast_atual is not None else '—'} | "
            f"Mana: {mana} | Sugar Lumps: {value.lumps if value.lumps is not None else '—'} "
            f"(gastos: {value.lumps_gastos}) | Cookies: {self._format_number(value.cookies_assados)}"
        )
        self.combo_buffs_label.setText(
            (", ".join(value.buffs_ativos) if value.buffs_ativos else "nenhum")
            + f" | Bônus de construções: {value.building_specials_ativos}"
        )
        self.combo_garden_label.setText(
            "Preservado: nenhuma alteração autorizada." if not self.combo_garden_checkbox.isChecked()
            else f"Plantas maduras: {value.garden_maduras}/{value.garden_total}"
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

        self.refresh_bot_control()

    def _set_combo_busy(self, busy: bool, preview: bool):
        for widget in (
            self.combo_garden_checkbox, self.combo_reserve_input, self.combo_advanced_group,
            self.combo_final_garden_checkbox,
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
                self.clicker_button, self.mouse_clicker_button, self.golden_checkbox, self.fortune_checkbox,
                self.reindeer_checkbox, self.wrinkler_checkbox,
                self.grimoire_spell_spam_checkbox, self.sugar_lump_checkbox, self.krumblor_checkbox,
                self.auto_season_checkbox, self.auto_season_combo,
                self.garden_strategy_combo,
                self.auto_ascension_toggle,
            ):
                widget.setEnabled(not busy)

    def _acquire_save_scum(self, owner="save_scum", error_handler=None):
        report_error = error_handler or self.save_scum_tab.display_error
        label = "Save Scum" if owner == "save_scum" else "Backups"
        if not self.bridge or not self.runner:
            report_error("Bridge ou runner indisponível.")
            return False
        if self._save_scum_exclusive:
            report_error("Restaure o início antes de iniciar outra sessão.")
            return False
        if any(worker and worker.isRunning() for worker in (self._combo_worker, self._auto_ascension_worker)):
            report_error("Desligue Simple Farm, Combo e Auto Ascensão antes de iniciar Save Scum.")
            return False
        self._save_scum_resume_clicker = self.runner.is_running
        if not self.runner.acquire_exclusive(owner):
            report_error("Outra automação mantém o controle exclusivo do jogo.")
            return False
        self._exclusive_session_owner = owner
        self._save_scum_exclusive = True
        self.stock_refresh_timer.stop()
        self.garden_refresh_timer.stop()
        for worker in (self._stock_worker, self._garden_worker):
            if worker and worker.isRunning() and not worker.wait((app_config.connection_timeout + 1) * 1000):
                self._release_save_scum()
                report_error("A operação do Garden/Banco ainda não terminou. Tente novamente.")
                return False
        widgets = (self.clicker_button, self.mouse_clicker_button, self.backups_button, self.golden_checkbox, self.fortune_checkbox,
                   self.reindeer_checkbox, self.wrinkler_checkbox, self.grimoire_spell_spam_checkbox,
                   self.sugar_lump_checkbox, self.krumblor_checkbox, self.auto_season_checkbox,
                   self.auto_season_combo, self.stock_toggle, self.garden_toggle,
                   self.combo_toggle, self.combo_preview_button, self.simple_farm_toggle,
                   self.simple_farm_preview_button, self.auto_ascension_toggle, self.auto_ascension_preview_button,
                   *self._preserve_checkboxes, self.save_scum_tab.toggle, self.save_scum_tab.preview)
        self._save_scum_disabled_widgets = [(w, w.isEnabled()) for w in widgets]
        for widget, _ in self._save_scum_disabled_widgets:
            widget.setEnabled(False)
        self.stock_toggle.set_paused(True, label)
        self.garden_toggle.set_paused(True, label)
        return True

    def _release_save_scum(self):
        if not self._save_scum_exclusive:
            return
        self.runner.release_exclusive(self._exclusive_session_owner)
        self._save_scum_exclusive = False
        for widget, enabled in self._save_scum_disabled_widgets:
            widget.setEnabled(enabled)
        self._save_scum_disabled_widgets = []
        self.stock_toggle.set_paused(False)
        self.garden_toggle.set_paused(False)
        if self.bridge:
            self.stock_automation = StockMarketAutomation(self.bridge)
            self.fazendeira = Fazendeira(self.bridge)
            self._stock_snapshot = None
            self.stock_refresh_timer.start(5000)
            QTimer.singleShot(0, self.refresh_garden)
            QTimer.singleShot(0, self._on_stock_market_timer)
        if self._save_scum_resume_clicker and self._bot_enabled:
            self.runner.ensure_clicker_running()
        self._save_scum_resume_clicker = False
        self._exclusive_session_owner = "save_scum"
        self._backup_recovery_pending = False

        self.refresh_bot_control()

    def _auto_ascension_tab(self):
        """Cria os controles e o relatório da máquina de Auto Ascensão."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        warning = QLabel(
            "Comece na tela de ascensão. A automação compra melhorias e repete as ascensões escolhidas."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #e8b766; font-weight: 600;")
        layout.addWidget(warning)

        config_group = QGroupBox("Ascensões")
        form = QFormLayout(config_group)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.auto_ascension_cycles_input = ScrollSafeSpinBox()
        self.auto_ascension_cycles_input.setRange(1, 10_000)
        self.auto_ascension_cycles_input.setValue(automation_config.auto_ascension_target_cycles)
        self.auto_ascension_cycles_input.valueChanged.connect(self._save_auto_ascension_settings)
        form.addRow("Quantidade de ascensões", self.auto_ascension_cycles_input)

        self.auto_ascension_prestige_input = ScrollSafeDoubleSpinBox()
        self.auto_ascension_prestige_input.setRange(0.0, 1e300)
        self.auto_ascension_prestige_input.setDecimals(0)
        self.auto_ascension_prestige_input.setValue(
            automation_config.auto_ascension_minimum_prestige_gain
        )
        self.auto_ascension_prestige_input.valueChanged.connect(self._save_auto_ascension_settings)
        form.addRow("Ganho mínimo de prestígio", self.auto_ascension_prestige_input)

        self.auto_ascension_interval_input = ScrollSafeDoubleSpinBox()
        self.auto_ascension_interval_input.setRange(0.1, 3600.0)
        self.auto_ascension_interval_input.setDecimals(1)
        self.auto_ascension_interval_input.setSingleStep(0.1)
        self.auto_ascension_interval_input.setSuffix(" s")
        self.auto_ascension_interval_input.setValue(
            automation_config.auto_ascension_poll_interval_seconds
        )
        self.auto_ascension_interval_input.valueChanged.connect(self._save_auto_ascension_settings)
        form.addRow("Intervalo de verificação", self.auto_ascension_interval_input)

        self.auto_ascension_timeout_input = ScrollSafeSpinBox()
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
        status_form.addRow("Estado", self.auto_ascension_state_label)
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
        if not self._bot_enabled:
            self.add_log("Ligue o bot no topo antes de iniciar automações.")
            return
        """Liga a automação; a prévia tem um botão independente."""
        if self._combo_exclusive or self._save_scum_exclusive or self._simple_farm_automation is not None:
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
            "A automação pode comprar itens, reincarnar e ascender. "
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
        self.auto_ascension_state_label.setText(self._automation_state_text(value.estado.value))
        self.auto_ascension_cycle_label.setText(f"{value.ciclo_atual} / {value.ciclos_alvo}")
        self.auto_ascension_last_action_label.setText(value.ultima_acao)
        self.auto_ascension_next_step_label.setText(value.proximo_passo)
        self.auto_ascension_stop_reason_label.setText(value.motivo_parada or "—")
        color = "#f07883" if value.motivo_parada and value.estado.value != "Concluído" else "#65d6a5"
        self.auto_ascension_state_label.setStyleSheet(f"color: {color}; font-weight: 700;")

    def _auto_ascension_failed(self, message: str):
        self.auto_ascension_state_label.setText("Parada por segurança")
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

        self.refresh_bot_control()

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
        self.wrinkler_free_slots_input = ScrollSafeSpinBox()
        self.wrinkler_free_slots_input.setRange(1, 12)
        self.wrinkler_free_slots_input.setMaximumWidth(140)
        self.wrinkler_free_slots_input.setValue(automation_config.wrinkler_free_slots)
        self.wrinkler_free_slots_input.setToolTip(
            "Mínimo de vagas para novos Wrinklers. Uma vaga mantém mais normais rendendo; "
            "Mais vagas renovam mais Wrinklers para procurar Shiny, reduzindo o rendimento. "
            "Aceita de 1 a 12, limitado pela capacidade atual do jogo. "
            "Abre vagas coletando os normais com menos cookies. Shiny nunca são coletados. "
            "Pode coletar os maiores para destravar Garden/Banco sem dinheiro, mantendo um normal rendendo.")
        self.wrinkler_free_slots_input.valueChanged.connect(self.update_wrinkler_free_slots)
        self.wrinkler_free_slots_input.setEnabled(automation_config.enable_wrinkler_popper)
        automation_form.addRow("Vagas mínimas para Shiny", self.wrinkler_free_slots_input)
        self.grimoire_spell_combo = ScrollSafeComboBox()
        self._load_grimoire_spells()
        self.grimoire_spell_combo.currentIndexChanged.connect(self.update_grimoire_spell)
        self.grimoire_spell_combo.setEnabled(automation_config.enable_grimoire_spell_spam)
        automation_form.addRow("Magia automática do Grimoire", self.grimoire_spell_combo)
        self.krumblor_interval_input = ScrollSafeDoubleSpinBox()
        self.krumblor_interval_input.setRange(0.05, 5.0)
        self.krumblor_interval_input.setDecimals(2)
        self.krumblor_interval_input.setSingleStep(0.05)
        self.krumblor_interval_input.setSuffix(" s")
        self.krumblor_interval_input.setMaximumWidth(140)
        self.krumblor_interval_input.setValue(automation_config.krumblor_pet_interval_seconds)
        self.krumblor_interval_input.setToolTip("Tempo mínimo entre carinhos. Um valor menor tenta liberar o upgrade mais rápido. Após liberá-lo, aguarda a próxima faixa de 15 minutos.")
        self.krumblor_interval_input.valueChanged.connect(self.update_krumblor_interval)
        automation_form.addRow("Intervalo entre carinhos no Krumblor", self.krumblor_interval_input)
        self.auto_season_combo = ScrollSafeComboBox()
        for key, label in SEASONS.items():
            self.auto_season_combo.addItem(label, key)
        self.auto_season_combo.setCurrentIndex(self.auto_season_combo.findData(automation_config.auto_season))
        self.auto_season_combo.setToolTip("Temporada mantida pela opção Manter temporada ativa. Ao trocar a seleção com a automação ligada, a nova temporada será ativada na próxima verificação. Sem saldo, aguarda sem comprar.")
        self.auto_season_combo.currentIndexChanged.connect(self.update_auto_season)
        automation_form.addRow("Temporada automática", self.auto_season_combo)
        for combo in (self.grimoire_spell_combo, self.auto_season_combo):
            combo.setFixedWidth(260)
            combo.setMinimumHeight(30)
            combo.setStyleSheet(
                "QComboBox { background: #171b21; border: 1px solid #37404e; "
                "border-radius: 6px; padding: 4px 26px 4px 8px; }"
                "QComboBox:hover, QComboBox:focus { border-color: #5799ef; }"
                "QComboBox:disabled { color: #778093; background: #20242b; }"
                "QComboBox::drop-down { width: 24px; border: none; }"
                "QComboBox QAbstractItemView { background: #20252e; "
                "selection-background-color: #2d5f9f; border: 1px solid #37404e; }"
            )
        layout.addWidget(automation_group)

        sugar_group = QGroupBox("Sugar Lumps"); sugar_form = QFormLayout(sugar_group)
        preserve_grid = QGridLayout(); entries = (("Normal", 0), ("Bifurcado", 1), ("Dourado", 2), ("Carnudo", 3), ("Caramelizado", 4)); self._preserve_checkboxes = []
        for index, (text, number) in enumerate(entries):
            checkbox = QCheckBox(text); checkbox.setChecked(getattr(automation_config, f"preserve_sugar_lump_type_{number}")); checkbox.stateChanged.connect(lambda state, n=number: self._set_sugar_lump_type(n, state)); preserve_grid.addWidget(checkbox, index // 3, index % 3); self._preserve_checkboxes.append(checkbox)
        for checkbox in self._preserve_checkboxes:
            checkbox.setToolTip("Para este tipo, aguarda a colheita com rendimento garantido. Os tipos desmarcados são colhidos mais cedo, com 50% de chance de não render Sugar Lumps.")
        sugar_form.addRow("Aguardar colheita garantida", preserve_grid)
        layout.addWidget(sugar_group)
        self.set_sugar_lump_preserve_enabled(automation_config.enable_sugar_lump_harvest)

        stock_group = QGroupBox("Stock Market"); stock_form = QFormLayout(stock_group)
        stock_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.stock_buy_limit_input = ScrollSafeDoubleSpinBox(); self.stock_buy_limit_input.setRange(0.01, 1_000_000_000.0); self.stock_buy_limit_input.setDecimals(2); self.stock_buy_limit_input.setPrefix("$ "); self.stock_buy_limit_input.setMaximumWidth(150); self.stock_buy_limit_input.setValue(automation_config.stock_market_buy_price_limit); self.stock_buy_limit_input.valueChanged.connect(self._update_stock_buy_limit)
        stock_form.addRow("Limite geral de compra", self.stock_buy_limit_input)
        self.stock_sell_limit_input = ScrollSafeDoubleSpinBox(); self.stock_sell_limit_input.setRange(0.01, 1_000_000_000.0); self.stock_sell_limit_input.setDecimals(2); self.stock_sell_limit_input.setPrefix("$ "); self.stock_sell_limit_input.setMaximumWidth(150); self.stock_sell_limit_input.setValue(automation_config.stock_market_sell_price_limit); self.stock_sell_limit_input.valueChanged.connect(self._update_stock_sell_limit)
        stock_form.addRow("Limite geral de venda", self.stock_sell_limit_input)
        self.stock_trend_ticks_input = ScrollSafeSpinBox(); self.stock_trend_ticks_input.setRange(2, 64); self.stock_trend_ticks_input.setSuffix(" ticks"); self.stock_trend_ticks_input.setMaximumWidth(120); self.stock_trend_ticks_input.setValue(automation_config.stock_market_trend_ticks); self.stock_trend_ticks_input.setToolTip("Quantidade de atualizações de preço usadas para identificar se um ativo está subindo ou caindo."); self.stock_trend_ticks_input.valueChanged.connect(self._update_stock_trend_ticks)
        stock_form.addRow("Histórico de preços analisado", self.stock_trend_ticks_input)
        self.stock_reversal_percent_input = ScrollSafeDoubleSpinBox(); self.stock_reversal_percent_input.setRange(0.01, 100.0); self.stock_reversal_percent_input.setDecimals(2); self.stock_reversal_percent_input.setSuffix(" %"); self.stock_reversal_percent_input.setMaximumWidth(120); self.stock_reversal_percent_input.setValue(automation_config.stock_market_reversal_percent); self.stock_reversal_percent_input.setToolTip("Quanto o preço precisa subir em uma atualização para confirmar uma recuperação após uma queda."); self.stock_reversal_percent_input.valueChanged.connect(self._update_stock_reversal_percent)
        stock_form.addRow("Alta mínima após uma queda", self.stock_reversal_percent_input)
        self.stock_owned_only_checkbox = QCheckBox("Mostrar no jogo apenas ativos em estoque")
        self.stock_owned_only_checkbox.setChecked(automation_config.enable_stock_market_owned_only_view)
        self.stock_owned_only_checkbox.stateChanged.connect(self._toggle_stock_owned_only_view)
        stock_form.addRow("Visualização no jogo", self.stock_owned_only_checkbox)
        self.stock_limits_button = QPushButton("Configurar limites por ativo")
        self.stock_limits_button.clicked.connect(self._configure_stock_limits)
        self.stock_limits_button.setEnabled(False)
        stock_form.addRow("Limites por ativo", self.stock_limits_button)
        self.stock_limits_button.setToolTip("Defina os preços para cada ativo. As compras aguardam uma recuperação; as vendas precisam dar lucro e podem ocorrer após uma queda de 10% do maior preço observado.")
        layout.addWidget(stock_group)

        garden_group = QGroupBox("Garden"); garden_form = QFormLayout(garden_group)
        garden_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.garden_interval_input = ScrollSafeSpinBox(); self.garden_interval_input.setRange(30, 3600); self.garden_interval_input.setSuffix(" s"); self.garden_interval_input.setMaximumWidth(140)
        self.garden_interval_input.setValue(automation_config.garden_poll_interval_seconds)
        self.garden_interval_input.setToolTip("Tempo entre consultas quando não for possível saber quando as plantas vão crescer novamente.")
        self.garden_interval_input.valueChanged.connect(self._update_garden_interval)
        garden_form.addRow("Intervalo alternativo de consulta", self.garden_interval_input)
        self.garden_interval_input.setToolTip(self.garden_interval_input.toolTip() + " As ações normalmente acompanham o crescimento das plantas.")
        layout.addWidget(garden_group)

        interface_group = QGroupBox("Interface"); interface_layout = QHBoxLayout(interface_group)
        interface_layout.addWidget(QLabel("Máximo de linhas no registro")); interface_layout.addStretch()
        self.log_limit_input = ScrollSafeSpinBox(); self.log_limit_input.setRange(1, 100000); self.log_limit_input.setValue(app_config.max_log_lines); self.log_limit_input.setToolTip("Limita apenas o histórico exibido na aba Atividade"); self.log_limit_input.valueChanged.connect(self.update_log_limit)
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
        self.stock_toggle = AutomationControl("Stock Market")
        self.stock_toggle.set_running(automation_config.enable_stock_market_auto_trade)
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
        self.stock_quantity_input = ScrollSafeSpinBox(); self.stock_quantity_input.setRange(1, 9_999); self.stock_quantity_input.setValue(1)
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
        if self._combo_exclusive or self._save_scum_exclusive:
            return
        if not self.bridge:
            self._show_stock_unavailable("Jogo desconectado. Abra o jogo e aguarde a conexão.")
            logger.warning("Stock Market: bridge não está disponível para atualização")
            return
        if not automatic:
            logger.info("Stock Market: atualização manual solicitada")
        operation = self.stock_automation.capture_snapshot if self.stock_automation else self.bridge.get_stock_market_snapshot
        self._run_stock_task(operation, self._display_stock_snapshot)

    def _on_stock_market_timer(self):
        """Atualiza o snapshot a cada 5 segundos e aplica a regra somente se autorizada."""
        if self._combo_exclusive or self._save_scum_exclusive:
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
        execute_orders = self._bot_enabled and self.stock_toggle.running and not stop_event.is_set()
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
        if enabled and not self._bot_enabled:
            self.add_log("Ligue o bot no topo antes de iniciar automações.")
            return
        if enabled:
            if self._combo_exclusive or self._save_scum_exclusive or not self.bridge or not self.stock_automation:
                self._show_stock_feedback(False, "Não foi possível ligar: conecte o jogo e aguarde o Combo terminar.")
                return
            self._stock_stop = threading.Event()
            self.stock_toggle.set_running(True)
            QTimer.singleShot(0, self._on_stock_market_timer)
        else:
            if self.runner:
                self.runner.request_wrinkler_cash("Banco")
            self._stock_stop.set()
            if self._stock_worker and self._stock_worker.isRunning():
                self.stock_toggle.set_stopping()
            else:
                self.stock_toggle.set_running(False)
        automation_config.enable_stock_market_auto_trade = bool(enabled)
        save_automation_settings()
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
        if self._combo_exclusive or self._save_scum_exclusive:
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
        if self._connection_recovering or (self.bridge and self.bridge.connected is False):
            return
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
        if self._connection_recovering or (self.bridge and self.bridge.connected is False):
            self._show_stock_feedback(False, "Conexão perdida. Automação aguardando reconexão.")
            return
        if self.stock_toggle.running:
            self._toggle_stock_auto_trade(False)
        logger.error(f"Stock Market: não foi possível concluir a operação: {message}")
        self._show_stock_feedback(False, f"Falha inesperada: {message}")

    def _stock_task_finished(self):
        self._stock_worker = None
        if self.stock_toggle.stopping:
            self.stock_toggle.set_running(False)
        self._set_stock_busy(False)
        if self._refresh_after_order:
            self._refresh_after_order = False
            QTimer.singleShot(0, self.refresh_stock_market)

        self.refresh_bot_control()

    def _display_stock_snapshot(self, value: object):
        if not isinstance(value, StockMarketSnapshot):
            self._show_stock_unavailable("Resposta inesperada do bridge")
            logger.error("Stock Market: não foi possível ler os preços.")
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
            self.stock_candidates_label.setText("")
            self._show_stock_feedback(False, snapshot.status.message)
            self.stock_table.setSortingEnabled(True)
            self._update_stock_actions()
            return
        total_profit = self.stock_automation.total_profit(snapshot) if self.stock_automation else None
        self.stock_total_profit_label.setText(self._format_stock_total_profit(total_profit))
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
                    item.setToolTip(f"Comprar abaixo de ${buy_limit:.2f} | Preço de referência para vender: ${sell_limit:.2f}")
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
        if self._combo_exclusive or self._save_scum_exclusive:
            return
        if not self.fazendeira:
            self._show_garden_feedback(False, "Bridge não está disponível.")
            return
        strategy = self.garden_strategy_combo.currentData()
        self._run_garden_task(
            lambda: self.fazendeira.run_cycle(
                dry_run=True,
                automation_enabled=False,
                strategy=strategy,
            ),
            self._display_garden_result,
        )

    def simulate_garden(self, _checked: bool = False):
        """Executa somente a leitura e o planejamento da Fazendeira."""
        if self._combo_exclusive or self._save_scum_exclusive:
            return
        if not self.fazendeira:
            self._show_garden_feedback(False, "Bridge não está disponível.")
            return
        logger.info("Garden: simulação solicitada; nenhuma ação será enviada ao jogo")
        strategy = self.garden_strategy_combo.currentData()
        self._run_garden_task(
            lambda: self.fazendeira.run_cycle(
                dry_run=True,
                automation_enabled=False,
                strategy=strategy,
            ),
            self._display_garden_result,
        )

    def _on_garden_timer(self):
        if self._combo_exclusive or self._save_scum_exclusive:
            return
        if not self.fazendeira or (self._garden_worker and self._garden_worker.isRunning()):
            return
        self._garden_run_when_idle = False
        stop_event = self._garden_stop
        enabled = self._bot_enabled and self.garden_toggle.running and not stop_event.is_set()
        strategy = self.garden_strategy_combo.currentData()
        self._run_garden_task(
            lambda: self.fazendeira.run_cycle(
                dry_run=not enabled, automation_enabled=enabled,
                strategy=strategy,
                should_stop=stop_event.is_set,
            ),
            self._display_garden_result,
        )

    def _run_garden_task(self, operation: Callable[[], object], handler: Callable[[object], None]):
        if self._connection_recovering or (self.bridge and self.bridge.connected is False):
            return
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
        if self._connection_recovering or (self.bridge and self.bridge.connected is False):
            self._show_garden_feedback(False, "Conexão perdida. Automação aguardando reconexão.")
            return
        if self.garden_toggle.running:
            self._toggle_garden_automation(False)
        logger.error(f"Garden: não foi possível concluir a operação: {message}")
        self._show_garden_feedback(False, f"Falha inesperada: {message}")
        self._schedule_next_garden_tick(None)

    def _garden_task_finished(self):
        self._garden_worker = None
        if self.garden_toggle.stopping:
            self.garden_toggle.set_running(False)
        self._set_garden_busy(False)
        if self._garden_run_when_idle and self.garden_toggle.running:
            QTimer.singleShot(0, self._on_garden_timer)

        self.refresh_bot_control()

    def _display_garden_result(self, value: object):
        if not isinstance(value, GardenCycleResult):
            self._show_garden_feedback(False, "Resposta inesperada do ciclo do Garden.")
            logger.error("Garden: não foi possível confirmar o resultado da operação.")
            return
        if self.runner:
            waits = [r.required_cookies for r in value.action_results
                     if r.waiting and r.reason == "insufficient_funds" and r.required_cookies]
            target = max(waits, default=0) if (not value.dry_run and self._bot_enabled
                       and self.garden_toggle.running and not self._garden_stop.is_set()) else 0
            self.runner.request_wrinkler_cash("Garden", target, value.snapshot.game_seed, ttl=600)
        snapshot, plan = value.snapshot, value.plan
        objective_completed = plan.completed and self.garden_strategy_combo.currentData() == (plan.mode or 'plants')
        if objective_completed and self.garden_toggle.running:
            self._toggle_garden_automation(False)
            logger.info("Garden: objetivo de %s concluído; automação desligada.",self.garden_strategy_combo.currentText())
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
            f"Upgrades: {sum(u.obtained for u in snapshot.upgrades)}/{len(snapshot.upgrades)}"
            if plan.mode == 'garden_upgrades' and snapshot.upgrades else
            f"Sementes: {unlocked}/{len(snapshot.seeds)}" if snapshot.seeds else "Sementes: —"
        )
        if not snapshot.status.available:
            self.garden_goal_label.setText("Garden indisponível")
            self.garden_parents_label.setText("Pais e requisitos: —")
            self.garden_reason_label.setText(snapshot.status.message)
            self.garden_state_label.setText("Garden indisponível")
            self.garden_state_detail.setText(short_message(snapshot.status.message))
            self.garden_plan_text.setPlainText("Aguardar a conexão com o Garden.")
            self.garden_details_text.setPlainText(snapshot.status.message)
            self._show_garden_feedback(False, snapshot.status.message)
            return
        if plan.goal is None:
            incompatible = plan.explanation.startswith("Catálogo incompatível")
            self.garden_goal_label.setText("Garden não reconhecido" if incompatible else "Coleção completa")
            self.garden_parents_label.setText(
                "Garden não reconhecido. A automação está pausada para proteger suas plantas."
                if incompatible else "Todas as sementes foram desbloqueadas."
            )
            self.garden_reason_label.setText(plan.explanation)
        else:
            goal = plan.goal
            self.garden_goal_label.setText(goal.target_name)
            parents = ", ".join(goal.parent_names) if goal.parent_names else "nenhum (condição especial)"
            self.garden_parents_label.setText(f"{'Planta para colher' if plan.mode == 'garden_upgrades' else 'Plantas do canteiro' if plan.mode == 'golden_cookies' else 'Planta de origem' if goal.strategy == 'derivado_erva' else 'Pais por espaço de mutação'}: {parents}")
            pending = f" Pendentes: {', '.join(goal.pending_prerequisites)}." if goal.pending_prerequisites else ""
            self.garden_reason_label.setText(
                short_message(f"{goal.reason}{pending}", 100)
            )
        self.garden_goal_label.setToolTip(f"{plan.goal.reason} {plan.goal.success_condition}" if plan.goal else plan.explanation)
        self.garden_reason_label.setToolTip(plan.explanation)
        state, state_detail = current_state(snapshot, plan)
        self.garden_state_label.setText(state)
        self.garden_state_detail.setText(state_detail)
        self.garden_state_detail.setToolTip(state_detail)
        remaining = pending_actions(plan, value.action_results)
        plan_text = grouped_actions(remaining)
        if not plan_text:
            plan_text = ("Objetivo concluído. A automação do Garden ficará desligada." if objective_completed else
                         "Ações confirmadas. Aguardar a próxima leitura do Garden." if value.action_results else
                         "Colher a nova planta quando estiver madura." if state == "Esperando a nova planta amadurecer" else
                         "Plantar os pais quando chegar o momento indicado acima." if state == "Alinhando a maturação dos pais" else
                         "Manter os espaços livres e aguardar a mutação." if state == "Esperando a mutação aparecer" else
                         "Nenhuma ação: coleção de sementes completa." if state == "Coleção completa" else
                         "Manter o bônus e repor as plantas que morrerem." if plan.mode == "golden_cookies" else
                         "Aguardar o crescimento dos pais.")
        self._set_garden_report_text(self.garden_plan_text, plan_text)
        self.garden_plan_text.setFixedHeight(max(56, min(120, 24 + 18*len(plan_text.splitlines()))))
        details = plan.explanation
        action_lines = [self._format_garden_action(index, action) for index, action in enumerate(plan.actions, 1)]
        if action_lines:
            details += "\n\nPlano deste ciclo\n" + "\n".join(action_lines)
        if value.action_results:
            details += "\n\nResultados\n" + "\n".join(
                ("Confirmado: " if r.success else "Aguardando: " if r.waiting else "Falhou: ") + r.message
                for r in value.action_results)
        self._set_garden_report_text(self.garden_details_text, details)
        self.garden_details_toggle.setText("Mostrar detalhes da prévia" if value.dry_run else "Mostrar detalhes do último ciclo")
        if objective_completed:
            self._show_garden_feedback(True, "Objetivo concluído. Garden desligado.")
        elif value.action_results:
            waits = [result for result in value.action_results if result.waiting]
            errors = [result for result in value.action_results if not result.success and not result.waiting]
            if waits and not errors:
                waiting = waits[0]
                message = "Plantio aguardando cookies."
                budget = waiting.message
                if waiting.required_cookies is not None and waiting.available_cookies is not None:
                    missing = max(0.0, waiting.required_cookies - waiting.available_cookies)
                    message = f"Para replantar, faltam {self._format_number(missing)} cookies."
                    budget = (f"Necessário: {self._format_number(waiting.required_cookies)} cookies. "
                              f"Disponível: {self._format_number(waiting.available_cookies)}.")
                if waiting.reason == "insufficient_funds":
                    self.garden_status_label.setText("Garden: aguardando dinheiro")
                    self.garden_state_label.setText("Esperando cookies para replantar")
                    self.garden_state_detail.setText(budget)
                    self.garden_status_label.setStyleSheet("color: #e8b766; font-weight: 600;")
                else:
                    message = "Uma ação está aguardando. Consulte os detalhes."
                self._show_garden_feedback(True, message, tone="waiting")
                self.garden_feedback_label.setToolTip(waiting.message)
            elif errors:
                self.garden_state_label.setText("Uma ação precisa de atenção")
                self.garden_state_detail.setText(short_message(errors[0].message))
                self.garden_state_detail.setToolTip(errors[0].message)
                self._show_garden_feedback(False, f"{len(errors)} {'ação não concluída' if len(errors) == 1 else 'ações não concluídas'}. Veja os detalhes.")
            else:
                self._show_garden_feedback(True, result_summary(value.action_results))
                if not remaining and any(r.action in {"plant", "harvest"} for r in value.action_results):
                    self.garden_state_label.setText("Canteiro atualizado")
                    self.garden_state_detail.setText("O próximo plano será calculado a partir de uma nova leitura do Garden.")
        elif value.dry_run:
            self._show_garden_feedback(True, "Prévia atualizada. Nenhuma ação executada.", tone="neutral")
        else:
            self._show_garden_feedback(True, "Estado atualizado. Aguardando o próximo tick.", tone="neutral")

    def _toggle_garden_details(self, visible):
        self.garden_details_text.setVisible(visible)
        target = self.garden_details_text if visible else self.garden_plan_text
        QTimer.singleShot(0, lambda: self.garden_scroll.ensureWidgetVisible(target, 0, 12))

    @staticmethod
    def _set_garden_report_text(widget, text):
        if widget.toPlainText() == text:
            return
        scroll = widget.verticalScrollBar().value()
        widget.setPlainText(text)
        widget.verticalScrollBar().setValue(scroll)

    @staticmethod
    def _format_garden_action(index, action) -> str:
        labels = {
            "plant": "Plantar", "harvest": "Colher", "change_soil": "Trocar solo", "boost_mutation": "Usar Sugar Lump",
            "set_freeze": "Descongelar",
        }
        if action.kind == "harvest" and not action.require_mature:
            labels["harvest"] = "Remover"
        position = f" em ({action.x}, {action.y})" if action.x is not None and action.y is not None else ""
        from app.core.garden_catalog import GARDEN_CATALOG
        recipe = GARDEN_CATALOG.get(action.seed_key)
        soils = {"dirt": "Dirt", "fertilizer": "Fertilizer", "clay": "Clay",
                 "pebbles": "Pebbles", "woodchips": "Wood Chips"}
        subject = recipe.name if recipe else soils.get(action.soil_key, action.seed_key or action.soil_key or "Garden")
        return f"{index}. {labels.get(action.kind, action.kind)} {subject}{position} — {action.reason}"

    def _show_garden_feedback(self, success: bool, message: str, *, tone=None):
        summary = short_message(message)
        self.garden_feedback_label.setText(summary)
        self.garden_feedback_label.setVisible(tone != "neutral")
        self.garden_feedback_label.setToolTip(message)
        if summary != message and message not in self.garden_details_text.toPlainText():
            self._set_garden_report_text(self.garden_details_text, self.garden_details_text.toPlainText() + "\n\nAviso\n" + message)
        color = '#9aa7ba' if tone == 'neutral' else '#e8b766' if tone == 'waiting' else '#65d6a5' if success else '#f07883'
        self.garden_feedback_label.setStyleSheet(f'color: {color};')
        self.status_bar.showMessage(summary, 7000)

    def _set_garden_busy(self, busy: bool):
        self.garden_refresh_button.setEnabled(not busy)
        self.garden_simulate_button.setEnabled(not busy)
        self.garden_strategy_combo.setEnabled(not busy)


    def _toggle_garden_automation(self, enabled: bool):
        if enabled and not self._bot_enabled:
            self.add_log("Ligue o bot no topo antes de iniciar automações.")
            return
        if enabled:
            if self._combo_exclusive or self._save_scum_exclusive or not self.bridge or not self.fazendeira:
                self._show_garden_feedback(False, "Não foi possível ligar: conecte o jogo e aguarde o Combo terminar.")
                return
            self._garden_stop = threading.Event()
            self.garden_toggle.set_running(True)
            self.garden_refresh_timer.stop()
            if self._garden_worker and self._garden_worker.isRunning():
                self._garden_run_when_idle = True
            else:
                QTimer.singleShot(0, self._on_garden_timer)
        else:
            if self.runner:
                self.runner.request_wrinkler_cash("Garden")
            self._garden_stop.set()
            self._garden_run_when_idle = False
            if self._garden_worker and self._garden_worker.isRunning():
                self.garden_toggle.set_stopping()
            else:
                self.garden_toggle.set_running(False)
        automation_config.enable_garden_automation = bool(enabled)
        save_automation_settings()
        logger.info("Garden: %s", "ligada" if enabled else "desligamento solicitado")
        self._show_garden_feedback(True, "Automação ligada." if enabled else "Novas ações interrompidas; aguardando o lote em andamento terminar.")

    def _update_garden_strategy_tooltip(self):
        tips = {
            'plants': 'Desbloqueia todas as sementes e desliga o Garden ao completar a coleção.',
            'green_aching_thumb': 'Cultiva e colhe Thumbcorn maduras até a conquista de 1.000 colheitas. Desliga ao concluir.',
            'golden_cookies': 'Cultivo contínuo de Golden Clover e Nursetulip. Usa Fertilizer para crescer e Clay para ampliar o bônus. Nursetulip reduz o CpS. Não usa Sugar Lumps.',
            'garden_upgrades': 'Cultiva e colhe as plantas dos upgrades que faltam. Considera concluídos os upgrades comprados ou disponíveis na loja. Não compra upgrades nem usa Sugar Lumps. Desliga ao liberar os sete.',
        }
        self.garden_strategy_combo.setToolTip(tips[self.garden_strategy_combo.currentData()])

    def _change_garden_strategy(self, index: int):
        automation_config.garden_strategy = self.garden_strategy_combo.currentData()
        self._update_garden_strategy_tooltip()
        save_automation_settings()
        logger.info("Garden: estratégia %s selecionada.",self.garden_strategy_combo.currentText())
        self._show_garden_feedback(True,f"Estratégia: {self.garden_strategy_combo.currentText()}.")
        if not (self._garden_worker and self._garden_worker.isRunning()):
            QTimer.singleShot(0, self._on_garden_timer if self.garden_toggle.running else self.refresh_garden)

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
            logger.error("Stock Market: não foi possível confirmar o resultado das negociações.")
            return
        if self.runner and value.tick_changed:
            snapshot = value.snapshot
            entries = {signal.asset_id for signal in value.signals if signal.is_entry_candidate}
            costs = [asset.price * (snapshot.highest_raw_cps or 0) * (snapshot.broker_overhead or 1)
                     for asset in snapshot.assets if asset.asset_id in entries and asset.owned == 0
                     and asset.capacity and asset.capacity > 0]
            target = min(costs, default=0) if (snapshot.status.available and self._bot_enabled
                      and self.stock_toggle.running and not self._stock_stop.is_set()) else 0
            if target <= (snapshot.cookies or 0):
                target = 0
            self.runner.request_wrinkler_cash("Banco", target, snapshot.game_seed,
                                             ttl=max(1, snapshot.seconds_per_tick or 60))
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
                f"Automação: {successful}/{len(value.orders)} ordens concluídas.",
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
            logger.error("Stock Market: não foi possível confirmar a ordem.")
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
            self.stock_feedback_label.setText("Atualizando mercado…")
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
    def toggle_wrinkler_detection(self, state): self._save("enable_wrinkler_popper", state); self.wrinkler_free_slots_input.setEnabled(bool(state))
    def update_krumblor_interval(self, value):
        automation_config.krumblor_pet_interval_seconds = float(value)
        save_automation_settings()
        if self.runner:
            self.runner.reset_krumblor_schedule()

    def toggle_auto_season(self, state):
        self._save("enable_auto_season", state)
        if self.runner:
            self.runner.reset_season_schedule()
        logger.info("Temporadas: renovação automática %s.", "ligada" if state else "desligada")

    def update_auto_season(self, index):
        season = self.auto_season_combo.itemData(index)
        if season not in SEASONS:
            return
        automation_config.auto_season = season
        save_automation_settings()
        if self.runner:
            self.runner.reset_season_schedule()

    def toggle_krumblor_upgrades(self, state):
        self._save("enable_krumblor_upgrades", state)
        if self.runner:
            self.runner.reset_krumblor_schedule()
        logger.info("Krumblor: coleta de upgrades %s.", "ativada" if state else "desativada")

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
    def update_wrinkler_free_slots(self, value): automation_config.wrinkler_free_slots = value; save_automation_settings()
    def update_log_limit(self, value):
        app_config.max_log_lines = max(1, int(value)); save_app_settings(); self._trim_logs()

    def toggle_clicker(self):
        if app_config.clicker_mode == "hold":
            return
        if not self._bot_enabled or self.clicker_hotkey_input.is_capturing or self.mouse_clicker_hotkey_input.is_capturing:
            return
        if not self.runner: logger.warning("Runner não está disponível"); return
        self.runner.toggle_clicker(); self.set_clicker_state(self.runner.is_running)
    def set_clicker_state(self, active):
        hold = app_config.clicker_mode == "hold"
        self.clicker_button.setText("Segure o atalho" if hold else "Desligar" if active else "Ligar")
        self.clicker_button.setFixedWidth(125 if hold else 90)
        if hold:
            self.clicker_button.setEnabled(False)
        self.clicker_button.setChecked(active)
        capturing = self.clicker_hotkey_input.is_capturing or self.mouse_clicker_hotkey_input.is_capturing
        self.clicker_run_status.setText("Detectando atalho…" if capturing else "Clicando" if active else "Aguardando atalho" if hold and self._bot_enabled else "Desligado")
        color = "#65d6a5" if active else "#9aa7ba"
        self.clicker_run_status.setStyleSheet(f"color: {color};")
        self.clicker_status.setText("Clicker: Ativo" if active else "Clicker: Parado")
        self.clicker_status.setStyleSheet(f"color: {color}; font-weight: 600;")

    def _hotkey_capture_changed(self, capturing):
        if capturing:
            source = self.sender()
            for widget in (self.clicker_hotkey_input, self.mouse_clicker_hotkey_input):
                if widget is not source and widget.is_capturing:widget.cancel()
        active = self.clicker_hotkey_input.is_capturing or self.mouse_clicker_hotkey_input.is_capturing
        if self.runner:
            self.runner.hotkey_capture_active.set() if active else self.runner.hotkey_capture_active.clear()
            self.set_clicker_state(bool(self.runner.is_running))
            self.set_mouse_clicker_state(bool(self.runner.mouse_clicker_running))

    def _save_clicker_hotkey(self, mode, key):
        own = "toggle_key" if mode == "clicker" else "mouse_toggle_key"
        other = "mouse_toggle_key" if mode == "clicker" else "toggle_key"
        widget = getattr(self, mode + "_hotkey_input")
        if key == getattr(app_config, other):
            widget.set_key(getattr(app_config, own))
            self.status_bar.showMessage("Este atalho já está no outro clicker. Detecte uma tecla ou botão diferente.", 7000)
            return
        if key in CLICKER_HOTKEYS:
            setattr(app_config, own, key)
            save_app_settings()

    def update_clicker_hotkey(self, key):
        self._save_clicker_hotkey("clicker", key)

    def update_mouse_clicker_hotkey(self, key):
        self._save_clicker_hotkey("mouse_clicker", key)

    def update_clicker_speed(self, value):
        app_config.click_interval = 1.0 / value
        save_app_settings()

    def update_clicker_mode(self, name):
        mode = getattr(self, name + "_mode_input").currentData()
        setattr(app_config, name + "_mode", mode)
        if self.runner:
            self.runner.reset_manual_clicker(mouse=name == "mouse_clicker")
        button = getattr(self, name + "_button")
        button.setEnabled(mode == "toggle" and self._bot_enabled and not self._combo_exclusive
                          and not self._save_scum_exclusive)
        save_app_settings()
        self.refresh_clicker_states()

    def refresh_clicker_states(self):
        cookie = bool(self.runner and (self.runner.is_running or self.runner.cookie_hold_active))
        mouse = bool(self.runner and (self.runner.mouse_clicker_running or self.runner.mouse_hold_active))
        self.set_clicker_state(cookie)
        self.set_mouse_clicker_state(mouse)

    def update_mouse_clicker_speed(self, value):
        app_config.mouse_click_interval = 1.0 / value
        save_app_settings()

    def toggle_mouse_clicker(self):
        if app_config.mouse_clicker_mode == "hold":
            return
        if self._bot_enabled and self.runner and not self.clicker_hotkey_input.is_capturing and not self.mouse_clicker_hotkey_input.is_capturing:
            self.runner.toggle_mouse_clicker()
            self.set_mouse_clicker_state(self.runner.mouse_clicker_running)

    def set_mouse_clicker_state(self, active):
        hold = app_config.mouse_clicker_mode == "hold"
        self.mouse_clicker_button.setText("Segure o atalho" if hold else "Desligar" if active else "Ligar")
        self.mouse_clicker_button.setFixedWidth(125 if hold else 90)
        if hold:
            self.mouse_clicker_button.setEnabled(False)
        self.mouse_clicker_button.setChecked(active)
        over_game = self.runner.mouse_clicker_over_game if self.runner and hasattr(self.runner, "mouse_clicker_over_game") else True
        capturing = self.clicker_hotkey_input.is_capturing or self.mouse_clicker_hotkey_input.is_capturing
        self.mouse_clicker_run_status.setText("Detectando atalho…" if capturing else "Clicando" if active and over_game else "Aguardando o mouse no jogo" if active else "Aguardando atalho" if hold and self._bot_enabled else "Desligado")
        self.mouse_clicker_run_status.setStyleSheet(f"color: {'#65d6a5' if active else '#9aa7ba'};")

    def update_bridge_status(self, connected):
        if bool(connected) != self._sugar_lump_connected:
            self._sugar_lump_connection_epoch += 1
        self._sugar_lump_connected = bool(connected)
        if not connected:
            self.sugar_lump_type_label.setText("Sugar Lump: —")
        self.bridge_status.setText("Jogo: conectado" if connected else "Jogo: desconectado"); self.bridge_status.setStyleSheet(f"color: {'#65d6a5' if connected else '#f07883'}; font-weight: 600;")
    def add_log(self, message):
        message = str(message)
        if not re.match(r"^(?:\d{4}-\d{2}-\d{2} )?\d{2}:\d{2}:\d{2} - (?:DEBUG|INFO|WARNING|ERROR|CRITICAL) - ", message):
            logger.info("%s", message)
            if any(getattr(handler, "emitter", None) is self.log_emitter for handler in logger.handlers):
                return
            message = time.strftime("%H:%M:%S") + " - INFO - " + message
        scrollbar = self.log_text.verticalScrollBar()
        follow = scrollbar.value() >= scrollbar.maximum() - 2
        position = scrollbar.value()
        cursor = QTextCursor(self.log_text.document())
        cursor.movePosition(QTextCursor.End)
        if not self.log_text.document().isEmpty():
            cursor.insertBlock()
        cursor.insertText(str(message))
        self._trim_logs()
        scrollbar.setValue(scrollbar.maximum() if follow else position)

    def _trim_logs(self):
        """Remove as linhas mais antigas para manter o histórico sob controle."""
        document = self.log_text.document()
        while document.blockCount() > app_config.max_log_lines:
            cursor = QTextCursor(document); cursor.movePosition(QTextCursor.Start)
            cursor.select(QTextCursor.BlockUnderCursor); cursor.removeSelectedText()
            if not cursor.atEnd():
                cursor.deleteChar()
    def refresh_stats(self):
        self.refresh_bot_control()
        self._refresh_sugar_lump_type()
        elapsed = int(time.monotonic() - self._session_started_at)
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.session_timer_label.setText(f"Sessão: {hours:02}:{minutes:02}:{seconds:02}")
        if not self.runner: return
        self.cookies_clicked_label.setText(f"Cliques: {self.runner.cookies_clicked}"); self.golden_clicked_label.setText(f"Golden: {self.runner.golden_cookies_clicked}"); self.reindeer_popped_label.setText(f"Renas: {self.runner.reindeer_popped}"); self.wrinklers_popped_label.setText(f"Wrinklers: {self.runner.wrinklers_popped}")
    def _refresh_sugar_lump_type(self):
        # Apenas leitura, mesmo com o bot pausado, sem bloquear a interface.
        if not self.bridge or not self._sugar_lump_connected:
            self.sugar_lump_type_label.setText("Sugar Lump: —")
            return
        if self._sugar_lump_worker is not None:
            return
        bridge, epoch = self.bridge, self._sugar_lump_connection_epoch
        worker = StockMarketWorker(lambda: (bridge, epoch, bridge.get_sugar_lump_status()), self)
        self._sugar_lump_worker = worker
        worker.completed.connect(self._display_sugar_lump_type)
        worker.failed.connect(self._sugar_lump_status_failed)
        worker.finished.connect(self._sugar_lump_status_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _display_sugar_lump_type(self, value):
        bridge, epoch, status = value
        if (bridge is not self.bridge or epoch != self._sugar_lump_connection_epoch
                or not self._sugar_lump_connected):
            return
        names = {0: "Normal", 1: "Bifurcado", 2: "Dourado", 3: "Carnudo", 4: "Caramelizado"}
        lump_type = status.get("type") if isinstance(status, dict) else None
        name = names.get(lump_type, "—") if type(lump_type) is int else "—"
        self.sugar_lump_type_label.setText(f"Sugar Lump: {name}")

    def _sugar_lump_status_failed(self, _message):
        self.sugar_lump_type_label.setText("Sugar Lump: —")

    def _sugar_lump_status_finished(self):
        self._sugar_lump_worker = None

    def open_backup_dialog(self):
        if self.backup_dialog is None:
            self.backup_dialog = BackupDialog(
                self.backup_manager, self, get_bridge=lambda: self.bridge,
                acquire_restore=self._acquire_backup_restore,
                finish_restore=self._finish_backup_restore,
            )
        self.backup_dialog.show()
        self.backup_dialog.raise_()
        self.backup_dialog.activateWindow()

    def _acquire_backup_restore(self):
        if self._save_scum_exclusive:
            if self._exclusive_session_owner == "backup_restore":
                return True
            pending = (not self.save_scum_tab.worker and self.save_scum_tab.last_report
                       and not self.save_scum_tab.last_report.safe_to_resume)
            if pending:
                return True
            self.backup_dialog.set_status("Desligue Save Scum antes de carregar um backup.", True)
            return False
        return self._acquire_save_scum(
            owner="backup_restore",
            error_handler=lambda message: self.backup_dialog.set_status(message, True),
        )

    def _finish_backup_restore(self, result):
        self.add_log("Backups: " + result.message)
        if self._exclusive_session_owner == "save_scum":
            if result.ok:
                self.save_scum_tab.manual_recovery()
            return
        if result.ok or (result.safe_to_resume and not self._backup_recovery_pending):
            self._backup_recovery_pending = False
            self._release_save_scum()
        else:
            self._backup_recovery_pending = True
            self.backups_button.setEnabled(True)
            self.add_log("Outras automações continuam pausadas até recuperar o save.")

    def on_backup_restored(self, save_data):
        if self._save_scum_exclusive:
            if self.save_scum_tab.worker or not self.save_scum_tab.last_report or self.save_scum_tab.last_report.safe_to_resume:
                self.add_log("Save Scum ativo: desligue antes de importar outro backup.")
                return
            if self.bridge and self.bridge.load_game_save(save_data):
                self.save_scum_tab.manual_recovery()
            else:
                self.add_log("Falha ao importar backup; outras automações continuam pausadas.")
            return
        if self.runner and self.runner.bridge and self.runner.bridge.load_game_save(save_data): logger.info("Backups: save restaurado com sucesso.")
        else: logger.warning("Backups: falha ao restaurar save; verifique a conexão com o jogo.")

    def closeEvent(self, event):
        """Evita destruir uma thread de consulta ainda em execução."""
        if hasattr(self, "game_connection_shutdown") and not self.game_connection_shutdown():
            event.ignore()
            return
        if self.backup_dialog and not self.backup_dialog.shutdown():
            event.ignore()
            return
        if not self.save_scum_tab.shutdown():
            event.ignore()
            return
        self.clicker_hotkey_input.cancel()
        self.mouse_clicker_hotkey_input.cancel()
        self.clicker_status_timer.stop()
        self.stats_timer.stop()
        if (self._sugar_lump_worker and self._sugar_lump_worker.isRunning()
                and not self._sugar_lump_worker.wait((app_config.connection_timeout + 1) * 1000)):
            self.clicker_status_timer.start(50)
            self.stats_timer.start(1000)
            event.ignore()
            return
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
        if not self.combo_planner.shutdown():
            event.ignore()
            return
        super().closeEvent(event)


def create_ui_app(bridge: Optional[CookieClickerBridge] = None):
    set_windows_app_id()
    app = QApplication(sys.argv); app.setStyleSheet(DARK_STYLESHEET); enable_dark_title_bars(app)
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    window = MainWindow(bridge); window.setWindowIcon(app.windowIcon())
    return app, window
