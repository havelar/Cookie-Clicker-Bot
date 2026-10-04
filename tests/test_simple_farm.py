import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from app.bridge.js_bridge import CookieClickerBridge
from app.config.settings import AutomationConfig
from app.core.simple_farm import SimpleFarmAutomation
from app.core.run import AutomationRunner
from app.config.settings import automation_config
from app.models.simple_farm import ConfiguracaoSimpleFarm, EstadoSimpleFarm
from app.ui.main_window import MainWindow


def snapshot(**changes):
    value = {
        "available": True,
        "screen": "game",
        "version": "2.053",
        "seed": "farm-seed",
        "cookiesEarned": 1e50,
        "cookies": 1e48,
        "spellsCastTotal": 10,
        "magic": 100.0,
        "magicM": 100.0,
        "skipSpellCost": 10.0,
        "wizardTowers": 726,
        "wizardTowerLevel": 10,
        "pantheonSlots": [2, 8, 6],
        "buffs": [],
        "shimmers": [],
    }
    value.update(changes)
    return value


class FakeSimpleFarmBridge:
    def __init__(self, state=None):
        self.state = state or snapshot()
        self.calls = []
        self.forecast = {
            "ok": True,
            "seed": "farm-seed",
            "version": "2.053",
            "currentCast": 10,
            "startCast": 10,
            "skipCount": 0,
            "results": ["click frenzy"],
            "quality": "Click Frenzy + Frenzy",
            "minimumTowers": 501,
            "finalTowers": 1,
        }
        self.reinvest_result = {"ok": False, "waiting": True, "message": "caixa protegido"}

    def get_combo_snapshot(self, **kwargs):
        self.calls.append(("snapshot",))
        return self.state

    def forecast_simple_farm_spell(self, ahead):
        self.calls.append(("forecast", ahead))
        return dict(self.forecast)

    def pop_combo_natural_shimmer(self, shimmer_id):
        self.calls.append(("pop", shimmer_id))
        return {"ok": True}

    def pop_combo_cookie_storm_drops(self):
        self.calls.append(("storm",))
        return {"ok": True, "count": 5}

    def cast_combo_skip(self, expected_cast, spell_id):
        self.calls.append(("skip", expected_cast, spell_id))
        return {"ok": True}

    def ensure_combo_building_minimum(self, building_id, minimum):
        self.calls.append(("minimum", building_id, minimum))
        return {"ok": True}

    def execute_simple_farm_spell(self, **kwargs):
        self.calls.append(("spell", kwargs))
        return {"ok": True}

    def reinvest_simple_farm(self, **kwargs):
        self.calls.append(("reinvest", kwargs))
        return dict(self.reinvest_result)


class SimpleFarmStateMachineTests(unittest.TestCase):
    def test_preview_is_read_only(self):
        bridge = FakeSimpleFarmBridge()

        report = SimpleFarmAutomation(bridge, ConfiguracaoSimpleFarm()).gerar_previa()

        self.assertEqual(report.estado, EstadoSimpleFarm.PREVIA)
        self.assertEqual([call[0] for call in bridge.calls], ["snapshot", "forecast"])

    def test_reinvestment_uses_high_water_reserve_and_counts_upgrade(self):
        bridge = FakeSimpleFarmBridge(snapshot(magic=90, magicM=100, cookies=1_000_000))
        bridge.reinvest_result = {
            "ok": True, "upgrades": 1, "buildings": 0, "spent": 50_000,
            "message": "Upgrade comprado",
        }
        automation = SimpleFarmAutomation(
            bridge,
            ConfiguracaoSimpleFarm(reserva_caixa=0.80, investimento_por_ciclo=0.10),
            relogio=lambda: 100.0,
        )

        report = automation.executar_passo()

        self.assertEqual(report.upgrades_comprados, 1)
        call = next(call[1] for call in bridge.calls if call[0] == "reinvest")
        self.assertEqual(call["cash_floor"], 800_000)
        self.assertEqual(call["max_spend_fraction"], 0.10)
        self.assertEqual(call["reserve_fraction"], 0.80)

    def test_reinvestment_never_runs_during_multiplier(self):
        bridge = FakeSimpleFarmBridge(snapshot(magic=90, magicM=100, buffs=[{
            "name": "Frenzy", "type": "frenzy", "timeSeconds": 30, "multCpS": 7,
        }]))

        SimpleFarmAutomation(bridge, ConfiguracaoSimpleFarm()).executar_passo()

        self.assertNotIn("reinvest", [call[0] for call in bridge.calls])

    def test_natural_cookie_is_collected_before_any_spell(self):
        bridge = FakeSimpleFarmBridge(snapshot(shimmers=[{"id": 42, "force": ""}]))

        report = SimpleFarmAutomation(bridge, ConfiguracaoSimpleFarm()).executar_passo()

        self.assertEqual(report.estado, EstadoSimpleFarm.COLETANDO)
        self.assertIn(("pop", 42), bridge.calls)
        self.assertNotIn("spell", [call[0] for call in bridge.calls])

    def test_cookie_storm_is_drained_without_stopping_simple_farm(self):
        bridge = FakeSimpleFarmBridge(snapshot(shimmers=[
            {"id": 43, "force": "cookie storm drop"},
            {"id": 44, "force": "cookie storm drop"},
        ]))

        report = SimpleFarmAutomation(bridge, ConfiguracaoSimpleFarm()).executar_passo()

        self.assertEqual(report.estado, EstadoSimpleFarm.COLETANDO)
        self.assertFalse(report.terminal)
        self.assertEqual(report.golden_cookies_coletados, 5)
        self.assertIn(("storm",), bridge.calls)

    def test_alignment_uses_only_cheap_spell_at_full_mana(self):
        bridge = FakeSimpleFarmBridge()
        bridge.forecast.update(startCast=12, skipCount=2)

        report = SimpleFarmAutomation(bridge, ConfiguracaoSimpleFarm()).executar_passo()

        self.assertEqual(report.estado, EstadoSimpleFarm.ALINHANDO)
        self.assertIn(("skip", 10, 4), bridge.calls)
        self.assertNotIn("refill", [call[0] for call in bridge.calls])

    def test_ready_natural_multiplier_executes_single_spell_without_lump_options(self):
        bridge = FakeSimpleFarmBridge(snapshot(buffs=[{
            "name": "Frenzy", "type": "frenzy", "timeSeconds": 30, "multCpS": 7,
        }]))

        report = SimpleFarmAutomation(bridge, ConfiguracaoSimpleFarm()).executar_passo()

        self.assertEqual(report.estado, EstadoSimpleFarm.EXECUTANDO)
        call = next(call[1] for call in bridge.calls if call[0] == "spell")
        self.assertNotIn("minimum_towers", call)
        self.assertNotIn("use_loans", call)
        self.assertNotIn("use_sugar_frenzy", call)

    def test_dragonflight_blocks_single_spell_and_skip(self):
        bridge = FakeSimpleFarmBridge(snapshot(buffs=[{
            "name": "Dragonflight", "type": "dragonflight", "timeSeconds": 20,
        }]))

        report = SimpleFarmAutomation(bridge, ConfiguracaoSimpleFarm()).executar_passo()

        self.assertEqual(report.estado, EstadoSimpleFarm.AGUARDANDO_BUFF)
        self.assertNotIn("spell", [call[0] for call in bridge.calls])
        self.assertNotIn("skip", [call[0] for call in bridge.calls])

    def test_natural_click_frenzy_preserves_mana(self):
        bridge = FakeSimpleFarmBridge(snapshot(buffs=[{
            "name": "Click frenzy", "type": "click frenzy", "timeSeconds": 12,
            "multCpS": 1, "multClick": 777,
        }]))
        report = SimpleFarmAutomation(bridge, ConfiguracaoSimpleFarm()).executar_passo()
        self.assertFalse(report.terminal)
        self.assertNotIn("spell", [call[0] for call in bridge.calls])
        self.assertNotIn("skip", [call[0] for call in bridge.calls])

    def test_missing_forecast_still_collects_and_invests(self):
        bridge = FakeSimpleFarmBridge()
        bridge.forecast = {"ok": False}
        farm = SimpleFarmAutomation(bridge, ConfiguracaoSimpleFarm())
        self.assertFalse(farm.gerar_previa().terminal)
        self.assertFalse(farm.executar_passo().terminal)
        self.assertIn("reinvest", [c[0] for c in bridge.calls])
        bridge.state["shimmers"] = [{"id": 42, "force": ""}]
        self.assertEqual(farm.executar_passo().golden_cookies_coletados, 1)

    def test_other_farms_cannot_lower_reserve_and_cooldown_limits_spending(self):
        now = [0]
        bridge = FakeSimpleFarmBridge(snapshot(cookies=1000))
        farm = SimpleFarmAutomation(bridge, ConfiguracaoSimpleFarm(), relogio=lambda: now[0])
        farm.executar_passo()
        bridge.state["cookies"] = 300
        farm.executar_passo()
        self.assertEqual(len([c for c in bridge.calls if c[0]=="reinvest"]), 1)
        now[0] = 15
        report = farm.executar_passo()
        self.assertEqual(report.caixa_reservado, 800)
        self.assertEqual([c for c in bridge.calls if c[0]=="reinvest"][-1][1]["cash_floor"], 800)

    def test_clicker_runs_only_during_useful_window_and_stops_afterward(self):
        bridge = FakeSimpleFarmBridge(snapshot(magic=50, magicM=100, buffs=[{
            "name": "Click frenzy", "type": "click frenzy", "timeSeconds": 12,
            "multClick": 777,
        }]))
        bridge.forecast.update(startCast=12, skipCount=2)
        clicker = []
        automation = SimpleFarmAutomation(
            bridge,
            ConfiguracaoSimpleFarm(),
            habilitar_clicker=lambda: clicker.append("start") or True,
            desabilitar_clicker=lambda: clicker.append("stop") or True,
            relogio=lambda: 0.0,
        )

        automation.executar_passo()
        bridge.state = snapshot(magic=50, magicM=100, buffs=[])
        automation.executar_passo()

        self.assertEqual(clicker, ["start", "stop"])

    def test_plain_frenzy_does_not_click_until_single_spell_is_ready(self):
        bridge = FakeSimpleFarmBridge(snapshot(magic=50, magicM=100, buffs=[{
            "name": "Frenzy", "type": "frenzy", "timeSeconds": 30, "multCpS": 7,
        }]))
        bridge.forecast.update(startCast=12, skipCount=2)
        clicker = []

        SimpleFarmAutomation(
            bridge,
            ConfiguracaoSimpleFarm(),
            habilitar_clicker=lambda: clicker.append("start") or True,
            desabilitar_clicker=lambda: clicker.append("stop") or True,
        ).executar_passo()

        self.assertEqual(clicker, [])

    def test_clicker_starts_before_ready_single_spell(self):
        bridge = FakeSimpleFarmBridge(snapshot(buffs=[{
            "name": "Frenzy", "type": "frenzy", "timeSeconds": 30, "multCpS": 7,
        }]))
        events = []
        original = bridge.execute_simple_farm_spell

        def single_spell(**kwargs):
            events.append("spell")
            return original(**kwargs)

        bridge.execute_simple_farm_spell = single_spell
        automation = SimpleFarmAutomation(
            bridge,
            ConfiguracaoSimpleFarm(),
            habilitar_clicker=lambda: events.append("start") or True,
        )

        automation.executar_passo()

        self.assertEqual(events[:2], ["start", "spell"])


class SimpleFarmBridgeTests(unittest.TestCase):
    class StubBridge(CookieClickerBridge):
        def __init__(self, responses):
            self.responses = list(responses)
            self.scripts = []

        def execute_js(self, code):
            self.scripts.append(code)
            return self.responses.pop(0)

    def test_invalid_spell_is_rejected_before_javascript(self):
        bridge = self.StubBridge([])
        result = bridge.execute_simple_farm_spell(expected_cast=-1, minimum_buff_seconds=8)
        self.assertFalse(result["ok"])
        self.assertEqual(bridge.scripts, [])

    def test_invalid_reinvestment_budget_never_reaches_javascript(self):
        for args in [(100, 0.99, 0.8), (100, 0.1, 0.3), (float("nan"), 0.1, 0.8)]:
            bridge = self.StubBridge([])
            self.assertFalse(bridge.reinvest_simple_farm(*args)["ok"])
            self.assertEqual(bridge.scripts, [])


class SimpleFarmUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_combo_tab_has_separate_simple_and_endgame_modes(self):
        window = MainWindow()

        names = [window.combo_mode_tabs.tabText(i) for i in range(window.combo_mode_tabs.count())]
        self.assertEqual(names, ["Simple Farm", "Endgame 1e72"])
        self.assertEqual(window.simple_farm_start_button.text(), "Iniciar Simple Farm")
        self.assertFalse(window.simple_farm_stop_button.isEnabled())
        window._set_simple_farm_busy(True, preview=False)
        self.assertTrue(window.garden_auto_checkbox.isEnabled())
        self.assertTrue(window.stock_auto_trade_checkbox.isEnabled())
        self.assertTrue(window.clicker_button.isEnabled())
        self.assertFalse(window.auto_ascension_start_button.isEnabled())
        for field in (window.simple_farm_search_input, window.simple_farm_interval_input,
                      window.simple_farm_min_buff_input, window.simple_farm_reserve_input,
                      window.simple_farm_investment_input):
            self.assertTrue(field.toolTip())
        window.close()

    def test_defaults_are_fast_and_disabled(self):
        config = AutomationConfig()
        self.assertFalse(config.enable_simple_farm)
        self.assertEqual(config.simple_farm_poll_interval_seconds, 0.2)
        self.assertEqual(config.simple_farm_minimum_buff_seconds, 8.0)
        self.assertEqual(config.simple_farm_cash_reserve_percent, 80.0)
        self.assertEqual(config.simple_farm_investment_percent, 5.0)

    def test_start_keeps_garden_and_bank_workers_and_timers_running(self):
        window = MainWindow()
        window.bridge = Mock()
        window.runner = Mock()
        window.backup_manager = Mock()
        window._garden_worker = Mock()
        window._stock_worker = Mock()
        window.garden_refresh_timer.start(5000)
        window.stock_refresh_timer.start(5000)
        window.simple_farm_enable_checkbox.blockSignals(True)
        window.simple_farm_enable_checkbox.setChecked(True)
        with patch.object(window, '_run_simple_farm_worker') as run:
            with patch.object(window, '_simple_farm_configuration', return_value=ConfiguracaoSimpleFarm()):
                with patch.object(window, '_set_combo_keep_awake'):
                    window.start_simple_farm()
        run.assert_called_once()
        window.runner.acquire_simple_farm.assert_called_once()
        window.runner.acquire_exclusive.assert_not_called()
        self.assertFalse(window._combo_exclusive)
        self.assertTrue(window.garden_refresh_timer.isActive())
        self.assertTrue(window.stock_refresh_timer.isActive())
        window._garden_worker.wait.assert_not_called()
        window._stock_worker.wait.assert_not_called()
        window._garden_worker = window._stock_worker = None
        window.close()


class SimpleFarmRunnerTests(unittest.TestCase):
    def make_runner(self):
        with patch('app.core.run.InputHandler'):
            runner = AutomationRunner(1, Mock())
        runner.update_cookie_position = Mock(return_value=True)
        return runner

    def test_manual_clicker_survives_farm_windows_and_release(self):
        runner = self.make_runner()
        runner.is_running = True
        self.assertTrue(runner.acquire_simple_farm())
        self.assertIsNone(runner.exclusive_owner)
        self.assertFalse(runner.acquire_exclusive('combo'))
        runner.set_simple_farm_clicker(True)
        runner.set_simple_farm_clicker(False)
        self.assertTrue(runner.is_running)
        runner.release_simple_farm()
        self.assertTrue(runner.is_running)

    def test_temporary_clicker_stops_and_manual_request_is_remembered(self):
        runner = self.make_runner()
        runner.acquire_simple_farm()
        runner.set_simple_farm_clicker(True)
        runner.set_simple_farm_clicker(False)
        self.assertFalse(runner.is_running)
        runner.set_simple_farm_clicker(True)
        runner.toggle_clicker()
        runner.release_simple_farm()
        self.assertTrue(runner.is_running)

    def test_detector_continues_other_collections_without_competing_for_magic(self):
        runner = self.make_runner()
        runner.acquire_simple_farm()
        runner.bridge.click_fortune.side_effect = lambda: runner.stop_event.set() or True
        with patch.multiple(automation_config, enable_golden_cookie=True,
                enable_fortune_cookie=True, enable_reindeer=True,
                enable_grimoire_spell_spam=True, enable_wrinkler_popper=False,
                enable_sugar_lump_harvest=False), patch('app.core.run.time.sleep'):
            runner.detector_loop()
        runner.bridge.click_fortune.assert_called_once()
        runner.bridge.pop_reindeer.assert_called_once()
        runner.bridge.pop_golden_cookie.assert_not_called()
        runner.bridge.cast_grimoire_spell_when_full.assert_not_called()
        runner.release_simple_farm()
        self.assertFalse(runner._simple_farm_active)


if __name__ == "__main__":
    unittest.main()
