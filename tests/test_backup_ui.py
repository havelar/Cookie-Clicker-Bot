"""Tela de backups sem clipboard e coordenação da restauração, com Qt offscreen."""
import copy
import os
from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt5.QtWidgets import QApplication, QLineEdit, QTextEdit
from app.ui.backup_dialog import BackupDialog
from app.ui.main_window import MainWindow
from app.models.backup import BackupEntry
from app.core.backup_service import BackupResult

class BackupDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.manager=Mock()
        self.entries=[BackupEntry('Newest',datetime(2026,10,9,20),Path('new.txt')),BackupEntry('Older',datetime(2026,10,9,10),Path('old.txt'))]
        self.manager.list_backups.return_value=self.entries
        self.bridge=Mock()
        self.acquire=Mock(return_value=True)
        self.finish=Mock()
        self.dialog=BackupDialog(self.manager,get_bridge=lambda:self.bridge,acquire_restore=self.acquire,finish_restore=self.finish)
        self.addCleanup(self.close)
    def close(self):self.dialog.worker=None;self.dialog.close()
    def test_latest_selected_no_clipboard_or_save_text_input(self):
        self.assertEqual(self.dialog.get_selected_backup(),self.entries[0])
        self.assertFalse(self.dialog.findChildren(QTextEdit))
        self.assertEqual(len(self.dialog.findChildren(QLineEdit)),2)
        self.assertTrue(self.dialog.restore_btn.isEnabled())
    def test_search_filters_and_disables_actions_without_matches(self):
        self.dialog.search_input.setText('older')
        self.assertEqual(self.dialog.get_selected_backup(),self.entries[1])
        self.dialog.search_input.setText('missing')
        self.assertIsNone(self.dialog.get_selected_backup())
        self.assertFalse(self.dialog.restore_btn.isEnabled())
        self.assertFalse(self.dialog.delete_btn.isEnabled())
    def test_refresh_preserves_selection_and_selects_new_backup(self):
        self.dialog.backup_list.setCurrentRow(1)
        self.dialog.refresh_backup_list()
        self.assertEqual(self.dialog.get_selected_backup(),self.entries[1])
        self.dialog.refresh_backup_list(self.entries[0].file_path)
        self.assertEqual(self.dialog.get_selected_backup(),self.entries[0])
    def test_capture_blank_name_uses_bridge_in_worker(self):
        with patch('app.ui.backup_dialog.BackupWorker') as factory, patch('app.ui.backup_dialog.BackupService') as service:
            self.dialog.on_create_backup()
            factory.return_value.start.assert_called_once()
            operation=factory.call_args.args[0]
            operation()
            service.return_value.capture.assert_called_once_with('')
            service.assert_called_once_with(self.bridge,self.manager)
            self.assertFalse(self.dialog.create_btn.isEnabled())
    def test_restore_waits_for_exclusivity_and_finishes_after_worker_result(self):
        with patch('app.ui.backup_dialog.BackupWorker') as factory:
            self.dialog.on_restore_backup()
            self.acquire.assert_called_once()
            self.assertEqual(self.dialog.operation,'restore')
            recovery=self.entries[1]
            self.dialog.operation_completed(BackupResult(True,'loaded',self.entries[0],recovery))
            self.dialog.operation_finished()
            self.finish.assert_called_once()
            self.assertEqual(self.dialog.undo_backup,recovery)
            self.assertTrue(self.dialog.undo_btn.isEnabled())
            self.assertEqual(self.dialog.status_label.text(),'loaded')
    def test_capture_with_actual_worker_finishes_without_clipboard(self):
        import time
        from tests.test_backups import save
        self.bridge.get_game_save.return_value=save("current")
        self.manager.create_backup.return_value=self.entries[0]
        self.dialog.name_input.setText("Manual")
        with patch.object(QApplication, "clipboard", side_effect=AssertionError("Clipboard accessed")):
            self.dialog.on_create_backup()
            deadline=time.monotonic()+3
            while self.dialog.worker and time.monotonic()<deadline:
                QApplication.processEvents()
                time.sleep(0.005)
        self.assertIsNone(self.dialog.worker)
        self.assertEqual(self.dialog.name_input.text(),"")
        self.assertIn("Backup salvo",self.dialog.status_label.text())
        self.assertTrue(self.dialog.create_btn.isEnabled())

    def test_busy_or_denied_exclusivity_never_launches_duplicate_worker(self):
        self.acquire.return_value=False
        with patch('app.ui.backup_dialog.BackupWorker') as factory:
            self.dialog.on_restore_backup()
            factory.assert_not_called()
        self.dialog.worker=Mock()
        with patch('app.ui.backup_dialog.BackupWorker') as factory:
            self.dialog.on_create_backup()
            factory.assert_not_called()

class BackupCoordinationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.patch=patch('app.ui.main_window.QTimer.singleShot');self.patch.start();self.addCleanup(self.patch.stop)
        self.window=MainWindow()
        self.window._bot_enabled = True  # Fixture: bot global ligado para testar controles individuais.
        for name in ("clicker_button", "stock_toggle", "garden_toggle", "simple_farm_toggle", "combo_toggle", "auto_ascension_toggle"):
            getattr(self.window, name).setEnabled(True)
        self.window.save_scum_tab.toggle.setEnabled(True)
        self.window.bridge=Mock()
        self.window.runner=Mock()
        self.window.runner.is_running=True
        self.window.runner.acquire_exclusive.return_value=True
        self.window.backup_dialog=Mock()
        self.addCleanup(self.close)
    def close(self):
        self.window._save_scum_exclusive=False
        self.window.backup_dialog=None
        self.window.close()
    def test_restore_pauses_and_success_resumes(self):
        self.window.stock_toggle.set_running(True)
        self.assertTrue(self.window._acquire_backup_restore())
        self.window.runner.acquire_exclusive.assert_called_once_with('backup_restore')
        self.assertIn('Backups',self.window.stock_toggle.status.text())
        self.assertFalse(self.window.save_scum_tab.toggle.isEnabled())
        self.window._finish_backup_restore(BackupResult(True,'loaded'))
        self.assertFalse(self.window._save_scum_exclusive)
        self.window.runner.release_exclusive.assert_called_once_with('backup_restore')
        self.window.runner.ensure_clicker_running.assert_called_once()
    def test_failed_recovery_stays_paused_until_successful_load(self):
        self.assertTrue(self.window._acquire_backup_restore())
        self.window._finish_backup_restore(BackupResult(False,'rollback failed',safe_to_resume=False))
        self.assertTrue(self.window._save_scum_exclusive)
        self.window._finish_backup_restore(BackupResult(False,'another load rejected',safe_to_resume=True))
        self.assertTrue(self.window._save_scum_exclusive)
        self.window.runner.release_exclusive.assert_not_called()
        self.window._finish_backup_restore(BackupResult(True,'recovered'))
        self.assertFalse(self.window._save_scum_exclusive)
    def test_active_save_scum_blocks_restoration(self):
        self.window._save_scum_exclusive=True
        self.window._exclusive_session_owner='save_scum'
        self.window.save_scum_tab.worker=Mock()
        self.assertFalse(self.window._acquire_backup_restore())
        self.window.save_scum_tab.worker=None
