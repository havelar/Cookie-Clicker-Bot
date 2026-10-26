"""Controle e acompanhamento do farm para a última conquista de dourados."""
import threading
import time

from PyQt5.QtCore import QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QGroupBox, QLabel, QProgressBar, QTextEdit, QCheckBox

from app.config.settings import automation_config, save_automation_settings
from app.core.gc_farm import GCFarm
from app.ui.automation_control import AutomationControl
from app.ui.number_inputs import ScrollSafeComboBox, ScrollSafeDoubleSpinBox


class GCWorker(QThread):
    result = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, farm, parent):
        super().__init__(parent)
        self.farm = farm

    def run(self):
        try:
            self.result.emit(self.farm.step())
        except Exception as error:
            self.failed.emit(str(error))


def duration(seconds):
    if seconds is None:
        return 'Aguardando cliques suficientes'
    if seconds < 60:
        return f'{max(0, round(seconds))} s'
    minutes = max(1, round(seconds / 60))
    days, minutes = divmod(minutes, 1440)
    hours, minutes = divmod(minutes, 60)
    return (f'{days} d ' if days else '') + (f'{hours} h ' if hours else '') + f'{minutes} min'


class GCFarmTab(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.worker = None
        self.farm = None
        self.stop_event = threading.Event()
        self.completed = False
        self.start_pending = False
        self.start_deadline = 0
        self.last_message = None
        layout = QVBoxLayout(self)
        controls = QGroupBox('Farm para os 27.777 Golden Cookies')
        form = QFormLayout(controls)
        self.strategy = ScrollSafeComboBox()
        self.strategy.addItem('Dourados frequentes', 'golden')
        self.strategy.addItem('Correntes de vermelhos — em breve', 'chain')
        self.strategy.model().item(1).setEnabled(False)
        self.strategy.setToolTip('Dourados frequentes prepara trevos e tulipas. Correntes de vermelhos ainda não está disponível.')
        self.reserve = ScrollSafeDoubleSpinBox()
        self.reserve.setRange(0, 99)
        self.reserve.setSuffix(' %')
        self.reserve.setMaximumWidth(140)
        self.reserve.setValue(automation_config.gc_farm_reserve_percent)
        self.reserve.setToolTip('Parte do saldo atual preservada em cada compra e lote de sementes. O Banco mantém seu próprio orçamento. Trocas de aura sacrificam construções.')
        self.reserve.valueChanged.connect(self._save)
        form.addRow('Estratégia', self.strategy)
        form.addRow('Reservar dinheiro', self.reserve)
        self.manual_last_click = QCheckBox('Deixar o clique 27.777 para mim')
        self.manual_last_click.setChecked(automation_config.gc_farm_manual_last_click)
        self.manual_last_click.setToolTip('Bloqueia a coleta automática somente em 27.776 cliques. Clique no próximo biscoito manualmente para ganhar a conquista. Em 27.777 ou mais, esta opção não bloqueia nada. Pode ser alterada com o farm ligado e fica salva.')
        self.manual_last_click.toggled.connect(self._save_manual_last_click)
        form.addRow(self.manual_last_click)
        info = QLabel('Prepara Garden, dragão, Panteão e temporada. Banco, Sugar Lumps e outras coletas compatíveis continuam conforme suas opções. Não gasta torrões nem ascende.')
        info.setWordWrap(True)
        form.addRow(info)
        self.toggle = AutomationControl('GC Farm')
        self.toggle.requested.connect(self.request)
        form.addRow(self.toggle)
        layout.addWidget(controls)
        progress = QGroupBox('Progresso da conquista')
        rows = QFormLayout(progress)
        self.progress = QProgressBar()
        self.progress.setRange(0, GCFarm.TARGET)
        self.progress.setFormat('%v / 27.777')
        self.rate = QLabel('—')
        self.eta = QLabel('—')
        self.session = QLabel('—')
        self.state = QLabel('Desligada')
        self.state.setWordWrap(True)
        self.garden = QLabel('—')
        self.garden.setWordWrap(True)
        rows.addRow(self.progress)
        rows.addRow('GC por hora', self.rate)
        rows.addRow('Tempo restante estimado', self.eta)
        rows.addRow('Nesta sessão', self.session)
        rows.addRow('Agora', self.state)
        rows.addRow('Garden', self.garden)
        self.rate.setToolTip('Variação do contador oficial na última hora, incluindo o preparo. Tempestades e biscoitos invocados não inflam esta medida.')
        self.eta.setToolTip('Projeção pelo ritmo observado, sem garantia. No início e durante o crescimento do Garden ela pode variar bastante.')
        layout.addWidget(progress)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(150)
        layout.addWidget(self.log, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self._tick)

    @property
    def active(self):
        return self.farm is not None

    def _save(self):
        automation_config.gc_farm_reserve_percent = self.reserve.value()
        save_automation_settings()

    def _save_manual_last_click(self, checked):
        automation_config.gc_farm_manual_last_click = checked
        save_automation_settings()

    def request(self, enabled):
        if not enabled:
            self.start_pending = False
            self.stop_event.set()
            self.timer.stop()
            if self.active:
                self.toggle.set_stopping()
            if not self.worker:
                self._finish()
                if not self.active:
                    self.toggle.set_running(False)
            return
        if self.active or self.strategy.currentData() != 'golden':
            return
        if not self.start_pending:
            self.start_deadline = time.monotonic() + 15
        ready = self.window.begin_gc_farm()
        if ready is None:
            self.start_pending = True
            self.toggle.set_running(True)
            if time.monotonic() >= self.start_deadline:
                self.start_pending = False
                self.toggle.set_running(False)
                self.state.setText('O outro modo ainda está encerrando. Aguarde antes de tentar novamente.')
            else:
                QTimer.singleShot(200, self._retry_start)
            return
        self.start_pending = False
        if not ready:
            self.toggle.set_running(False)
            return
        self.completed = False
        self.stop_event = threading.Event()
        self.last_message = None
        self.farm = GCFarm(self.window.bridge, self.reserve.value(), should_stop=self.stop_event.is_set,
                           manual_last_click=lambda: automation_config.gc_farm_manual_last_click)
        self.strategy.setEnabled(False)
        self.reserve.setEnabled(False)
        self.toggle.set_running(True)
        self.state.setText('Preparando a coleta…')
        self.timer.start()
        self._tick()

    def _retry_start(self):
        if self.start_pending:
            self.request(True)

    def _tick(self):
        if self.worker or not self.active or self.stop_event.is_set():
            return
        self.worker = GCWorker(self.farm, self)
        self.worker.result.connect(self._display)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _display(self, report):
        if 'count' in report and not report.get('terminal') and not self.stop_event.is_set() and self.farm:
            self.window.runner.activate_gc_farm_collection(self.farm.seed)
        if 'count' in report:
            self.progress.setValue(min(GCFarm.TARGET, report['count']))
            initial = ' (estimativa inicial)' if report['elapsed'] < 300 else ''
            self.rate.setText(f"{report['rate']:.1f}" + initial)
            self.eta.setText('Concluído' if report.get('completed') else duration(report['eta']))
            if report.get('waiting_manual'):
                self.eta.setText('Aguardando seu clique')
            self.session.setText(f"{report['gained']} cliques válidos em {duration(report['elapsed'])}")
            self.garden.setText(report['garden'][:350])
            self.garden.setToolTip(report['garden'])
        message = ('Falta só o seu clique! Clique manualmente no próximo Golden Cookie para concluir a conquista.'
                   if report.get('waiting_manual') else report['message'])
        self.state.setText(message)
        if message != self.last_message:
            self.log.append(message)
            self.last_message = message
        if report.get('terminal'):
            self.completed = bool(report.get('completed'))
            self.stop_event.set()
            self.timer.stop()

    def _failed(self, message):
        self.state.setText('Farm interrompido: ' + message)
        self.log.append('Farm interrompido: ' + message)
        self.stop_event.set()
        self.timer.stop()

    def _worker_finished(self):
        worker, self.worker = self.worker, None
        if worker:
            worker.deleteLater()
        if self.stop_event.is_set():
            self._finish()

    def _finish(self):
        if not self.active:
            return
        self.farm = None
        self.toggle.set_running(False)
        self.strategy.setEnabled(True)
        self.reserve.setEnabled(True)
        self.window.end_gc_farm(self.completed)

    def shutdown(self):
        self.request(False)
        if self.worker and not self.worker.wait(7000):
            return False
        # A notificação finished pode ainda estar na fila do Qt.
        if self.active:
            self._finish()
        return True
