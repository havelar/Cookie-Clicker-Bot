"""Consulta das próximas magias para montar combos manualmente."""
from PyQt5.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.config.settings import app_config
from app.ui.number_inputs import ScrollSafeComboBox


EFFECTS = {
    "frenzy": "Frenesi ×7",
    "multiply cookies": "Sorte (ganha biscoitos)",
    "click frenzy": "Frenesi de cliques",
    "building special": "Bônus de construção",
    "blood frenzy": "Frenesi ancestral",
    "cookie storm": "Tempestade de biscoitos",
    "cookie storm drop": "Biscoito da tempestade",
    "free sugar lump": "Torrão de açúcar",
    "blab": "Mensagem sem efeito",
    "clot": "Coágulo (produção ÷2)",
    "ruin cookies": "Azar (perde biscoitos)",
    "cursed finger": "Dedo amaldiçoado",
}


class PlannerWorker(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, bridge, count, mode, parent):
        super().__init__(parent)
        self.bridge, self.count, self.mode = bridge, count, mode

    def run(self):
        try:
            self.completed.emit(self.bridge.forecast_fthof_planner(self.count, self.mode))
        except Exception:
            self.failed.emit("Não foi possível atualizar. Verifique a conexão com o jogo.")


class ComboPlanner(QWidget):
    def __init__(self, bridge_provider, parent=None):
        super().__init__(parent)
        self.bridge_provider = bridge_provider
        self.worker = None
        self._request = None
        self._last_value = None
        self._closing = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Previsão"))
        self.season_combo = ScrollSafeComboBox()
        for label, key in (("Temporada atual", "current"), ("Outras temporadas", "normal"),
                           ("Páscoa ou Dia dos Namorados", "seasonal")):
            self.season_combo.addItem(label, key)
        self.season_combo.setFixedWidth(230)
        self.season_combo.setMinimumHeight(30)
        self.season_combo.setToolTip("Compara os resultados de Forçar a Mão do Destino sem trocar a temporada no jogo. Páscoa e Dia dos Namorados têm uma sequência diferente de Natal, Dia das Bruxas, Dia dos Negócios e sem temporada.")
        controls.addWidget(self.season_combo)
        controls.addWidget(QLabel("Próximas"))
        self.count_combo = ScrollSafeComboBox()
        for count in (50, 100, 250, 500):
            self.count_combo.addItem(str(count), count)
        self.count_combo.setCurrentIndex(1)
        self.count_combo.setFixedWidth(75)
        self.count_combo.setMinimumHeight(30)
        for combo in (self.season_combo, self.count_combo):
            combo.setStyleSheet(
                "QComboBox { background: #171b21; border: 1px solid #37404e; "
                "border-radius: 6px; padding: 4px 24px 4px 8px; }"
                "QComboBox::drop-down { width: 20px; border: none; }"
                "QComboBox QAbstractItemView { background: #20252e; selection-background-color: #2d5f9f; }"
            )
        controls.addWidget(self.count_combo)
        controls.addStretch()
        self.refresh_button = QPushButton("Atualizar")
        self.refresh_button.clicked.connect(self.refresh)
        controls.addWidget(self.refresh_button)
        layout.addLayout(controls)
        self.auto_refresh = QCheckBox("Acompanhar magias automaticamente")
        self.auto_refresh.setChecked(True)
        self.auto_refresh.setToolTip("Atualiza a cada 2 segundos enquanto o Planejador estiver visível. Não lança magias nem ativa automações.")
        self.auto_refresh.toggled.connect(self._auto_changed)
        layout.addWidget(self.auto_refresh)
        self.status = QLabel("Conecte o jogo para consultar o Grimório.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        hint = QLabel("Magias antes: 0 significa lançar Forçar a Mão do Destino agora. Escolha a coluna pela quantidade de biscoitos dourados ou da ira ainda em tela antes de lançar.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(("Magias antes", "Contador", "0 biscoitos", "1 biscoito", "2 biscoitos", "3 biscoitos"))
        self.table.horizontalHeaderItem(0).setToolTip("Quantas magias lançar para avançar o contador antes de usar Forçar a Mão do Destino nesta posição. Zero significa lançar agora.")
        self.table.horizontalHeaderItem(1).setToolTip("Total de magias já lançadas no momento desta previsão. Inclui as magias usadas para avançar até esta posição.")
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setMinimumSectionSize(65)
        for column in range(2, 6):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.Stretch)
            self.table.horizontalHeaderItem(column).setToolTip(f"Resultado com {column-2} biscoitos dourados ou da ira ainda em tela antes de lançar. Efeitos já ativos não contam. Cada biscoito acrescenta 15 pontos percentuais à chance de falha.")
        layout.addWidget(self.table, 1)
        note = QLabel("A previsão usa os efeitos e construções atuais; mudanças podem alterar o resultado. A construção que receberá o bônus só é definida ao abrir o biscoito. Para jogar manualmente, desligue as automações que lançam magias ou coletam biscoitos dourados.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.refresh)
        self.season_combo.currentIndexChanged.connect(self._options_changed)
        self.count_combo.currentIndexChanged.connect(self._options_changed)

    def _options(self):
        return self.count_combo.currentData(), self.season_combo.currentData()

    def _options_changed(self):
        self._last_value = None
        self.table.setRowCount(0)
        self.status.setText("Atualizando a previsão…")
        self.refresh()

    def _auto_changed(self, enabled):
        if enabled and self.isVisible():
            self.timer.start()
            self.refresh()
        else:
            self.timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        if self.auto_refresh.isChecked():
            self.timer.start()
        self.refresh()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def refresh(self):
        if self._closing or (self.worker and self.worker.isRunning()):
            return
        bridge = self.bridge_provider()
        if bridge is None or bridge.connected is False:
            self._last_value = None
            self.table.setRowCount(0)
            self.status.setText("Conecte o jogo e aguarde a liberação da consulta para atualizar o Planejador.")
            return
        count, mode = self._options()
        self._request = (bridge, count, mode)
        self.worker = PlannerWorker(bridge, count, mode, self)
        self.worker.completed.connect(self.display_result)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._finished)
        self.refresh_button.setEnabled(False)
        self.worker.start()

    def _finished(self):
        self.refresh_button.setEnabled(True)
        worker = self.worker
        self.worker = None
        if worker:
            worker.deleteLater()
        if not self._closing and self.isVisible() and self._request and self._request[1:] != self._options():
            self.refresh()

    def _current_request(self):
        return (not self._closing and self._request is not None
                and self._request[0] is self.bridge_provider() and self._request[1:] == self._options())

    def _failed(self, message):
        if not self._current_request():
            return
        self._last_value = None
        self.table.setRowCount(0)
        self.status.setText(message)

    def display_result(self, value):
        if not self._current_request():
            return
        if not isinstance(value, dict) or not value.get("ok") or not isinstance(value.get("rows"), list):
            self._failed(value.get("message", "Não foi possível consultar o Grimório.") if isinstance(value, dict) else "Resposta inválida do Grimório.")
            return
        if value == self._last_value:
            return
        self._last_value = value
        current = value['currentCast']
        visible = value['visible']
        context = "Páscoa / Dia dos Namorados" if value['seasonal'] else "Natal / Dia das Bruxas / Negócios / sem temporada"
        warning = " Voo do dragão ativo: frenesi de cliques indisponível." if value['dragonflight'] else ""
        self.status.setText(f"Contador: {current} · Biscoitos em tela: {visible} · Previsão: {context}.{warning}")
        scroll = self.table.verticalScrollBar().value()
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(value['rows']))
        for index, row in enumerate(value['rows']):
            for column, text in enumerate((str(row['offset']), str(row['cast']))):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                if column == 0:
                    item.setToolTip("Quantas magias lançar antes de usar Forçar a Mão do Destino nesta posição. Zero significa lançar agora.")
                self.table.setItem(index, column, item)
            for existing, outcome in enumerate(row['outcomes']):
                effect = outcome['effect']
                text = EFFECTS.get(effect, effect)
                item = QTableWidgetItem(text + (" [falha]" if outcome['backfire'] else ""))
                item.setToolTip(f"{text}\nChance de falha: {outcome['failChance']:.1%}\n" +
                                ("A magia falha e cria um biscoito da ira com este efeito." if outcome['backfire'] else "A magia cria um biscoito dourado com este efeito."))
                if effect in ("click frenzy", "blood frenzy", "building special", "free sugar lump"):
                    item.setForeground(QColor("#8de0a6"))
                elif outcome['backfire']:
                    item.setForeground(QColor("#e8b766"))
                if existing == visible:
                    item.setBackground(QColor("#25354c"))
                self.table.setItem(index, existing + 2, item)
        self.table.resizeRowsToContents()
        self.table.verticalScrollBar().setValue(scroll)
        self.table.setUpdatesEnabled(True)

    def shutdown(self):
        self._closing = True
        self.timer.stop()
        if self.worker and self.worker.isRunning():
            return self.worker.wait((app_config.connection_timeout + 1) * 1000)
        return True
