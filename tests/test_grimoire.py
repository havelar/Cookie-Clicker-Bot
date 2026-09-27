"""Testes da automação de mana máxima do Grimoire."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from app.bridge.js_bridge import CookieClickerBridge
from app.config.settings import automation_config
from app.core.run import AutomationRunner
from app.ui.main_window import MainWindow


class CaptureBridge(CookieClickerBridge):
    def __init__(self, payload):
        self.payload = payload
        self.scripts = []

    def execute_js(self, code):
        self.scripts.append(code)
        return self.payload


class GrimoireBridgeTests(unittest.TestCase):
    def test_spell_list_is_sanitized(self):
        bridge = CaptureBridge([
            {"id": 1, "name": "Force the Hand of Fate", "description": "Golden cookie"},
            {"id": -1, "name": "Inválida"},
            "inválida",
        ])

        spells = bridge.get_grimoire_spells()

        self.assertEqual(spells, [{
            "id": 1,
            "name": "Force the Hand of Fate",
            "description": "Golden cookie",
        }])

    def test_cast_checks_full_mana_and_casts_in_one_runtime_call(self):
        bridge = CaptureBridge({"cast": False, "reason": "waiting_mana"})

        result = bridge.cast_grimoire_spell_when_full(2)

        self.assertEqual(result["reason"], "waiting_mana")
        self.assertEqual(len(bridge.scripts), 1)
        script = bridge.scripts[0]
        self.assertLess(script.index("magic + 1e-7 < maximum"), script.index("M.castSpell(spell)"))

    def test_invalid_spell_is_rejected_before_javascript(self):
        bridge = CaptureBridge(None)

        result = bridge.cast_grimoire_spell_when_full(-1)

        self.assertEqual(result["reason"], "invalid_spell")
        self.assertEqual(bridge.scripts, [])


class FakeGrimoireBridge:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def cast_grimoire_spell_when_full(self, spell_id):
        self.calls.append(spell_id)
        return self.responses.pop(0)


class GrimoireRunnerTests(unittest.TestCase):
    def setUp(self):
        self.previous_enabled = automation_config.enable_grimoire_spell_spam
        self.previous_spell = automation_config.grimoire_spell_id

    def tearDown(self):
        automation_config.enable_grimoire_spell_spam = self.previous_enabled
        automation_config.grimoire_spell_id = self.previous_spell

    def test_runner_waits_for_full_mana_and_throttles_attempts(self):
        bridge = FakeGrimoireBridge([
            {"cast": False, "reason": "waiting_mana", "message": "Aguardando"},
            {"cast": True, "reason": "cast", "spellName": "Stretch Time"},
        ])
        runner = object.__new__(AutomationRunner)
        runner.bridge = bridge
        runner._last_grimoire_attempt_at = 0.0
        runner._last_grimoire_failure = None
        automation_config.enable_grimoire_spell_spam = True
        automation_config.grimoire_spell_id = 2

        self.assertFalse(runner._run_grimoire_cycle(now=10.0))
        self.assertFalse(runner._run_grimoire_cycle(now=10.5))
        self.assertTrue(runner._run_grimoire_cycle(now=11.0))
        self.assertEqual(bridge.calls, [2, 2])


class GrimoireUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_automation_tab_has_only_the_toggle_and_settings_has_the_dropdown(self):
        window = MainWindow()
        automation_tab = window.tabs.widget(0)
        settings_tab = window.tabs.widget(next(
            index for index in range(window.tabs.count())
            if window.tabs.tabText(index) == "Configurações"
        ))

        self.assertEqual(window.grimoire_spell_spam_checkbox.text(), "Spammar Skill")
        self.assertEqual(window.grimoire_spell_combo.count(), 9)
        self.assertEqual(window.grimoire_spell_combo.isEnabled(),
                         automation_config.enable_grimoire_spell_spam)
        self.assertTrue(automation_tab.isAncestorOf(window.grimoire_spell_spam_checkbox))
        self.assertFalse(automation_tab.isAncestorOf(window.grimoire_spell_combo))
        self.assertTrue(settings_tab.isAncestorOf(window.grimoire_spell_combo))
        self.assertNotIn(
            "Sugar Lumps",
            [window.tabs.tabText(index) for index in range(window.tabs.count())],
        )
        self.assertTrue(automation_tab.isAncestorOf(window.sugar_lump_checkbox))
        self.assertTrue(all(
            settings_tab.isAncestorOf(checkbox)
            for checkbox in window._preserve_checkboxes
        ))
        window.close()


if __name__ == "__main__":
    unittest.main()
