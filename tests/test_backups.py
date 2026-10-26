"""Backups integrados: arquivos temporários e bridge falsa, sem restaurar o jogo."""
import base64
import copy
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from app.config.settings import backup_config
from app.core.backup_manager import BackupManager
from app.core.backup_service import BackupService, BackupResult
from app.models.backup import BackupEntry


def save(seed):
    return base64.b64encode(f'2.053||100;200;300;Bakery;{seed}||0|'.encode()).decode()+'!END!'

class BackupManagerTests(unittest.TestCase):
    def setUp(self):
        previous=copy.deepcopy(backup_config.__dict__)
        self.addCleanup(lambda:backup_config.__dict__.update(previous))
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        backup_config.backup_folder=str(Path(self.temp.name)/'nested'/'backups')
        backup_config.max_backups=50
        self.manager=BackupManager()
    def test_unnamed_backups_are_unique_and_roundtrip(self):
        first=self.manager.create_backup(save('first'))
        second=self.manager.create_backup(save('second'))
        self.assertEqual(first.name,'Backup')
        self.assertNotEqual(first.file_path,second.file_path)
        self.assertEqual(len(self.manager.list_backups()),2)
        self.assertEqual(self.manager.load_backup_data(first),save('first'))
        self.assertEqual(BackupEntry.from_file(first.file_path).timestamp,first.timestamp)
    def test_same_timestamp_does_not_overwrite(self):
        with patch("app.core.backup_manager.datetime") as clock:
            clock.now.return_value=datetime(2026,10,9,10,20,30,123456)
            first=self.manager.create_backup(save("first"),"Same")
            second=self.manager.create_backup(save("second"),"Same")
        self.assertNotEqual(first.file_path,second.file_path)
        self.assertEqual(self.manager.load_backup_data(first),save("first"))
        self.assertEqual(self.manager.load_backup_data(second),save("second"))

    def test_old_filename_still_loads(self):
        file=self.manager.backup_dir/'backup_2026-10-09_14-20-30_Antigo.txt'
        file.write_text(save('old'),encoding='utf-8')
        entry=self.manager.list_backups()[0]
        self.assertEqual(entry.name,'Antigo')
        self.assertEqual(entry.timestamp,datetime(2026,10,9,14,20,30))
    def test_name_cannot_escape_folder_and_empty_save_is_rejected(self):
        entry=self.manager.create_backup(save('safe'),'../../nome:com?barras')
        self.assertEqual(entry.file_path.parent,self.manager.backup_dir)
        self.assertNotIn('/',entry.name)
        self.assertNotIn(':',entry.name)
        with self.assertRaises(ValueError):self.manager.create_backup('','')
        outsider=BackupEntry('outside',datetime.now(),Path(self.temp.name)/'outside.txt')
        outsider.file_path.write_text('keep',encoding='utf-8')
        self.assertFalse(self.manager.delete_backup(outsider))
        self.assertTrue(outsider.file_path.exists())
    def test_retention_keeps_selected_and_recovery_even_with_limit_one(self):
        selected=self.manager.create_backup(save('target'),'selected')
        self.manager.create_backup(save('old'),'old')
        backup_config.max_backups=1
        recovery=self.manager.create_backup(save('current'),'recovery',protect_paths=(selected.file_path,))
        self.assertTrue(selected.file_path.exists())
        self.assertTrue(recovery.file_path.exists())
        self.assertEqual(len(self.manager.list_backups()),2)
    def test_zero_limit_never_deletes_just_created_backup(self):
        backup_config.max_backups=0
        self.assertTrue(self.manager.create_backup(save('x')).file_path.exists())

class BackupServiceTests(unittest.TestCase):
    def setUp(self):
        self.bridge=Mock()
        self.manager=Mock()
        self.service=BackupService(self.bridge,self.manager)
        self.selected=BackupEntry('Selected',datetime.now(),Path('selected.txt'))
        self.manager.load_backup_data.return_value=save('selected')
        self.manager.create_backup.return_value=BackupEntry('Recovery',datetime.now(),Path('recovery.txt'))
        self.bridge.get_game_save.side_effect=[save('current'),save('selected')]
        self.bridge.load_game_save.return_value=True
        self.bridge.persist_game_save.return_value=True
    def test_capture_gets_runtime_save_without_clipboard_and_allows_blank_name(self):
        self.bridge.get_game_save.side_effect=None
        self.bridge.get_game_save.return_value=save('current')
        result=self.service.capture()
        self.assertTrue(result.ok)
        self.manager.create_backup.assert_called_once_with(save('current'),'')
    def test_restore_saves_current_state_first_and_persists_selected(self):
        result=self.service.restore(self.selected)
        self.assertTrue(result.ok)
        self.manager.create_backup.assert_called_once_with(save('current'),'antes-da-restauracao',protect_paths=(self.selected.file_path,))
        self.bridge.load_game_save.assert_called_once_with(save('selected'))
        self.bridge.persist_game_save.assert_called_once()
        self.assertIsNotNone(result.recovery)
    def test_backup_failure_never_imports(self):
        self.manager.create_backup.side_effect=OSError('disk full')
        self.assertFalse(self.service.restore(self.selected).ok)
        self.bridge.load_game_save.assert_not_called()
    def test_invalid_save_and_disconnection_never_import(self):
        self.manager.load_backup_data.return_value='garbage'
        self.assertFalse(self.service.restore(self.selected).ok)
        self.bridge.load_game_save.assert_not_called()
        self.bridge.get_game_save.side_effect=None
        self.bridge.get_game_save.return_value=None
        self.assertFalse(self.service.capture().ok)
    def test_failed_import_rolls_back_before_resuming(self):
        self.bridge.load_game_save.side_effect=[False,True]
        self.bridge.get_game_save.side_effect=[save('current'),save('current')]
        result=self.service.restore(self.selected)
        self.assertFalse(result.ok)
        self.assertTrue(result.safe_to_resume)
        self.assertEqual(self.bridge.load_game_save.call_args_list[-1].args,(save('current'),))
    def test_mismatched_import_and_failed_rollback_hold_other_automations(self):
        self.bridge.load_game_save.side_effect=[True,False]
        self.bridge.get_game_save.side_effect=[save('current'),save('wrong')]
        result=self.service.restore(self.selected)
        self.assertFalse(result.ok)
        self.assertFalse(result.safe_to_resume)
        self.assertIsNotNone(result.recovery)
    def test_file_import_works_offline_without_clipboard(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'Original.txt'
            source.write_text(save('file'),encoding='utf-8-sig')
            result=BackupService(None,self.manager).import_file(source)
            self.assertTrue(result.ok)
            self.manager.create_backup.assert_called_once_with(save('file'),'Original')
