"""Controles de Save Scum e preferências persistidas, com Qt offscreen."""
import copy
import os
import unittest
from unittest.mock import Mock, patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt5.QtWidgets import QApplication
from app.ui.main_window import MainWindow
from app.core.save_scum import SaveScumReport
from app.config.settings import automation_config, load_automation_settings, save_automation_settings

class SaveScumUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.previous=copy.deepcopy(automation_config.__dict__)
        self.addCleanup(lambda:automation_config.__dict__.update(self.previous))
        self.patches=[patch('app.ui.save_scum_tab.save_automation_settings'),patch('app.ui.main_window.save_automation_settings'),patch('app.ui.main_window.QTimer.singleShot')]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        self.window=MainWindow()
        self.tab=self.window.save_scum_tab
        self.addCleanup(self.close)
    def close(self):
        self.tab.worker=None
        self.window._stock_worker=self.window._garden_worker=None
        self.window._save_scum_exclusive=False
        self.window.close()
    def connect(self):
        self.window.bridge=Mock()
        self.window.runner=Mock()
        self.window.runner.is_running=True
        self.window.runner.acquire_exclusive.return_value=True
    def test_tab_starts_off_and_missing_bridge_does_not_start(self):
        self.assertIn('Save Scum',[self.window.tabs.tabText(i) for i in range(self.window.tabs.count())])
        self.assertFalse(self.tab.toggle.running)
        self.tab.toggle.button.click()
        self.assertFalse(self.tab.toggle.running)
        self.assertIn('indisponível',self.tab.status.text())
    def test_start_pauses_market_garden_detector_and_preserves_targets(self):
        self.connect()
        self.window.stock_toggle.set_running(True)
        self.window.garden_toggle.set_running(True)
        with patch('app.ui.save_scum_tab.SaveScumWorker') as factory:
            self.tab.request(True)
            self.assertTrue(self.window._save_scum_exclusive)
            self.assertEqual(self.window.runner.acquire_exclusive.call_args.args,('save_scum',))
            self.assertIn('Save Scum',self.window.stock_toggle.status.text())
            self.assertFalse(self.window.stock_toggle.isEnabled())
            self.assertTrue(automation_config.preserve_sugar_lump_type_2)
            self.assertTrue(automation_config.preserve_sugar_lump_type_4)
            self.assertTrue(self.tab.toggle.running)
            factory.return_value.start.assert_called_once()
            self.tab.request(False)
            self.assertTrue(self.tab.automation.stop.is_set())
            self.assertEqual(self.tab.toggle.status.text(),'Desligando…')
            self.tab.display(SaveScumReport('desligada','Restaurado'))
            self.tab.finished()
            self.assertFalse(self.window._save_scum_exclusive)
            self.window.runner.release_exclusive.assert_called_once_with('save_scum')
            self.window.runner.ensure_clicker_running.assert_called_once()
    def test_failed_restore_retains_pause_and_enables_recovery(self):
        self.connect()
        self.window._acquire_save_scum()
        self.tab.worker=Mock()
        self.tab.display(SaveScumReport('restauração pendente','Falha',safe_to_resume=False))
        self.tab.finished()
        self.assertTrue(self.window._save_scum_exclusive)
        self.assertTrue(self.tab.recover.isEnabled())
        self.assertFalse(self.tab.toggle.isEnabled())
        self.window.runner.release_exclusive.assert_not_called()
        self.tab.worker=Mock()
        self.tab.display(SaveScumReport('restaurado','OK'))
        self.tab.finished()
        self.assertFalse(self.window._save_scum_exclusive)
    def test_active_worker_blocks_other_starts_and_manual_restore(self):
        self.connect()
        self.window._combo_worker=Mock()
        self.window._combo_worker.isRunning.return_value=True
        self.assertFalse(self.window._acquire_save_scum())
        self.window._combo_worker=None
        self.window._save_scum_exclusive=True
        self.window.on_backup_restored('other save')
        self.window.runner.bridge.load_game_save.assert_not_called()
    def test_manual_backup_recovers_pending_session(self):
        self.connect()
        self.window._acquire_save_scum()
        self.tab.last_report=SaveScumReport("restauração pendente","Falha",safe_to_resume=False)
        self.window.bridge.load_game_save.return_value=True
        self.window.on_backup_restored("manual backup")
        self.window.bridge.load_game_save.assert_called_once_with("manual backup")
        self.assertFalse(self.window._save_scum_exclusive)
        self.assertFalse(self.tab.recover.isEnabled())
        self.assertTrue(self.tab.toggle.isEnabled())

    def test_no_targets_never_acquires_exclusivity(self):
        self.connect()
        self.tab.golden.setChecked(False)
        self.tab.caramelized.setChecked(False)
        self.tab.request(True)
        self.window.runner.acquire_exclusive.assert_not_called()

class SaveScumSettingsTests(unittest.TestCase):
    def test_settings_roundtrip(self):
        previous=copy.deepcopy(automation_config.__dict__)
        self.addCleanup(lambda:automation_config.__dict__.update(previous))
        values={}
        class Settings:
            def __init__(self,*args):pass
            def beginGroup(self,*args):pass
            def endGroup(self):pass
            def sync(self):pass
            def setValue(self,k,v):values[k]=v
            def value(self,k,default=None,type=None):return values.get(k,default)
        with patch('app.config.settings.QSettings',Settings):
            automation_config.save_scum_golden=False
            automation_config.save_scum_caramelized=True
            automation_config.save_scum_max_attempts=321
            automation_config.save_scum_interval_seconds=0.15
            save_automation_settings()
            automation_config.save_scum_golden=True
            automation_config.save_scum_max_attempts=1
            load_automation_settings()
            self.assertFalse(automation_config.save_scum_golden)
            self.assertTrue(automation_config.save_scum_caramelized)
            self.assertEqual(automation_config.save_scum_max_attempts,321)
            self.assertEqual(automation_config.save_scum_interval_seconds,0.15)
