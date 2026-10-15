"""Janelas com títulos parecidos não podem esconder Abrir jogo."""
import os
import unittest
from unittest.mock import Mock, patch
from app.core.window_finder import find_cookie_window, is_cookie_process


class WindowDetectionTests(unittest.TestCase):
    def detect(self, executable_matches, title='Cookie Clicker - Chrome'):
        with patch('app.core.window_finder.win32gui.EnumWindows', side_effect=lambda callback, pids: callback(1, pids)), \
             patch('app.core.window_finder.win32gui.IsWindowVisible', return_value=True), \
             patch('app.core.window_finder.win32gui.GetWindowText', return_value=title), \
             patch('app.core.window_finder.win32process.GetWindowThreadProcessId', return_value=(1, 123)), \
             patch('app.core.window_finder.is_cookie_process', return_value=executable_matches):
            return find_cookie_window()

    def test_browser_title_is_not_a_game(self):
        self.assertIsNone(self.detect(False))

    def test_game_executable_is_recognized(self):
        self.assertEqual(self.detect(True), 123)

    def test_business_day_game_is_recognized_with_cookie_baker_title(self):
        self.assertEqual(self.detect(True, '18,536 cookies - Cookie Baker'), 123)
        self.assertEqual(self.detect(True, 'ASCENDING! - COOKIE BAKER'), 123)

    def test_business_day_browser_is_not_a_game(self):
        self.assertIsNone(self.detect(False, '18,536 cookies - Cookie Baker - Chrome'))

    def test_bot_title_is_rejected_even_if_executable_check_would_pass(self):
        self.assertIsNone(self.detect(True, 'Cookie Clicker Bot'))

    def test_native_process_query_rejects_python(self):
        self.assertFalse(is_cookie_process(os.getpid()))

    def test_native_query_closes_handle_and_checks_full_path(self):
        kernel = Mock()
        kernel.OpenProcess.return_value = 10
        def query(handle, flags, path, size):
            path.value = r'D:\Steam\Cookie Clicker\Cookie Clicker.exe'
            return True
        kernel.QueryFullProcessImageNameW.side_effect = query
        with patch('app.core.window_finder.ctypes.WinDLL', return_value=kernel):
            self.assertTrue(is_cookie_process(123))
        kernel.CloseHandle.assert_called_once_with(10)

    def test_inaccessible_process_is_not_detected(self):
        kernel = Mock()
        kernel.OpenProcess.return_value = None
        with patch('app.core.window_finder.ctypes.WinDLL', return_value=kernel):
            self.assertFalse(is_cookie_process(123))
        kernel.CloseHandle.assert_not_called()
