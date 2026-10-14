"""Quedas e retomadas simuladas, sem enviar ações ao jogo."""
import copy
import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication
from app.bridge.js_bridge import CookieClickerBridge
from app.config.settings import app_config
from app.core.game_launcher import GameLauncher, GameLaunchResult
from app.core.run import AutomationRunner
from app.ui.main_window import MainWindow
from main import Application


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        previous = copy.deepcopy(app_config.__dict__)
        self.addCleanup(lambda: app_config.__dict__.update(previous))
        app_config.clicker_mode = 'toggle'
        timer = patch('app.ui.main_window.QTimer.singleShot')
        timer.start(); self.addCleanup(timer.stop)
        self.window = MainWindow()
        self.addCleanup(self.close)
        self.application = Application()
        self.application.window = self.window
        self.bridge = Mock(connected=True)
        self.runner = Mock(is_running=True, mouse_clicker_running=True,
                           _simple_farm_active=False, detector_thread=None, clicker_thread=None)
        self.application.bridge = self.window.bridge = self.bridge
        self.application.runner = self.window.runner = self.runner
        self.application.pid = 42
        self.application._connection_identity = 'same-save'
        self.window._game_open = self.window._bot_enabled = True
        self.window.stock_toggle.set_running(True)
        self.window.garden_toggle.set_running(True)

    def close(self):
        self.window._combo_worker = self.window._auto_ascension_worker = None
        self.window._stock_worker = self.window._garden_worker = None
        self.window._sugar_lump_worker = None
        self.window.save_scum_tab.worker = None
        self.window._save_scum_exclusive = False
        self.window.runner = None
        self.window.close()

    def reconnect(self, *, identity='same-save', ascending=False):
        bridge = Mock(connected=True)
        result = GameLaunchResult(True, 'ready', bridge, 42,
                                  snapshot={'identity': identity, 'ascending': ascending})
        with patch('main.AutomationRunner', return_value=Mock(is_running=False, mouse_clicker_running=False,
                   _simple_farm_active=False, detector_thread=None, clicker_thread=None)), \
             patch('main.find_cookie_window', return_value=42), \
             patch.object(self.window, '_load_grimoire_spells'):
            self.application._connection_completed(result)
        return bridge

    def test_lost_connection_pauses_once_and_preserves_periodic_choices(self):
        self.application._begin_recovery()
        self.application._begin_recovery()
        self.assertFalse(self.window._bot_enabled)
        self.assertFalse(self.bridge.connected)
        self.assertTrue(self.bridge.managed_connection)
        self.runner.stop.assert_called_once()
        self.assertTrue(self.window.stock_toggle.running)
        self.assertTrue(self.window.garden_toggle.running)
        self.assertTrue(self.application._recover_resume)
        self.assertFalse(self.window._resume_mouse_clicker)
        self.assertEqual(self.window.open_game_button.text(), 'Manter pausado')

    def test_same_save_rebuilds_controllers_and_resumes_without_mouse(self):
        old_stock = self.window.stock_automation
        self.application._begin_recovery()
        bridge = self.reconnect()
        self.assertFalse(self.application._recovering)
        self.assertTrue(self.window._bot_enabled)
        self.assertIs(self.window.stock_automation.bridge, bridge)
        self.assertIsNot(self.window.stock_automation, old_stock)
        self.window.runner.ensure_clicker_running.assert_called_once()
        self.window.runner.toggle_mouse_clicker.assert_not_called()
        self.assertTrue(self.window.runner.require_fresh_hotkeys)

    def test_other_save_ascending_and_manual_pause_do_not_resume(self):
        for case in ('other-save', 'ascending', 'paused'):
            with self.subTest(case=case):
                self.application._recovering = False
                self.window._bot_enabled = case != 'paused'
                self.application._connection_identity = 'same-save'
                self.application._begin_recovery()
                self.reconnect(identity='other' if case == 'other-save' else 'same-save', ascending=case == 'ascending')
                self.assertFalse(self.window._bot_enabled)

    def test_user_can_cancel_automatic_resume(self):
        self.application._begin_recovery()
        self.application.open_game()
        self.assertFalse(self.application._recover_resume)
        self.assertEqual(self.window.open_game_button.text(), 'Reconectando…')
        self.reconnect()
        self.assertFalse(self.window._bot_enabled)

    def test_pending_save_scum_keeps_exclusivity_and_rebinds_recovery(self):
        self.window._save_scum_exclusive = True
        self.window._exclusive_session_owner = 'save_scum'
        self.window.save_scum_tab.automation = Mock()
        self.application._begin_recovery()
        bridge = self.reconnect()
        self.assertFalse(self.window._bot_enabled)
        self.assertIs(self.window.save_scum_tab.automation.bridge, bridge)
        self.window.runner.acquire_exclusive.assert_called_once_with('save_scum')

    def test_retries_wait_for_workers_and_use_backoff_without_log_spam(self):
        self.application._begin_recovery()
        with patch('main.find_cookie_window', return_value=42), \
             patch('main.time.monotonic', return_value=100), \
             patch.object(self.application, '_connect') as connect:
            self.window._stock_worker = Mock()
            self.application._refresh_game_state()
            connect.assert_not_called()
            self.window._stock_worker = None
            self.application._retry_at = 101
            self.application._refresh_game_state()
            connect.assert_not_called()
            self.application._retry_at = 100
            self.application._refresh_game_state()
            connect.assert_called_once_with(launch=False, automatic=True)
            with patch.object(self.window, 'add_log') as log:
                self.application._connection_completed(GameLaunchResult(False, 'offline'))
                self.assertEqual(self.application._retry_at, 102)
                self.assertEqual(self.application._retry_delay, 4)
                log.assert_not_called()

    def test_closed_game_is_not_relaunched_automatically(self):
        with patch('main.find_cookie_window', return_value=None), \
             patch.object(self.application, '_connect') as connect:
            self.application._refresh_game_state()
            self.application._refresh_game_state()
            connect.assert_not_called()
        self.assertEqual(self.window.open_game_button.text(), 'Abrir jogo')

    def test_stale_health_result_cannot_pause_a_new_connection(self):
        with patch.object(self.application, '_begin_recovery') as recover:
            self.application._health_completed(Mock(), 42, None)
            recover.assert_not_called()
            self.application._health_completed(self.bridge, 42, None)
            recover.assert_called_once()

    def test_stale_reconnect_result_does_not_replace_old_connection(self):
        self.application._begin_recovery()
        bridge = Mock()
        result = GameLaunchResult(True, 'ready', bridge, 42, snapshot={'identity': 'same-save'})
        with patch('main.find_cookie_window', return_value=99):
            self.application._connection_completed(result)
        bridge.disconnect.assert_called_once()
        self.assertIs(self.application.bridge, self.bridge)
        self.assertTrue(self.application._recovering)

    def test_transport_failure_does_not_disable_garden_or_stock(self):
        self.bridge.connected = False
        with patch('app.ui.main_window.save_automation_settings') as save:
            self.window._garden_task_failed('connection lost')
            self.window._stock_task_failed('connection lost')
            self.assertTrue(self.window.garden_toggle.running)
            self.assertTrue(self.window.stock_toggle.running)
            save.assert_not_called()


class RecoveryTransportTests(unittest.TestCase):
    def test_failed_action_is_not_retried_on_managed_bridge(self):
        bridge = CookieClickerBridge()
        bridge.managed_connection = bridge.connected = True
        bridge.tab = Mock()
        bridge.tab.Runtime.evaluate.side_effect = TimeoutError('lost response')
        with patch.object(bridge, 'connect') as connect:
            self.assertIsNone(bridge.execute_js('Game.Earn(1)'))
            self.assertIsNone(bridge.execute_js('Game.Earn(1)'))
            connect.assert_not_called()
        bridge.tab.Runtime.evaluate.assert_called_once()
        self.assertEqual(bridge.tab.Runtime.evaluate.call_args.kwargs['_timeout'], bridge.timeout)

    def test_launcher_requires_fresh_readiness_snapshot(self):
        bridge = Mock()
        bridge.execute_js.return_value = True
        launcher = GameLauncher(bridge_factory=Mock(return_value=bridge))
        with patch.object(launcher, '_game_tab', return_value='game'), \
             patch('app.core.game_launcher.find_cookie_window', return_value=42):
            bridge.get_connection_snapshot.return_value = None
            self.assertIsNone(launcher._connect())
            bridge.get_connection_snapshot.return_value = {'identity': 'save', 'ascending': False}
            result = launcher._connect()
            self.assertEqual(result.snapshot['identity'], 'save')

    def test_clickers_stop_immediately_when_bridge_disconnects(self):
        with patch('app.core.run.InputHandler'):
            runner = AutomationRunner(0, Mock(connected=False))
        runner.is_running = runner.mouse_clicker_running = True
        runner.stop_event = Mock()
        runner.stop_event.is_set.side_effect = [False, True]
        runner.input_handler.is_key_pressed.return_value = True
        runner.clicker_loop()
        runner.input_handler.click_cookie.assert_not_called()
        runner.input_handler.click_at_cursor.assert_not_called()

    def test_held_hotkeys_do_not_restart_mouse_after_recovery(self):
        previous = copy.deepcopy(app_config.__dict__)
        self.addCleanup(lambda: app_config.__dict__.update(previous))
        app_config.clicker_mode = app_config.mouse_clicker_mode = 'hold'
        with patch('app.core.run.InputHandler'):
            runner = AutomationRunner(0, Mock(connected=True))
        runner.cookie_position = (10, 10)
        runner.require_fresh_hotkeys = True
        class Event:
            index = 0
            def is_set(self):return self.index >= 4
            def wait(self, delay):self.index += 1
        event = Event(); runner.stop_event = event
        runner.input_handler.is_key_pressed.side_effect = lambda key: event.index != 2
        clicks = []
        runner.input_handler.click_at_cursor.side_effect = lambda: clicks.append(event.index) or True
        runner.clicker_loop()
        self.assertEqual(clicks, [3])
