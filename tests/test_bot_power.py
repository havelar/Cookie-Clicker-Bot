"""Controle geral testado sem iniciar o jogo ou executar ações reais."""
import os
import unittest
from unittest.mock import Mock, patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication
from app.ui.main_window import MainWindow
from app.core.run import AutomationRunner
from main import Application

class BotPowerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.timer = patch('app.ui.main_window.QTimer.singleShot')
        self.timer.start()
        self.addCleanup(self.timer.stop)
        self.window = MainWindow()
        self.addCleanup(self.close)

    def close(self):
        self.window._stock_worker = self.window._garden_worker = None
        self.window._combo_worker = self.window._auto_ascension_worker = None
        self.window.save_scum_tab.worker = None
        self.window._save_scum_exclusive = False
        self.window.close()

    def connect(self):
        self.window.bridge = Mock()
        self.window.runner = Mock(is_running=False)
        self.window._game_open = True
        self.window.refresh_bot_control()

    def test_closed_open_and_enabled_button_states(self):
        self.assertEqual(self.window.open_game_button.text(), 'Abrir jogo')
        self.assertFalse(self.window.stock_toggle.isEnabled())
        self.connect()
        self.assertEqual(self.window.open_game_button.text(), 'Ligar bot')
        self.window.set_bot_enabled(True)
        self.assertEqual(self.window.open_game_button.text(), 'Desligar bot')
        self.assertTrue(self.window.stock_toggle.isEnabled())
        self.assertFalse(self.window.stock_toggle.running)
        self.window.runner.set_paused.assert_called_with(False)
        self.window.set_bot_enabled(False)
        self.assertEqual(self.window.open_game_button.text(), 'Ligar bot')
        self.window.runner.set_paused.assert_called_with(True)

    def test_pause_cancels_all_workers_and_preserves_periodic_selection(self):
        self.connect()
        self.window.set_bot_enabled(True)
        self.window.stock_toggle.set_running(True)
        self.window.garden_toggle.set_running(True)
        self.window._stock_stop.clear(); self.window._garden_stop.clear()
        stock_token, garden_token = self.window._stock_stop, self.window._garden_stop
        combo, ascension, scum = Mock(), Mock(), Mock()
        self.window._combo_worker = combo
        self.window._auto_ascension_worker = ascension
        self.window.save_scum_tab.worker = Mock()
        self.window.save_scum_tab.automation = scum
        self.window.set_bot_enabled(False)
        self.assertTrue(stock_token.is_set()); self.assertTrue(garden_token.is_set())
        combo.stop.assert_called(); ascension.stop.assert_called_once()
        scum.parar.assert_called_once()
        self.assertTrue(self.window.stock_toggle.running)
        self.assertTrue(self.window.garden_toggle.running)
        self.assertEqual(self.window.open_game_button.text(), 'Pausando…')
        self.assertFalse(self.window.open_game_button.isEnabled())
        self.window._combo_worker = self.window._auto_ascension_worker = None
        self.window.save_scum_tab.worker = None
        self.window.refresh_bot_control()
        self.window.set_bot_enabled(True)
        self.assertFalse(self.window._stock_stop.is_set())
        self.assertFalse(self.window._garden_stop.is_set())
        self.assertIsNot(self.window._stock_stop, stock_token)

    def test_paused_bot_blocks_all_start_paths(self):
        self.connect()
        with patch('app.ui.main_window.ComboWorker') as combo, patch('app.ui.main_window.AutoAscensaoWorker') as ascension:
            self.window.start_simple_farm(); self.window.start_combo()
            self.window.start_auto_ascension(); self.window.save_scum_tab.request(True)
            self.window._toggle_stock_auto_trade(True)
            self.window._toggle_garden_automation(True)
            combo.assert_not_called(); ascension.assert_not_called()
            self.window.runner.acquire_exclusive.assert_not_called()
            self.assertFalse(self.window.stock_toggle.running)
            self.assertFalse(self.window.garden_toggle.running)

    def test_game_closing_pauses_the_bot(self):
        self.connect(); self.window.set_bot_enabled(True)
        application = Application(); application.window = self.window
        application.pid = 123
        with patch('main.find_cookie_window', return_value=None):
            application._refresh_game_state()
        self.assertFalse(self.window._bot_enabled)
        self.assertEqual(self.window.open_game_button.text(), 'Abrir jogo')

    def test_runner_pause_blocks_detector_and_clicker_requests(self):
        with patch('app.core.run.InputHandler'):
            runner = AutomationRunner(123, Mock())
        runner.set_paused(True)
        runner._run_detector_cycle()
        runner.toggle_clicker()
        self.assertFalse(runner.ensure_clicker_running())
        self.assertEqual(runner.bridge.mock_calls, [])
        runner.set_paused(False)
        runner.bridge.get_cookie_position.return_value = {'x': 1, 'y': 2}
        self.assertTrue(runner.ensure_clicker_running())
        runner.set_paused(True)
        self.assertFalse(runner.is_running)

    def test_pause_during_collection_blocks_following_actions(self):
        from app.config.settings import automation_config
        with patch('app.core.run.InputHandler'):
            runner = AutomationRunner(123, Mock())
        runner.bridge.pop_golden_cookie.side_effect = lambda: runner.set_paused(True)
        with patch.object(automation_config, 'enable_golden_cookie', True):
            runner._run_detector_cycle()
        runner.bridge.click_fortune.assert_not_called()
        runner.bridge.pop_reindeer.assert_not_called()
        runner.bridge.get_wrinklers.assert_not_called()
        runner.bridge.get_sugar_lump_status.assert_not_called()
        runner.bridge.cast_grimoire_spell_when_full.assert_not_called()
