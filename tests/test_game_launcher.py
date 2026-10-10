"""Launcher testado sem iniciar processos ou alterar a Steam."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt5.QtWidgets import QApplication
from app.config.settings import app_config
from app.core.game_launcher import GameLauncher, GameLaunchResult, find_game_executable
from app.ui.main_window import MainWindow
from main import Application

class LauncherTests(unittest.TestCase):
    def test_find_installation_in_secondary_steam_library(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'Steam';library=Path(temp)/'Games'
            (root/'steamapps').mkdir(parents=True)
            executable=library/'steamapps/common/Cookie Clicker/Cookie Clicker.exe'
            executable.parent.mkdir(parents=True);executable.touch()
            escaped=str(library).replace('\\','\\\\')
            (root/'steamapps/libraryfolders.vdf').write_text('"path" "'+escaped+'"',encoding='utf-8')
            with patch('app.core.game_launcher.steam_roots',return_value=[root]):
                self.assertEqual(find_game_executable(),executable)
                self.assertEqual(find_game_executable(str(executable)),executable)
    def test_saved_missing_path_falls_back_to_detection(self):
        with patch('app.core.game_launcher.steam_roots',return_value=[]):
            self.assertIsNone(find_game_executable('missing.exe'))
    def test_launch_passes_debugger_argument_and_working_directory(self):
        launcher=GameLauncher()
        executable=Path('D:/Steam/steamapps/common/Cookie Clicker/Cookie Clicker.exe')
        result=GameLaunchResult(True,'ready',Mock(),123)
        with patch.object(launcher,'_connect',side_effect=[None,result]), \
             patch('app.core.game_launcher.cookie_process_running',return_value=False), \
             patch('app.core.game_launcher.find_game_executable',return_value=executable), \
             patch('app.core.game_launcher.subprocess.Popen') as popen:
            self.assertTrue(launcher.launch().ok)
            popen.assert_called_once_with([str(executable),'--remote-debugging-port=9222'],cwd=str(executable.parent))
            self.assertEqual(result.executable,str(executable))
    def test_existing_debugger_connects_without_duplicate_process(self):
        launcher=GameLauncher()
        with patch.object(launcher,'_connect',return_value=GameLaunchResult(True,'ready')),patch('app.core.game_launcher.subprocess.Popen') as popen:
            self.assertTrue(launcher.launch().ok)
            popen.assert_not_called()
    def test_open_without_debugger_requires_manual_close(self):
        launcher=GameLauncher()
        with patch.object(launcher,'_connect',return_value=None),patch('app.core.game_launcher.cookie_process_running',return_value=True),patch('app.core.game_launcher.subprocess.Popen') as popen:
            result=launcher.launch()
            self.assertEqual(result.reason,'already_running')
            self.assertIn('Salve e feche',result.message)
            popen.assert_not_called()
    def test_missing_installation_does_not_spawn(self):
        launcher=GameLauncher()
        with patch.object(launcher,'_connect',return_value=None),patch('app.core.game_launcher.cookie_process_running',return_value=False),patch('app.core.game_launcher.find_game_executable',return_value=None),patch('app.core.game_launcher.subprocess.Popen') as popen:
            self.assertEqual(launcher.launch().reason,'missing_executable')
            popen.assert_not_called()
    def test_cancel_does_not_open_game(self):
        launcher=GameLauncher();launcher.stop()
        with patch('app.core.game_launcher.subprocess.Popen') as popen:
            self.assertEqual(launcher.launch().reason,'cancelled')
            popen.assert_not_called()
    def test_runtime_must_be_ready_and_failed_bridge_is_disconnected(self):
        bridge=Mock();bridge.execute_js.return_value=False
        launcher=GameLauncher(bridge_factory=Mock(return_value=bridge))
        with patch.object(launcher,'_game_tab',return_value='game'),patch('app.core.game_launcher.find_cookie_window',return_value=42):
            self.assertIsNone(launcher._connect())
            bridge.connect.assert_called_once_with(tab_id='game')
            bridge.disconnect.assert_called_once()
    def test_probe_selects_cookie_page_not_other_debugger_tabs(self):
        data=[{'type':'page','id':'other','url':'chrome://newtab'}, {'type':'page','id':'game','url':'file:///D:/Steam/Cookie%20Clicker/resources/app/src/index.html'}]
        response=Mock();response.read.return_value=json.dumps(data).encode()
        context=Mock();context.__enter__=Mock(return_value=response);context.__exit__=Mock()
        with patch('app.core.game_launcher.urlopen',return_value=context):
            self.assertEqual(GameLauncher()._game_tab(),'game')

class LaunchUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_header_button_emits_request_while_game_is_closed(self):
        window=MainWindow()
        try:
            fired=[];window.open_game_requested.connect(lambda:fired.append(True))
            window.open_game_button.click()
            self.assertEqual(fired,[True])
            self.assertIsNone(window.bridge)
            self.assertIsNone(window.runner)
        finally:window.close()
    def test_application_initializes_offline_without_starting_runner(self):
        app=Application()
        with patch('main.QTimer'),patch('main.load_app_settings'),patch('main.load_automation_settings'),patch('main.load_backup_settings'),patch('main.add_ui_handler'),patch('main.create_ui_app',return_value=(Mock(),Mock())) as ui,patch('main.AutomationRunner') as runner:
            self.assertTrue(app.initialize())
            ui.assert_called_once_with()
            runner.assert_not_called()
            self.assertIsNone(app.bridge)
    def test_connect_in_background_and_no_duplicate_worker(self):
        app=Application();app.window=Mock()
        with patch('main.GameLauncher') as launcher,patch('main.StockMarketWorker') as factory:
            app._connect(launch=True)
            app._connect(launch=True)
            self.assertEqual(factory.call_count,1)
            self.assertEqual(factory.call_args.args[0],launcher.return_value.launch)
            factory.return_value.start.assert_called_once()
    def test_main_button_dispatches_open_enable_and_pause(self):
        app=Application();app.window=Mock()
        app.window._bot_enabled=False;app.window._game_open=False
        with patch.object(app,'_connect') as connect:
            app.open_game()
            connect.assert_called_once_with(launch=True)
            connect.reset_mock()
            app.window._game_open=True
            app.open_game()
            connect.assert_called_once_with(launch=False)
            self.assertTrue(app._enable_after_connect)
            app.window._bot_enabled=True
            app.open_game()
            app.window.set_bot_enabled.assert_called_once_with(False)
    def test_success_attaches_bridge_and_starts_detector(self):
        app=Application();app.window=Mock()
        result=GameLaunchResult(True,'ready',Mock(),123)
        with patch('main.AutomationRunner') as runner:
            app._connection_completed(result)
            app.window.attach_game.assert_called_once_with(result.bridge,runner.return_value)
            runner.return_value.start.assert_called_once()
    def test_bot_window_is_not_mistaken_for_the_game(self):
        from app.core.window_finder import find_cookie_window
        with patch('app.core.window_finder.win32gui.EnumWindows',side_effect=lambda cb,pids:cb(1,pids)),patch('app.core.window_finder.win32gui.IsWindowVisible',return_value=True),patch('app.core.window_finder.win32gui.GetWindowText',return_value='Cookie Clicker Bot'),patch('app.core.window_finder.win32process.GetWindowThreadProcessId') as pid:
            self.assertIsNone(find_cookie_window())
            pid.assert_not_called()
