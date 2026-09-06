from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QTextEdit, QCheckBox,
    QMessageBox, QGroupBox, QSplitter, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from app.core.backup_manager import BackupManager
from app.models.backup import BackupEntry
from app.utils.logger import logger

from typing import Optional


class BackupDialog(QDialog):
    """Dialog for managing save backups."""

    backup_restored = pyqtSignal(str)  # Emits save data when restored

    def __init__(self, backup_manager: BackupManager, parent=None):
        super().__init__(parent)
        self.backup_manager = backup_manager
        self.setWindowTitle("Gerenciar Backups de Save")
        self.setModal(False)
        self.resize(800, 600)

        self.setup_ui()
        self.refresh_backup_list()

    def setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # Splitter for list and form
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # Left side: Backup list
        list_group = QGroupBox("Backups Salvos")
        list_layout = QVBoxLayout(list_group)

        self.backup_list = QListWidget()
        self.backup_list.itemDoubleClicked.connect(self.on_backup_double_clicked)
        list_layout.addWidget(self.backup_list)

        # List buttons
        list_buttons_layout = QHBoxLayout()
        self.restore_btn = QPushButton("Restaurar Selecionado")
        self.restore_btn.clicked.connect(self.on_restore_backup)
        self.delete_btn = QPushButton("Deletar Selecionado")
        self.delete_btn.clicked.connect(self.on_delete_backup)
        self.refresh_btn = QPushButton("Atualizar Lista")
        self.refresh_btn.clicked.connect(self.refresh_backup_list)

        list_buttons_layout.addWidget(self.restore_btn)
        list_buttons_layout.addWidget(self.delete_btn)
        list_buttons_layout.addStretch()
        list_buttons_layout.addWidget(self.refresh_btn)
        list_layout.addLayout(list_buttons_layout)

        splitter.addWidget(list_group)

        # Right side: Create backup form
        form_group = QGroupBox("Criar Novo Backup")
        form_layout = QVBoxLayout(form_group)

        # Name input
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Nome do Backup:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ex: Save Inicial, Antes do Update...")
        name_layout.addWidget(self.name_input)
        form_layout.addLayout(name_layout)

        # Auto clipboard checkbox
        self.auto_clipboard_cb = QCheckBox("Puxar automaticamente do clipboard")
        self.auto_clipboard_cb.setChecked(True)
        form_layout.addWidget(self.auto_clipboard_cb)

        # Save data input
        form_layout.addWidget(QLabel("Dados do Save (cole aqui):"))
        self.save_data_input = QTextEdit()
        self.save_data_input.setPlaceholderText("Cole o save string aqui (Ctrl+V)...")
        self.save_data_input.setFont(QFont("Courier New", 10))
        form_layout.addWidget(self.save_data_input)

        # Create button
        self.create_btn = QPushButton("Criar Backup")
        self.create_btn.clicked.connect(self.on_create_backup)
        self.create_btn.setStyleSheet("QPushButton { font-weight: bold; }")
        form_layout.addWidget(self.create_btn)

        splitter.addWidget(form_group)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: blue;")
        layout.addWidget(self.status_label)

        # Bottom buttons
        bottom_layout = QHBoxLayout()
        self.close_btn = QPushButton("Fechar")
        self.close_btn.clicked.connect(self.accept)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.close_btn)
        layout.addLayout(bottom_layout)

        # Set splitter proportions
        splitter.setSizes([400, 400])

    def refresh_backup_list(self):
        """Refresh the backup list."""
        self.backup_list.clear()
        backups = self.backup_manager.list_backups()

        if not backups:
            item = QListWidgetItem("Nenhum backup encontrado")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.backup_list.addItem(item)
            return

        for backup in backups:
            item = QListWidgetItem(backup.display_name)
            item.setData(Qt.UserRole, backup)
            self.backup_list.addItem(item)

        self.status_label.setText(f"{len(backups)} backup(s) encontrado(s)")

    def get_selected_backup(self) -> Optional[BackupEntry]:
        """Get the currently selected backup."""
        current_item = self.backup_list.currentItem()
        if current_item and current_item.data(Qt.UserRole):
            return current_item.data(Qt.UserRole)
        return None

    def on_create_backup(self):
        """Handle create backup button click."""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Erro", "Por favor, digite um nome para o backup.")
            return

        save_data = self.save_data_input.toPlainText().strip()
        if self.auto_clipboard_cb.isChecked():
            # Try to get from clipboard
            clipboard = QApplication.clipboard() if QApplication.instance() else None
            if clipboard:
                clipboard_text = clipboard.text().strip()
                if clipboard_text:
                    save_data = clipboard_text
                    self.save_data_input.setPlainText(save_data)
                else:
                    QMessageBox.warning(self, "Erro", "Clipboard vazio. Cole o save manualmente.")
                    return
            else:
                QMessageBox.warning(self, "Erro", "Não foi possível acessar o clipboard.")
                return

        if not save_data:
            QMessageBox.warning(self, "Erro", "Dados do save estão vazios.")
            return

        try:
            backup = self.backup_manager.create_backup(save_data, name)
            self.name_input.clear()
            self.save_data_input.clear()
            self.refresh_backup_list()
            self.status_label.setText(f"Backup criado: {backup.display_name}")
            QMessageBox.information(self, "Sucesso", f"Backup '{name}' criado com sucesso!")
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            QMessageBox.critical(self, "Erro", f"Falha ao criar backup: {str(e)}")

    def on_restore_backup(self):
        """Handle restore backup button click."""
        backup = self.get_selected_backup()
        if not backup:
            QMessageBox.warning(self, "Erro", "Selecione um backup para restaurar.")
            return

        reply = QMessageBox.question(
            self, "Confirmar Restauração",
            f"Tem certeza que deseja restaurar o save '{backup.name}'?\n"
            "Isso irá sobrescrever o save atual do jogo.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                save_data = self.backup_manager.load_backup_data(backup)

                # Copiar para clipboard
                clipboard = QApplication.clipboard()
                clipboard.setText(save_data)

                self.status_label.setText(f"Backup copiado para o Clipboard: {backup.display_name}")
                QMessageBox.information(self, "Sucesso", f"Backup '{backup.name}' preparado para restauração!")
            except Exception as e:
                logger.error(f"Failed to restore backup: {e}")
                QMessageBox.critical(self, "Erro", f"Falha ao restaurar backup: {str(e)}")

    def on_delete_backup(self):
        """Handle delete backup button click."""
        backup = self.get_selected_backup()
        if not backup:
            QMessageBox.warning(self, "Erro", "Selecione um backup para deletar.")
            return

        reply = QMessageBox.question(
            self, "Confirmar Exclusão",
            f"Tem certeza que deseja deletar o backup '{backup.name}'?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                if self.backup_manager.delete_backup(backup):
                    self.refresh_backup_list()
                    self.status_label.setText(f"Backup deletado: {backup.display_name}")
                    QMessageBox.information(self, "Sucesso", f"Backup '{backup.name}' deletado!")
                else:
                    QMessageBox.critical(self, "Erro", "Falha ao deletar backup.")
            except Exception as e:
                logger.error(f"Failed to delete backup: {e}")
                QMessageBox.critical(self, "Erro", f"Falha ao deletar backup: {str(e)}")

    def on_backup_double_clicked(self, item: QListWidgetItem):
        """Handle double click on backup item - restore."""
        self.on_restore_backup()