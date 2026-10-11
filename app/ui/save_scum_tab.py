"""Aba Save Scum: tentativas em worker e recuperação explícita de checkpoint."""
import time
from pathlib import Path
from app.utils.logger import logger
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QHBoxLayout, QGroupBox, QCheckBox, QLabel, QPushButton, QTextEdit
from app.config.settings import automation_config, save_automation_settings
from app.core.save_scum import SaveScumAutomation, SaveScumConfig, SaveScumReport
from app.ui.automation_control import AutomationControl
from app.ui.number_inputs import ScrollSafeSpinBox, ScrollSafeDoubleSpinBox

class SaveScumWorker(QThread):
    updated = pyqtSignal(object)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, automation, mode, parent=None):
        super().__init__(parent)
        self.automation, self.mode = automation, mode

    def run(self):
        try:
            report = (self.automation.executar(self.updated.emit) if self.mode == 'run' else
                      self.automation.recuperar() if self.mode == 'recover' else self.automation.gerar_previa())
            self.completed.emit(report)
        except Exception as error:
            self.failed.emit(str(error))

class SaveScumTab(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window, self.worker, self.automation = window, None, None
        self.last_report = None
        self._last_log_signature = None
        self._last_log_state = None
        self._last_log_at = 0.0
        layout = QVBoxLayout(self)
        description = QLabel("Tenta obter um Sugar Lump Dourado ou Caramelizado. Pausa as outras automações durante as tentativas.")
        description.setWordWrap(True)
        layout.addWidget(description)
        group = QGroupBox("Sugar Lumps desejados")
        form = QFormLayout(group)
        targets = QHBoxLayout()
        self.golden = QCheckBox("Dourado")
        self.caramelized = QCheckBox("Caramelizado")
        for checkbox, key in ((self.golden, 'save_scum_golden'), (self.caramelized, 'save_scum_caramelized')):
            checkbox.setChecked(getattr(automation_config, key))
            checkbox.setToolTip("Encerra as tentativas quando o próximo lump tiver este tipo. Será preservado até a colheita garantida.")
            checkbox.toggled.connect(self.save_settings)
            targets.addWidget(checkbox)
        form.addRow("Tipos desejados", targets)
        self.limit = ScrollSafeSpinBox()
        self.limit.setRange(1, 100000)
        self.limit.setValue(automation_config.save_scum_max_attempts)
        self.limit.setToolTip("Ao atingir o limite, restaura o backup inicial e desliga. Não é uma garantia de encontrar o alvo.")
        self.limit.valueChanged.connect(self.save_settings)
        form.addRow("Máximo de tentativas", self.limit)
        self.interval = ScrollSafeDoubleSpinBox()
        self.interval.setRange(0.05, 10)
        self.interval.setDecimals(2)
        self.interval.setSuffix(" s")
        self.interval.setValue(automation_config.save_scum_interval_seconds)
        self.interval.setToolTip("Pausa entre tentativas. O instante da colheita precisa mudar para variar o sorteio.")
        self.interval.valueChanged.connect(self.save_settings)
        form.addRow("Intervalo", self.interval)
        layout.addWidget(group)
        note = QLabel("Comece com o Sugar Lump maduro e pelo menos 30 segundos antes da colheita automática.")
        note.setWordWrap(True)
        note.setToolTip("Antes da colheita garantida, a coleta tem 50% de chance de não render Sugar Lumps. Se o tipo atual já for um dos desejados, nenhuma tentativa é feita.")
        layout.addWidget(note)
        self.status = QLabel("Desligada")
        self.status.setWordWrap(True)
        self.backup = QLabel("Backup inicial: —")
        self.backup.setWordWrap(True)
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        layout.addWidget(self.status)
        layout.addWidget(self.backup)
        layout.addWidget(self.logs, 1)
        controls = QHBoxLayout()
        self.preview = QPushButton("Consultar estado")
        self.preview.setToolTip("Consulta o tipo do Sugar Lump e se ele já pode ser colhido, sem realizar uma tentativa.")
        self.preview.clicked.connect(self.refresh)
        self.recover = QPushButton("Restaurar backup inicial")
        self.recover.setToolTip("Restaura o backup inicial após uma tentativa interrompida. Use se a recuperação estiver pendente.")
        self.recover.setEnabled(False)
        self.recover.clicked.connect(lambda: self.launch(self.automation, 'recover'))
        self.toggle = AutomationControl("Save Scum")
        self.toggle.setToolTip("Salva o jogo antes de colher. Se o próximo Sugar Lump não for um dos tipos escolhidos, restaura e tenta novamente. Ao encontrar um tipo desejado, salva o resultado e desliga.")
        self.toggle.requested.connect(self.request)
        controls.addWidget(self.preview)
        controls.addWidget(self.recover)
        controls.addStretch()
        controls.addWidget(self.toggle)
        layout.addLayout(controls)

    def save_settings(self, *_):
        automation_config.save_scum_golden = self.golden.isChecked()
        automation_config.save_scum_caramelized = self.caramelized.isChecked()
        automation_config.save_scum_max_attempts = self.limit.value() if hasattr(self, 'limit') else automation_config.save_scum_max_attempts
        automation_config.save_scum_interval_seconds = self.interval.value() if hasattr(self, 'interval') else automation_config.save_scum_interval_seconds
        save_automation_settings()

    def configuration(self):
        return SaveScumConfig(tuple(t for t, enabled in ((2, self.golden.isChecked()), (4, self.caramelized.isChecked())) if enabled), self.limit.value(), self.interval.value())

    def refresh(self):
        if not self.window.bridge or self.worker or self.window._save_scum_exclusive:
            return
        self.launch(SaveScumAutomation(self.window.bridge, self.window.backup_manager, self.configuration()), 'preview')

    def request(self, enabled):
        if not enabled:
            if self.automation and self.worker:
                self.toggle.set_stopping()
                self.automation.parar()
            return
        if not self.window._bot_enabled:
            self.display_error("Ligue o bot no topo antes de iniciar Save Scum.")
            return
        if self.worker:
            return
        config = self.configuration()
        if not config.targets:
            self.display_error("Selecione Dourado e/ou Caramelizado.")
            return
        if not self.window._acquire_save_scum():
            return
        for target in config.targets:
            setattr(automation_config, f'preserve_sugar_lump_type_{target}', True)
            checkbox = self.window._preserve_checkboxes[target]
            checkbox.setChecked(True)
        self.save_settings()
        self.launch(SaveScumAutomation(self.window.bridge, self.window.backup_manager, config), 'run')

    def launch(self, automation, mode):
        if not automation or self.worker:
            return
        self.automation = automation
        self.last_report = None
        self.worker = SaveScumWorker(automation, mode, self)
        self.worker.updated.connect(self.display)
        self.worker.completed.connect(self.display)
        self.worker.failed.connect(self.display_error)
        self.worker.finished.connect(self.finished)
        for widget in (self.golden, self.caramelized, self.limit, self.interval, self.preview, self.recover):
            widget.setEnabled(False)
        self.toggle.set_running(mode == 'run')
        self.toggle.setEnabled(mode == 'run')
        self.worker.start()

    def display(self, report):
        self.last_report = report
        text = f"{report.state} | Tentativas: {report.attempts} | {report.message}"
        self.status.setText(text)
        self.backup.setText("Backup inicial: " + (Path(report.backup_path).name if report.backup_path else "—"))
        self.backup.setToolTip(report.backup_path)
        signature = (report.state, report.attempts, report.message)
        now = time.monotonic()
        if signature == self._last_log_signature:
            return
        if report.state == "rodando" and self._last_log_state == report.state and now - self._last_log_at < 5:
            logger.debug("Save Scum: %s", text)
            return
        self._last_log_signature, self._last_log_state, self._last_log_at = signature, report.state, now
        self.logs.append(text)
        self.logs.document().setMaximumBlockCount(500)
        log = logger.error if not report.safe_to_resume or report.state == "erro" else logger.info
        log("Save Scum: %s", text)

    def display_error(self, message):
        if self.worker:
            self.last_report = None
        self.status.setText("Erro: " + message)
        logger.error("Save Scum: %s", message)

    def finished(self):
        worker, self.worker = self.worker, None
        pending = self.window._save_scum_exclusive and (self.last_report is None or not self.last_report.safe_to_resume)
        self.toggle.set_running(False)
        self.toggle.setEnabled(not pending)
        for widget in (self.golden, self.caramelized, self.limit, self.interval, self.preview):
            widget.setEnabled(not pending)
        self.recover.setEnabled(pending)
        if pending:
            self.window.backups_button.setEnabled(True)
        if not pending:
            self.window._release_save_scum()
        if worker:
            worker.deleteLater()

        self.window.refresh_bot_control()

    def manual_recovery(self):
        self.display(SaveScumReport("restaurado", "Backup carregado. Tentativas encerradas."))
        self.finished()

    def shutdown(self):
        if self.worker and self.worker.isRunning():
            self.automation.parar()
            return self.worker.wait(20000)
        return True
