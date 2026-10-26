"""Seleção persistida de Banco e Garden, respeitando o controle geral."""
import copy
import os
import unittest
from unittest.mock import Mock, patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication
from app.config.settings import automation_config, load_automation_settings, save_automation_settings
from app.ui.main_window import MainWindow

class PeriodicPreferencesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        previous = copy.deepcopy(automation_config.__dict__)
        self.addCleanup(lambda: automation_config.__dict__.update(previous))
        self.patches = [patch('app.ui.main_window.save_automation_settings'),
                        patch('app.ui.main_window.QTimer.singleShot')]
        for p in self.patches:
            p.start(); self.addCleanup(p.stop)

    def test_settings_roundtrip_and_first_run_defaults(self):
        values = {}
        class Settings:
            def __init__(self, *args): pass
            def beginGroup(self, *args): pass
            def endGroup(self): pass
            def sync(self): pass
            def setValue(self, key, value): values[key] = value
            def value(self, key, default=None, type=None): return values.get(key, default)
        with patch('app.config.settings.QSettings', Settings):
            load_automation_settings()
            self.assertFalse(automation_config.enable_stock_market_auto_trade)
            self.assertFalse(automation_config.enable_garden_automation)
            for stock, garden in ((True, False), (False, True), (True, True), (False, False)):
                automation_config.enable_stock_market_auto_trade = stock
                automation_config.enable_garden_automation = garden
                save_automation_settings()
                automation_config.enable_stock_market_auto_trade = not stock
                automation_config.enable_garden_automation = not garden
                load_automation_settings()
                self.assertEqual(automation_config.enable_stock_market_auto_trade, stock)
                self.assertEqual(automation_config.enable_garden_automation, garden)

    def test_reopened_window_restores_selection_but_stays_paused(self):
        automation_config.enable_stock_market_auto_trade = True
        automation_config.enable_garden_automation = True
        window = MainWindow()
        try:
            self.assertTrue(window.stock_toggle.running)
            self.assertTrue(window.garden_toggle.running)
            self.assertFalse(window._bot_enabled)
            self.assertTrue(window._stock_stop.is_set())
            self.assertTrue(window._garden_stop.is_set())
            self.assertIn('bot', window.stock_toggle.status.text())
            window.bridge = Mock(); window.runner = Mock(is_running=False)
            window._game_open = True
            window.set_bot_enabled(True)
            self.assertFalse(window._stock_stop.is_set())
            self.assertFalse(window._garden_stop.is_set())
            window.set_bot_enabled(False)
            self.assertTrue(automation_config.enable_stock_market_auto_trade)
            self.assertTrue(automation_config.enable_garden_automation)
        finally:
            window.close()

    def test_individual_toggle_saves_immediately_even_while_stopping(self):
        window = MainWindow()
        try:
            window.bridge = Mock(); window.runner = Mock(is_running=False)
            window.stock_automation = Mock(); window.fazendeira = Mock()
            window.set_bot_enabled(True)
            for name, handler, key in (
                ('stock', window._toggle_stock_auto_trade, 'enable_stock_market_auto_trade'),
                ('garden', window._toggle_garden_automation, 'enable_garden_automation'),
            ):
                with patch('app.ui.main_window.save_automation_settings') as save:
                    handler(True)
                    self.assertTrue(getattr(automation_config, key))
                    save.assert_called_once()
                    setattr(window, '_' + name + '_worker', Mock())
                    handler(False)
                    self.assertFalse(getattr(automation_config, key))
                    self.assertEqual(save.call_count, 2)
                    self.assertTrue(getattr(window, name + '_toggle').stopping)
                    setattr(window, '_' + name + '_worker', None)
        finally:
            window.close()
