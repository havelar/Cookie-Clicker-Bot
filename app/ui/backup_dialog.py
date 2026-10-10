"""Backups diretamente no jogo, sem clipboard ou campos de save."""
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem, QLineEdit, QMessageBox, QFileDialog
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from app.core.backup_service import BackupService, BackupResult

class BackupWorker(QThread):
    completed = pyqtSignal(object)
    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation
    def run(self):
        try:
            self.completed.emit(self.operation())
        except Exception as error:
            self.completed.emit(BackupResult(False, str(error), safe_to_resume=False))

class BackupDialog(QDialog):
    backup_restored = pyqtSignal(str)  # Compatibilidade; não transporta mais saves pelo clipboard.

    def __init__(self, backup_manager, parent=None, *, get_bridge=None, acquire_restore=None, finish_restore=None):
        super().__init__(parent)
        self.backup_manager = backup_manager
        self.get_bridge = get_bridge or (lambda: getattr(parent, 'bridge', None))
        self.acquire_restore = acquire_restore or (lambda: True)
        self.finish_restore = finish_restore or (lambda result: None)
        self.worker = None
        self.operation = ''
        self.result = None
        self.undo_backup = None
        self.setWindowTitle('Backups do jogo')
        self.setModal(False)
        self.resize(720, 520)
        self.setup_ui()
        self.refresh_backup_list()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        hint = QLabel('Salve o jogo aberto em um clique. Para carregar, selecione um backup da lista. O estado atual é salvo antes de cada carga.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        create = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText('Nome opcional — padrão: Backup + data e hora')
        self.name_input.returnPressed.connect(self.on_create_backup)
        self.create_btn = QPushButton('Salvar jogo agora')
        self.create_btn.setObjectName('primaryButton')
        self.create_btn.setToolTip('Captura o save diretamente do jogo; não usa o clipboard.')
        self.create_btn.clicked.connect(self.on_create_backup)
        create.addWidget(self.name_input, 1)
        create.addWidget(self.create_btn)
        layout.addLayout(create)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Buscar por nome ou data…')
        self.search_input.textChanged.connect(self.filter_list)
        layout.addWidget(self.search_input)
        self.backup_list = QListWidget()
        self.backup_list.currentItemChanged.connect(self.update_selection)
        self.backup_list.itemDoubleClicked.connect(lambda item: self.on_restore_backup())
        layout.addWidget(self.backup_list, 1)
        self.details = QLabel('Nenhum backup selecionado.')
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        actions = QHBoxLayout()
        self.restore_btn = QPushButton('Carregar no jogo')
        self.restore_btn.setObjectName('primaryButton')
        self.restore_btn.setToolTip('Carrega o backup selecionado. Antes, salva o estado atual para permitir desfazer.')
        self.restore_btn.clicked.connect(self.on_restore_backup)
        self.undo_btn = QPushButton('Desfazer carga')
        self.undo_btn.clicked.connect(self.on_undo_restore)
        self.delete_btn = QPushButton('Excluir')
        self.delete_btn.clicked.connect(self.on_delete_backup)
        self.refresh_btn = QPushButton('Atualizar')
        self.refresh_btn.clicked.connect(self.refresh_backup_list)
        self.import_btn = QPushButton('Adicionar arquivo…')
        self.import_btn.setToolTip('Adiciona um arquivo de save existente à lista, sem copiar ou colar texto.')
        self.import_btn.clicked.connect(self.on_import_file)
        for button in (self.restore_btn, self.undo_btn, self.delete_btn, self.import_btn, self.refresh_btn):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.status_label = QLabel('')
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.close_btn = QPushButton('Fechar')
        self.close_btn.clicked.connect(self.close)
        layout.addWidget(self.close_btn, alignment=Qt.AlignRight)

    def showEvent(self, event):
        if not self.worker:
            self.refresh_backup_list()
        super().showEvent(event)

    def set_status(self, message, error=False):
        self.status_label.setText(message)
        self.status_label.setStyleSheet('color: #f07883;' if error else 'color: #65d6a5;')

    def refresh_backup_list(self, select_path=None):
        if self.worker:
            return
        current = self.get_selected_backup()
        keep = str(select_path or (current.file_path if current else ''))
        self.backup_list.clear()
        backups = self.backup_manager.list_backups()
        selected = None
        for backup in backups:
            item = QListWidgetItem(backup.display_name)
            item.setData(Qt.UserRole, backup)
            item.setToolTip(str(backup.file_path))
            self.backup_list.addItem(item)
            if str(backup.file_path) == keep:
                selected = item
        self.filter_list()
        if selected and not selected.isHidden():
            self.backup_list.setCurrentItem(selected)
        self.update_selection()
        if not backups:
            self.details.setText('Nenhum backup salvo. Use Salvar jogo agora.')
        self.set_status(f'{len(backups)} backup(s) · Mais recentes primeiro')

    def filter_list(self, *_):
        query = self.search_input.text().strip().casefold()
        first = None
        for i in range(self.backup_list.count()):
            item = self.backup_list.item(i)
            item.setHidden(query not in item.text().casefold())
            if not item.isHidden() and first is None:
                first = item
        current = self.backup_list.currentItem()
        if not current or current.isHidden():
            self.backup_list.setCurrentItem(first)
        self.update_selection()

    def get_selected_backup(self):
        item = self.backup_list.currentItem()
        return item.data(Qt.UserRole) if item and not item.isHidden() else None

    def update_selection(self, *_):
        backup = self.get_selected_backup()
        self.restore_btn.setEnabled(bool(backup) and self.worker is None)
        self.delete_btn.setEnabled(bool(backup) and self.worker is None)
        self.undo_btn.setEnabled(self.undo_backup is not None and self.worker is None)
        if backup:
            self.details.setText(f'Selecionado: {backup.name} · {backup.timestamp:%d/%m/%Y %H:%M:%S}')
        else:
            self.details.setText('Nenhum backup corresponde à busca.' if self.search_input.text() else 'Nenhum backup selecionado.')

    def start_operation(self, operation, kind):
        if self.worker:
            return
        self.operation, self.result = kind, None
        self.worker = BackupWorker(operation, self)
        self.worker.completed.connect(self.operation_completed)
        self.worker.finished.connect(self.operation_finished)
        for widget in (self.name_input, self.create_btn, self.search_input, self.backup_list, self.restore_btn, self.undo_btn, self.delete_btn, self.import_btn, self.refresh_btn):
            widget.setEnabled(False)
        self.set_status('Carregando e verificando o save…' if kind == 'restore' else 'Salvando backup…')
        self.worker.start()

    def service(self):
        bridge = self.get_bridge()
        if not bridge:
            self.set_status('Jogo desconectado. Conecte a bridge antes de salvar ou carregar.', True)
            return None
        return BackupService(bridge, self.backup_manager)

    def on_create_backup(self):
        service = self.service()
        if service:
            name = self.name_input.text().strip()
            self.start_operation(lambda: service.capture(name), 'capture')

    def on_restore_backup(self):
        self.restore(self.get_selected_backup())

    def restore(self, backup):
        if self.worker or not backup:
            return
        service = self.service()
        if service and self.acquire_restore():
            protected = (self.undo_backup.file_path,) if self.undo_backup else ()
            self.start_operation(lambda: service.restore(backup, protect_paths=protected), 'restore')

    def on_undo_restore(self):
        self.restore(self.undo_backup)

    def on_import_file(self):
        if self.worker:
            return
        file_path, _ = QFileDialog.getOpenFileName(self, 'Adicionar save à lista', '', 'Saves (*.txt);;Todos os arquivos (*)')
        if file_path:
            service = BackupService(self.get_bridge(), self.backup_manager)
            name = self.name_input.text().strip()
            self.start_operation(lambda: service.import_file(file_path, name), 'import')

    def operation_completed(self, result):
        self.result = result

    def operation_finished(self):
        worker, self.worker = self.worker, None
        result = self.result or BackupResult(False, 'A operação terminou sem confirmação.', safe_to_resume=False)
        kind = self.operation
        for widget in (self.name_input, self.create_btn, self.search_input, self.backup_list, self.import_btn, self.refresh_btn):
            widget.setEnabled(True)
        if kind == 'restore':
            if result.ok:
                self.undo_backup = result.recovery
            self.finish_restore(result)
        elif result.ok:
            self.name_input.clear()
            self.search_input.clear()
        self.refresh_backup_list(result.backup.file_path if result.backup else None)
        self.set_status(result.message, not result.ok)
        if kind == 'restore' and not result.safe_to_resume and result.recovery and self.undo_backup is None:
            self.undo_backup = result.recovery
        self.update_selection()
        if worker:
            worker.deleteLater()

    def on_delete_backup(self):
        backup = self.get_selected_backup()
        if self.worker or not backup:
            return
        if QMessageBox.question(self, 'Excluir backup', f'Excluir {backup.display_name}?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if self.backup_manager.delete_backup(backup):
            if self.undo_backup and self.undo_backup.file_path == backup.file_path:
                self.undo_backup = None
            self.refresh_backup_list()
            self.set_status('Backup excluído.')
        else:
            self.set_status('Não foi possível excluir o arquivo.', True)

    def shutdown(self):
        return self.worker.wait(20000) if self.worker and self.worker.isRunning() else True

    def closeEvent(self, event):
        if self.worker:
            event.ignore()
            self.set_status('Aguarde a operação terminar antes de fechar.')
            return
        super().closeEvent(event)
