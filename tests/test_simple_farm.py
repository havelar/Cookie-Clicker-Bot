import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from app.bridge.js_bridge import CookieClickerBridge
from app.config.settings import AutomationConfig
from app.core.simple_farm import SimpleFarmAutomation
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
            "results": ["click frenzy", "frenzy"],
            "quality": "Click Frenzy + Frenzy",
            "minimumTowers": 501,
            "finalTowers": 1,
        }
        self.reinvest_result = {"ok": False, "waiting": True, "message": "caixa protegido"}

    def get_combo_snapshot(self):
        self.calls.append(("snapshot",))
        return self.state

    def forecast_simple_farm_pair(self, ahead):
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

    def execute_simple_farm_dualcast(self, **kwargs):
        self.calls.append(("dualcast", kwargs))
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
            "ok": True, "kind": "upgrade", "count": 1, "spent": 50_000,
            "message": "Upgrade comprado",
        }
        automation = SimpleFarmAutomation(
            bridge,
            ConfiguracaoSimpleFarm(reserva_caixa=0.30, investimento_por_ciclo=0.10),
            relogio=lambda: 100.0,
        )

        report = automation.executar_passo()

        self.assertEqual(report.upgrades_comprados, 1)
        call = next(call[1] for call in bridge.calls if call[0] == "reinvest")
        self.assertEqual(call["cash_floor"], 300_000)
        self.assertEqual(call["max_spend_fraction"], 0.10)
        self.assertEqual(call["minimum_towers"], 501)

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
        self.assertNotIn("dualcast", [call[0] for call in bridge.calls])

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

    def test_ready_natural_multiplier_executes_dualcast_without_lump_options(self):
        bridge = FakeSimpleFarmBridge(snapshot(buffs=[{
            "name": "Frenzy", "type": "frenzy", "timeSeconds": 30, "multCpS": 7,
        }]))

        report = SimpleFarmAutomation(bridge, ConfiguracaoSimpleFarm()).executar_passo()

        self.assertEqual(report.estado, EstadoSimpleFarm.EXECUTANDO)
        call = next(call[1] for call in bridge.calls if call[0] == "dualcast")
        self.assertEqual(call["minimum_towers"], 501)
        self.assertEqual(call["final_towers"], 1)
        self.assertNotIn("use_loans", call)
        self.assertNotIn("use_sugar_frenzy", call)

    def test_dragonflight_blocks_dualcast_and_skip(self):
        bridge = FakeSimpleFarmBridge(snapshot(buffs=[{
            "name": "Dragonflight", "type": "dragonflight", "timeSeconds": 20,
        }]))

        report = SimpleFarmAutomation(bridge, ConfiguracaoSimpleFarm()).executar_passo()

        self.assertEqual(report.estado, EstadoSimpleFarm.AGUARDANDO_BUFF)
        self.assertNotIn("dualcast", [call[0] for call in bridge.calls])
        self.assertNotIn("skip", [call[0] for call in bridge.calls])

    def test_natural_click_frenzy_triggers_tower_sale_dualcast(self):
        bridge = FakeSimpleFarmBridge(snapshot(buffs=[{
            "name": "Click frenzy", "type": "click frenzy", "timeSeconds": 12,
            "multCpS": 1, "multClick": 777,
        }]))

        report = SimpleFarmAutomation(bridge, ConfiguracaoSimpleFarm()).executar_passo()

        self.assertEqual(report.estado, EstadoSimpleFarm.EXECUTANDO)
        self.assertIn("dualcast", [call[0] for call in bridge.calls])

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

    def test_plain_frenzy_does_not_click_until_dualcast_is_ready(self):
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

    def test_clicker_starts_before_ready_dualcast(self):
        bridge = FakeSimpleFarmBridge(snapshot(buffs=[{
            "name": "Frenzy", "type": "frenzy", "timeSeconds": 30, "multCpS": 7,
        }]))
        events = []
        original = bridge.execute_simple_farm_dualcast

        def dualcast(**kwargs):
            events.append("dualcast")
            return original(**kwargs)

        bridge.execute_simple_farm_dualcast = dualcast
        automation = SimpleFarmAutomation(
            bridge,
            ConfiguracaoSimpleFarm(),
            habilitar_clicker=lambda: events.append("start") or True,
        )

        automation.executar_passo()

        self.assertEqual(events[:2], ["start", "dualcast"])


class SimpleFarmBridgeTests(unittest.TestCase):
    class StubBridge(CookieClickerBridge):
        def __init__(self, responses):
            self.responses = list(responses)
            self.scripts = []

        def execute_js(self, code):
            self.scripts.append(code)
            return self.responses.pop(0)

    def test_invalid_dualcast_is_rejected_before_javascript(self):
        bridge = self.StubBridge([])

        result = bridge.execute_simple_farm_dualcast(
            expected_cast=1,
            expected_results=["clot", "click frenzy"],
            minimum_buff_seconds=8,
            minimum_towers=501,
            final_towers=1,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(bridge.scripts, [])

    def test_invalid_reinvestment_budget_never_reaches_javascript(self):
        bridge = self.StubBridge([])

        result = bridge.reinvest_simple_farm(100, 0.99, 501)

        self.assertFalse(result["ok"])
        self.assertEqual(bridge.scripts, [])

    def test_reinvestment_script_protects_cash_and_uses_building_roi(self):
        bridge = self.StubBridge([{"ok": True}])

        bridge.reinvest_simple_farm(1e40, 0.10, 501)

        script = bridge.scripts[0]
        self.assertIn("cashFloor", script)
        self.assertIn("luckyReserve", script)
        self.assertIn("rebuyReserve", script)
        self.assertIn("roi:gain/price", script)
        self.assertIn("purchases<25", script)
        self.assertIn("name==='sugar frenzy'", script)
        self.assertIn("name==='chocolate egg'", script)
        self.assertNotIn("Game.lumps-=", script)
        self.assertNotIn("takeLoan", script)

    def test_dualcast_script_has_hard_resource_guarantees(self):
        bridge = self.StubBridge([{"ok": True}])

        bridge.execute_simple_farm_dualcast(
            expected_cast=1,
            expected_results=["click frenzy", "frenzy"],
            minimum_buff_seconds=8,
            minimum_towers=501,
            final_towers=1,
        )

        script = bridge.scripts[0]
        self.assertIn("lumpsBefore", script)
        self.assertNotIn("Game.lumps-=", script)
        self.assertNotIn("takeLoan", script)
        self.assertNotIn("slotGod", script)
        self.assertNotIn("getGarden", script)
        self.assertIn("restore()", script)
        self.assertIn("M.computeMagicM()", script)

    def test_double_click_frenzy_is_an_accepted_immediate_pair(self):
        bridge = self.StubBridge([{"ok": True}])

        result = bridge.execute_simple_farm_dualcast(
            expected_cast=1017,
            expected_results=["click frenzy", "click frenzy"],
            minimum_buff_seconds=8,
            minimum_towers=501,
            final_towers=1,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(len(bridge.scripts), 1)


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
        window.close()

    def test_defaults_are_fast_and_disabled(self):
        config = AutomationConfig()
        self.assertFalse(config.enable_simple_farm)
        self.assertEqual(config.simple_farm_poll_interval_seconds, 0.2)
        self.assertEqual(config.simple_farm_minimum_buff_seconds, 8.0)
        self.assertEqual(config.simple_farm_cash_reserve_percent, 30.0)
        self.assertEqual(config.simple_farm_investment_percent, 10.0)


if __name__ == "__main__":
    unittest.main()
