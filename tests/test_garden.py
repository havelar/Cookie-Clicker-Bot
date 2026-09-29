"""Testes da bridge, catálogo, planejamento, UI e segurança do Garden."""
from collections import Counter
import os
import unittest
from unittest.mock import Mock

from app.bridge.js_bridge import CookieClickerBridge
from app.config.settings import AutomationConfig, automation_config
from app.core.fazendeira import Fazendeira
from app.core.garden_catalog import GARDEN_CATALOG, TARGET_SEED_KEYS, validate_catalog
from app.models.garden import (
    GardenActionResult,
    GardenCycleResult,
    GardenGoal,
    GardenPlan,
    GardenPlant,
    GardenSeed,
    GardenSnapshot,
    GardenSoil,
    GardenStatus,
)


def snapshot(
    unlocked, plants=(), *, available=True, soil="dirt", tiles=None,
    next_tick_at=None,
):
    seeds = tuple(
        GardenSeed(
            index, key, recipe.name, key in unlocked, key != "queenbeetLump", 50,
            weed=key == "meddleweed",
            fungus=key in {"whiteMildew", "brownMold", "crumbspore", "doughshroom"},
        )
        for index, (key, recipe) in enumerate(GARDEN_CATALOG.items())
    )
    tiles = tiles or tuple((x, y) for y in range(1, 5) for x in range(1, 5))
    soils = (
        GardenSoil(0, "dirt", "Terra", 0, 5, True),
        GardenSoil(1, "fertilizer", "Fertilizante", 50, 3, True),
        GardenSoil(4, "woodchips", "Lascas de madeira", 300, 5, True),
    )
    return GardenSnapshot(
        GardenStatus(available, available, "Garden disponível" if available else "Indisponível"),
        farm_level=9, farm_amount=500, soil_key=soil, plot_width=4, plot_height=4,
        next_tick_at=next_tick_at, unlocked_tiles=tiles, seeds=seeds,
        plants=tuple(plants), soils=soils,
    )


class FakeGardenBridge:
    def __init__(self, current):
        self.current = current
        self.mutable_calls = []

    def get_garden_snapshot(self):
        return self.current

    def plant_garden_seed(self, key, x, y):
        self.mutable_calls.append(("plant", key, x, y))
        return GardenActionResult(True, "plant", "Plantio confirmado", x=x, y=y, seed_key=key)

    def harvest_garden_tile(self, x, y, **options):
        self.mutable_calls.append(("harvest", options.get("expected_key"), x, y))
        return GardenActionResult(True, "harvest", "Colheita confirmada", x=x, y=y)

    def change_garden_soil(self, key):
        self.mutable_calls.append(("soil", key))
        return GardenActionResult(True, "change_soil", "Solo confirmado", soil_key=key)

    def set_garden_frozen(self, frozen):
        self.mutable_calls.append(("freeze", frozen))
        return GardenActionResult(True, "set_freeze", "Estado confirmado")


class GardenCatalogTests(unittest.TestCase):
    def test_catalog_has_all_runtime_plants_and_valid_dependencies(self):
        self.assertEqual(len(GARDEN_CATALOG), 34)
        self.assertEqual(validate_catalog(), ())
        self.assertEqual(set(Fazendeira.ESTRATEGIAS_POR_PLANTA), set(TARGET_SEED_KEYS))
        self.assertEqual(GARDEN_CATALOG["queenbeetLump"].parents[0].count, 8)
        self.assertEqual(GARDEN_CATALOG["everdaisy"].parents[0].count, 3)
        self.assertEqual(GARDEN_CATALOG["everdaisy"].parents[1].count, 3)
        self.assertEqual(GARDEN_CATALOG["whiteMildew"].maximum_neighbors, (("whiteMildew", 1),))
        self.assertEqual(GARDEN_CATALOG["shriekbulb"].parents[0].key, "duketater")
        self.assertEqual(GARDEN_CATALOG["shriekbulb"].parents[0].count, 3)
        self.assertFalse(GARDEN_CATALOG["shriekbulb"].parents[0].mature)
        self.assertEqual(GARDEN_CATALOG["bakerWheat"].name, "Baker's wheat")
        self.assertEqual(GARDEN_CATALOG["queenbeetLump"].name, "Juicy queenbeet")

    def test_automation_default_is_disabled_and_interval_is_conservative(self):
        config = AutomationConfig()
        self.assertFalse(config.enable_garden_automation)
        self.assertGreaterEqual(config.garden_poll_interval_seconds, 30)


class FazendeiraPlanningTests(unittest.TestCase):
    def test_priority_changes_with_unlocked_dependencies(self):
        farmer = Fazendeira(FakeGardenBridge(snapshot({"bakerWheat"})))
        first = farmer.select_next_goal(snapshot({"bakerWheat"}))
        second = farmer.select_next_goal(snapshot({"bakerWheat", "thumbcorn"}))
        self.assertEqual(first.target_key, "thumbcorn")
        self.assertEqual(second.target_key, "cronerice")
        self.assertNotEqual(first.target_key, second.target_key)

    def test_plan_uses_generic_stripes_and_never_harvests_parents(self):
        six_by_six = tuple((x, y) for y in range(6) for x in range(6))
        current = snapshot({"bakerWheat"}, tiles=six_by_six)
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        self.assertEqual(plan.goal.target_key, "thumbcorn")
        plant_actions = [action for action in plan.actions if action.kind == "plant"]
        self.assertEqual(len(plant_actions), 10)
        self.assertIn("layout genérico", plan.explanation)
        self.assertIn("layout máximo de 10 plantas", plan.explanation)
        self.assertFalse(any(action.kind == "harvest" for action in plan.actions))
        positions = {(action.x, action.y) for action in plant_actions}
        self.assertEqual(positions, {
            (0, 1), (1, 1), (3, 1), (4, 1), (5, 1),
            (0, 4), (1, 4), (3, 4), (4, 4), (5, 4),
        })

    def test_two_different_parents_alternate_in_generic_layout(self):
        six_by_six = tuple((x, y) for y in range(6) for x in range(6))
        current = snapshot({"bakerWheat", "thumbcorn"}, tiles=six_by_six)
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        plants = [action for action in plan.actions if action.kind == "plant"]
        self.assertEqual(plan.goal.target_key, "cronerice")
        self.assertEqual({action.seed_key for action in plants}, {"bakerWheat", "thumbcorn"})
        self.assertEqual(len(plants), 10)
        layout = {(action.x, action.y): action.seed_key for action in plants}
        self.assertEqual(
            [layout.get((x, 1)) for x in range(6)],
            ["bakerWheat", "thumbcorn", "bakerWheat", None, "thumbcorn", "bakerWheat"],
        )
        self.assertEqual(
            [layout.get((x, 4)) for x in range(6)],
            ["bakerWheat", "thumbcorn", None, "bakerWheat", "thumbcorn", "bakerWheat"],
        )
    def test_juicy_queenbeet_uses_four_complete_rings_on_maximum_garden(self):
        six_by_six = tuple((x, y) for y in range(6) for x in range(6))
        unlocked = set(TARGET_SEED_KEYS) - {"queenbeetLump"}
        current = snapshot(unlocked, tiles=six_by_six)
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        plants = [action for action in plan.actions if action.kind == "plant"]
        layout = {(action.x, action.y): action.seed_key for action in plants}

        self.assertEqual(plan.goal.target_key, "queenbeetLump")
        self.assertEqual(len(plants), 32)
        self.assertEqual({action.seed_key for action in plants}, {"queenbeet"})
        self.assertNotIn("layout genérico", plan.explanation)
        self.assertIn("4 espaços", plan.explanation)
        self.assertEqual(
            tuple("".join("Q" if (x, y) in layout else "." for x in range(6)) for y in range(6)),
            ("QQQQQQ", "Q.QQ.Q", "QQQQQQ", "QQQQQQ", "Q.QQ.Q", "QQQQQQ"),
        )
        mutation_tiles = set(six_by_six) - set(layout)
        self.assertEqual(mutation_tiles, {(1, 1), (4, 1), (1, 4), (4, 4)})
        self.assertTrue(all(
            sum(neighbor in layout for neighbor in Fazendeira._neighbors(position)) == 8
            for position in mutation_tiles
        ))

    def test_juicy_queenbeet_falls_back_to_one_ring_on_smaller_garden(self):
        unlocked = set(TARGET_SEED_KEYS) - {"queenbeetLump"}
        current = snapshot(unlocked)
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        plants = [action for action in plan.actions if action.kind == "plant"]

        self.assertEqual(plan.goal.target_key, "queenbeetLump")
        self.assertEqual(len(plants), 8)
        self.assertEqual({action.seed_key for action in plants}, {"queenbeet"})
        self.assertIn("anel", plan.explanation)

    def test_shriekbulb_prefers_three_duketaters_of_any_age(self):
        six_by_six = tuple((x, y) for y in range(6) for x in range(6))
        unlocked = set(TARGET_SEED_KEYS) - {"shriekbulb"}
        current = snapshot(unlocked, tiles=six_by_six)
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        plants = [action for action in plan.actions if action.kind == "plant"]

        self.assertEqual(plan.goal.target_key, "shriekbulb")
        self.assertEqual(len(plants), 3)
        self.assertEqual({action.seed_key for action in plants}, {"duketater"})
        self.assertEqual(plan.goal.parent_names, ("3× Duketater",))

    def test_golden_clover_uses_optimized_maximum_garden_layout(self):
        six_by_six = tuple((x, y) for y in range(6) for x in range(6))
        unlocked = set(TARGET_SEED_KEYS) - {"goldenClover"}
        current = snapshot(unlocked, tiles=six_by_six)
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        plants = [action for action in plan.actions if action.kind == "plant"]
        layout = {(action.x, action.y): action.seed_key for action in plants}

        self.assertEqual(plan.goal.target_key, "goldenClover")
        self.assertEqual(len(plants), 20)
        self.assertEqual(set(layout.values()), {"clover"})
        self.assertIn("setup otimizado específico", plan.explanation)
        self.assertIn("16 espaços", plan.explanation)
        self.assertEqual(
            tuple("".join("G" if (x, y) in layout else "." for x in range(6)) for y in range(6)),
            ("G.G..G", ".GGGGG", "GG....", "....GG", "GGGGG.", "G..G.G"),
        )

        recipe = GARDEN_CATALOG["goldenClover"]
        mutation_tiles = set(six_by_six) - set(layout)
        self.assertEqual(len(mutation_tiles), 16)
        neighbor_counts = Counter(
            sum(neighbor in layout for neighbor in Fazendeira._neighbors(position))
            for position in mutation_tiles
        )
        self.assertEqual(neighbor_counts, Counter({4: 14, 5: 2}))
        self.assertTrue(all(
            Fazendeira(FakeGardenBridge(current))._intended_tile_matches(
                position, layout, {}, recipe,
            )
            for position in mutation_tiles
        ))

    def test_golden_clover_falls_back_to_local_ring_on_smaller_garden(self):
        unlocked = set(TARGET_SEED_KEYS) - {"goldenClover"}
        current = snapshot(unlocked)
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        plants = [action for action in plan.actions if action.kind == "plant"]

        self.assertEqual(plan.goal.target_key, "goldenClover")
        self.assertEqual(len(plants), 4)
        self.assertEqual({action.seed_key for action in plants}, {"clover"})
        self.assertIn("anel", plan.explanation)

    def test_mature_golden_clover_layout_switches_to_woodchips(self):
        six_by_six = tuple((x, y) for y in range(6) for x in range(6))
        unlocked = set(TARGET_SEED_KEYS) - {"goldenClover"}
        empty = snapshot(unlocked, tiles=six_by_six)
        initial = Fazendeira(FakeGardenBridge(empty)).build_plan(empty)
        plants = tuple(
            GardenPlant(
                action.x, action.y, 0, "clover", "Ordinary clover", 55, 50, True,
            )
            for action in initial.actions if action.kind == "plant"
        )
        current = snapshot(unlocked, plants, tiles=six_by_six)
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)

        self.assertEqual(len(plan.actions), 1)
        self.assertEqual(plan.actions[0].kind, "change_soil")
        self.assertEqual(plan.actions[0].soil_key, "woodchips")
        self.assertIn("16 espaços", plan.explanation)

    def test_mature_target_is_harvested_before_completing_next_layout(self):
        six_by_six = tuple((x, y) for y in range(6) for x in range(6))
        plant = GardenPlant(2, 2, 1, "thumbcorn", "Thumbcorn", 55, 50, True)
        current = snapshot({"bakerWheat"}, (plant,), tiles=six_by_six)
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        self.assertEqual(plan.goal.target_key, "thumbcorn")
        self.assertEqual(plan.actions[0].kind, "harvest")
        self.assertTrue(plan.actions[0].require_mature)
        plant_actions = [action for action in plan.actions if action.kind == "plant"]
        self.assertEqual(len(plant_actions), 10)
        self.assertEqual(
            {action.seed_key for action in plant_actions},
            {"bakerWheat", "thumbcorn"},
        )
        self.assertIn("Cronerice", plan.explanation)

    def test_immature_target_is_protected_while_next_layout_is_prepared(self):
        six_by_six = tuple((x, y) for y in range(6) for x in range(6))
        target = GardenPlant(2, 2, 1, "thumbcorn", "Thumbcorn", 10, 50, False)
        current = snapshot({"bakerWheat"}, (target,), tiles=six_by_six)
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        self.assertFalse(any(
            action.kind == "harvest" and (action.x, action.y) == (2, 2)
            for action in plan.actions
        ))
        self.assertFalse(any(
            action.kind == "plant" and (action.x, action.y) == (2, 2)
            for action in plan.actions
        ))
        plants = [action for action in plan.actions if action.kind == "plant"]
        self.assertEqual(len(plants), 6)
        self.assertEqual({action.seed_key for action in plants}, {"bakerWheat"})
        self.assertIn("Cronerice", plan.explanation)

    def test_immature_target_already_in_next_layout_is_reused(self):
        six_by_six = tuple((x, y) for y in range(6) for x in range(6))
        target = GardenPlant(1, 1, 1, "thumbcorn", "Thumbcorn", 10, 50, False)
        current = snapshot({"bakerWheat"}, (target,), tiles=six_by_six)
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        self.assertFalse(any(
            (action.x, action.y) == (1, 1)
            for action in plan.actions if action.kind in {"harvest", "plant"}
        ))

    def test_all_locked_discoveries_are_protected_while_pipeline_advances(self):
        six_by_six = tuple((x, y) for y in range(6) for x in range(6))
        older = GardenPlant(5, 5, 1, "thumbcorn", "Thumbcorn", 20, 50, False)
        newer = GardenPlant(0, 0, 2, "cronerice", "Cronerice", 2, 50, False)
        current = snapshot({"bakerWheat"}, (older, newer), tiles=six_by_six)
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        protected = {(5, 5), (0, 0)}
        self.assertEqual(len(Fazendeira(FakeGardenBridge(current))._pending_discoveries(current)), 2)
        self.assertFalse(any(
            action.kind == "harvest" and (action.x, action.y) in protected
            for action in plan.actions
        ))
        self.assertIn("2 descoberta(s)", plan.explanation)

    def test_harvesting_one_discovery_does_not_remove_another_immature_one(self):
        six_by_six = tuple((x, y) for y in range(6) for x in range(6))
        mature = GardenPlant(5, 5, 1, "thumbcorn", "Thumbcorn", 55, 50, True)
        immature = GardenPlant(0, 0, 2, "cronerice", "Cronerice", 2, 50, False)
        current = snapshot({"bakerWheat"}, (mature, immature), tiles=six_by_six)
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        self.assertTrue(any(
            action.kind == "harvest" and (action.x, action.y) == (5, 5)
            and action.require_mature for action in plan.actions
        ))
        self.assertFalse(any(
            action.kind == "harvest" and (action.x, action.y) == (0, 0)
            for action in plan.actions
        ))

    def test_reconciliation_removes_wrong_plants_keeps_correct_and_replants_same_tick(self):
        six_by_six = tuple((x, y) for y in range(6) for x in range(6))
        empty = snapshot({"bakerWheat"}, tiles=six_by_six)
        initial_plan = Fazendeira(FakeGardenBridge(empty)).build_plan(empty)
        intended = [action for action in initial_plan.actions if action.kind == "plant"]
        correct_action, wrong_action = intended[0], intended[1]
        correct = GardenPlant(
            correct_action.x, correct_action.y, 0, correct_action.seed_key,
            "Baker's wheat", 10, 50, False,
        )
        wrong = GardenPlant(
            wrong_action.x, wrong_action.y, 1, "cronerice", "Cronerice", 10, 50, False,
        )
        stray = GardenPlant(5, 5, 1, "cronerice", "Cronerice", 10, 50, False)
        current = snapshot({"bakerWheat", "cronerice"}, (correct, wrong, stray), tiles=six_by_six)
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        harvest_positions = {
            (action.x, action.y) for action in plan.actions if action.kind == "harvest"
        }
        plant_positions = {
            (action.x, action.y) for action in plan.actions if action.kind == "plant"
        }
        self.assertNotIn((correct.x, correct.y), harvest_positions)
        self.assertNotIn((correct.x, correct.y), plant_positions)
        self.assertIn((wrong.x, wrong.y), harvest_positions)
        self.assertIn((wrong.x, wrong.y), plant_positions)
        self.assertIn((stray.x, stray.y), harvest_positions)

    def test_real_cycle_executes_entire_plan_even_above_old_eight_action_limit(self):
        six_by_six = tuple((x, y) for y in range(6) for x in range(6))
        bridge = FakeGardenBridge(snapshot({"bakerWheat"}, tiles=six_by_six))
        result = Fazendeira(bridge).run_cycle(dry_run=False, automation_enabled=True)
        self.assertGreater(len(result.plan.actions), 8)
        self.assertEqual(len(result.action_results), len(result.plan.actions))

    def test_one_failed_action_does_not_abort_the_rest_of_the_tick_plan(self):
        bridge = FakeGardenBridge(snapshot({"bakerWheat"}))

        def fail_soil(key):
            bridge.mutable_calls.append(("soil", key))
            return GardenActionResult(False, "change_soil", "Cooldown de solo", soil_key=key)

        bridge.change_garden_soil = fail_soil
        result = Fazendeira(bridge).run_cycle(dry_run=False, automation_enabled=True)
        self.assertFalse(result.action_results[0].success)
        self.assertTrue(any(item.success for item in result.action_results[1:]))
        self.assertEqual(len(result.action_results), len(result.plan.actions))

    def test_real_reconciliation_runs_only_once_for_same_tick_token(self):
        bridge = FakeGardenBridge(snapshot({"bakerWheat"}, next_tick_at=1_234.5))
        farmer = Fazendeira(bridge)
        first = farmer.run_cycle(dry_run=False, automation_enabled=True)
        first_call_count = len(bridge.mutable_calls)
        second = farmer.run_cycle(dry_run=False, automation_enabled=True)
        self.assertTrue(first.action_results)
        self.assertEqual(second.action_results, ())
        self.assertEqual(len(bridge.mutable_calls), first_call_count)
        bridge.current = snapshot({"bakerWheat"}, next_tick_at=1_999.5)
        third = farmer.run_cycle(dry_run=False, automation_enabled=True)
        self.assertTrue(third.action_results)
        self.assertGreater(len(bridge.mutable_calls), first_call_count)

    def test_dry_run_and_disabled_real_mode_never_call_mutable_bridge(self):
        bridge = FakeGardenBridge(snapshot({"bakerWheat"}))
        farmer = Fazendeira(bridge)
        simulated = farmer.run_cycle(dry_run=True, automation_enabled=True)
        unauthorized = farmer.run_cycle(dry_run=False, automation_enabled=False)
        self.assertTrue(simulated.dry_run)
        self.assertTrue(unauthorized.dry_run)
        self.assertEqual(bridge.mutable_calls, [])
        self.assertTrue(simulated.plan.actions)

    def test_enabled_real_mode_executes_prebuilt_plan(self):
        bridge = FakeGardenBridge(snapshot({"bakerWheat"}))
        result = Fazendeira(bridge, clock=lambda: 1_000).run_cycle(
            dry_run=False, automation_enabled=True,
        )
        self.assertFalse(result.dry_run)
        self.assertTrue(bridge.mutable_calls)
        self.assertEqual(len(result.action_results), len(bridge.mutable_calls))
        self.assertTrue(all(item.success for item in result.action_results))

    def test_unavailable_snapshot_has_no_goal_or_actions(self):
        current = snapshot(set(), available=False)
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        self.assertIsNone(plan.goal)
        self.assertEqual(plan.actions, ())
        self.assertTrue(plan.waiting)


class GardenBridgeTests(unittest.TestCase):
    def test_invalid_response_becomes_unavailable_snapshot(self):
        bridge = CookieClickerBridge()
        bridge.execute_js = Mock(return_value=None)
        result = bridge.get_garden_snapshot()
        self.assertFalse(result.status.available)
        self.assertIn("inválida", result.status.message)

    def test_disconnected_action_returns_clear_error(self):
        bridge = CookieClickerBridge()
        bridge.execute_js = Mock(return_value=None)
        result = bridge.plant_garden_seed("bakerWheat", 2, 2)
        self.assertFalse(result.success)
        self.assertIn("bridge desconectada", result.message)

    def test_invalid_coordinates_do_not_reach_javascript(self):
        bridge = CookieClickerBridge()
        bridge.execute_js = Mock()
        result = bridge.harvest_garden_tile(9, 2, expected_key="bakerWheat")
        self.assertFalse(result.success)
        bridge.execute_js.assert_not_called()


class GardenUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_tab_exposes_simulation_progress_and_explicit_real_toggle(self):
        from app.ui.main_window import MainWindow
        previous = automation_config.enable_garden_automation
        automation_config.enable_garden_automation = False
        try:
            window = MainWindow()
            tabs = [window.tabs.tabText(index) for index in range(window.tabs.count())]
            self.assertIn("Garden", tabs)
            self.assertEqual(window.garden_simulate_button.text(), "Simular próximo tick")
            self.assertEqual(window.garden_auto_checkbox.text(), "Automação real")
            self.assertFalse(window.garden_auto_checkbox.isChecked())
            self.assertGreaterEqual(window.garden_interval_input.minimum(), 30)
            self.assertTrue(window.garden_refresh_timer.isSingleShot())
            window.close()
        finally:
            automation_config.enable_garden_automation = previous

    def test_valid_result_displays_one_explainable_goal(self):
        from app.ui.main_window import MainWindow
        current = snapshot({"bakerWheat"})
        goal = GardenGoal(
            "thumbcorn", "Thumbcorn", ("bakerWheat",), ("2× Baker's wheat",),
            "Libera novas dependências.", (), "Colher madura.", "mutacao_adjacente",
        )
        result = GardenCycleResult(
            current, GardenPlan(goal, explanation="Plano seguro.", waiting=True), True,
        )
        window = MainWindow()
        window._display_garden_result(result)
        self.assertEqual(window.garden_goal_label.text(), "Thumbcorn")
        self.assertIn("2× Baker's wheat", window.garden_parents_label.text())
        self.assertIn("Libera novas dependências", window.garden_reason_label.text())
        self.assertIn("Simulação concluída", window.garden_feedback_label.text())
        window.close()


if __name__ == "__main__":
    unittest.main()
