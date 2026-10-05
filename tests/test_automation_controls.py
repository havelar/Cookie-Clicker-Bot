"""Transições reais dos controles compartilhados, sem conectar ao jogo."""
import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication, QCheckBox, QMessageBox
from app.ui.main_window import MainWindow


class AutomationControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.patches = [patch('app.ui.main_window.save_automation_settings'),
                        patch('app.ui.main_window.QTimer.singleShot'),
                        patch.object(MainWindow, '_set_combo_keep_awake')]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.window = MainWindow()
        self.addCleanup(self.close_window)

    def close_window(self):
        for name in ('_combo_worker', '_auto_ascension_worker', '_stock_worker', '_garden_worker'):
            setattr(self.window, name, None)
        self.window.close()

    def connect_fakes(self):
        self.window.bridge = Mock()
        self.window.runner = Mock()
        self.window.backup_manager = Mock()
        self.window.stock_automation = Mock()
        self.window.fazendeira = Mock()

    def test_all_controls_start_off_and_no_execution_permission_checkbox_remains(self):
        for name in ('stock', 'garden', 'combo', 'simple_farm', 'auto_ascension'):
            control = getattr(self.window, name + '_toggle')
            self.assertEqual(control.button.text(), 'Ligar')
            self.assertEqual(control.status.text(), 'Desligada')
            self.assertFalse(control.running)
        texts = [c.text().lower() for c in self.window.findChildren(QCheckBox)]
        self.assertFalse(any('real' in t or 'simulação' in t for t in texts))

    def test_missing_connection_never_claims_running(self):
        for name in ('stock', 'garden', 'combo', 'simple_farm', 'auto_ascension'):
            control = getattr(self.window, name + '_toggle')
            control.button.click()
            self.assertFalse(control.running)
            self.assertEqual(control.button.text(), 'Ligar')

    def test_worker_modes_toggle_on_stopping_and_off_after_finish(self):
        self.connect_fakes()
        for name, worker_name, finish in (
            ('simple_farm', 'ComboWorker', lambda: self.window._simple_farm_finished(False)),
            ('combo', 'ComboWorker', lambda: self.window._combo_finished(False)),
            ('auto_ascension', 'AutoAscensaoWorker', self.window._auto_ascension_finished),
        ):
            with self.subTest(name=name), patch('app.ui.main_window.' + worker_name) as factory, \
                    patch('app.ui.main_window.QMessageBox.question', return_value=QMessageBox.Yes), \
                    patch('app.ui.main_window.QMessageBox.warning', return_value=QMessageBox.Yes):
                worker = factory.return_value
                worker.isRunning.return_value = True
                control = getattr(self.window, name + '_toggle')
                control.button.click()
                worker.start.assert_called_once()
                self.assertTrue(control.running)
                self.assertEqual(control.button.text(), 'Desligar')
                control.button.click()
                worker.stop.assert_called_once()
                self.assertEqual(control.status.text(), 'Desligando…')
                self.assertFalse(control.button.isEnabled())
                finish()
                self.assertFalse(control.running)
                self.assertEqual(control.button.text(), 'Ligar')

    def test_cancelled_confirmation_and_failed_backup_stay_off(self):
        self.connect_fakes()
        with patch('app.ui.main_window.QMessageBox.question', return_value=QMessageBox.No), \
                patch('app.ui.main_window.QMessageBox.warning', return_value=QMessageBox.No):
            self.window.combo_toggle.button.click()
            self.window.auto_ascension_toggle.button.click()
        self.assertFalse(self.window.combo_toggle.running)
        self.assertFalse(self.window.auto_ascension_toggle.running)
        self.window.bridge.get_game_save.return_value = None
        self.window.simple_farm_toggle.button.click()
        self.assertFalse(self.window.simple_farm_toggle.running)
        self.window.runner.release_simple_farm.assert_called_once()

    def test_preview_never_turns_on_automation(self):
        self.connect_fakes()
        with patch('app.ui.main_window.ComboWorker') as factory:
            self.window.simple_farm_preview_button.click()
            self.assertTrue(factory.call_args.args[1])
            self.assertFalse(self.window.simple_farm_toggle.running)
            self.assertFalse(self.window.simple_farm_toggle.isEnabled())
            self.window._simple_farm_finished(True)
            self.assertTrue(self.window.simple_farm_toggle.isEnabled())
        self.window.runner.acquire_simple_farm.assert_not_called()

    def test_periodic_modes_stop_pending_cycle_and_finish_off(self):
        self.connect_fakes()
        for name, timer, task, finished, automation in (
            ('stock', self.window._on_stock_market_timer, '_run_stock_task',
             self.window._stock_task_finished, self.window.stock_automation),
            ('garden', self.window._on_garden_timer, '_run_garden_task',
             self.window._garden_task_finished, self.window.fazendeira),
        ):
            with self.subTest(name=name), patch.object(self.window, task) as run_task:
                control = getattr(self.window, name + '_toggle')
                control.button.click()
                self.assertTrue(control.running)
                timer()
                operation = run_task.call_args.args[0]
                setattr(self.window, '_' + name + '_worker', Mock())
                control.button.click()
                self.assertTrue(control.stopping)
                operation()
                self.assertTrue(automation.run_cycle.call_args.kwargs['should_stop']())
                finished()
                self.assertFalse(control.running)
                self.assertEqual(control.status.text(), 'Desligada')

    def test_periodic_modes_can_be_turned_off_while_combo_has_paused_them(self):
        self.connect_fakes()
        self.window.stock_toggle.button.click()
        self.window.garden_toggle.button.click()
        self.window._combo_exclusive = True
        self.window._set_combo_busy(True, False)
        for control in (self.window.stock_toggle, self.window.garden_toggle):
            self.assertEqual(control.status.text(), 'Pausada pelo Combo')
            control.button.click()
            self.assertFalse(control.running)
        self.window._combo_exclusive = False
        self.window._set_combo_busy(False, False)
        self.assertFalse(self.window.stock_toggle.running)
        self.assertFalse(self.window.garden_toggle.running)


if __name__ == '__main__':
    unittest.main()
