import os
import threading
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from app.bridge.js_bridge import CookieClickerBridge
from app.config.settings import AutomationConfig
from app.core.combo import ComboAutomation
from app.core.run import AutomationRunner
from app.models.combo import ConfiguracaoCombo, EstadoCombo, PlanoCombo, RelatorioCombo
from app.models.garden import (
    GardenActionResult,
    GardenPlant,
    GardenSeed,
    GardenSnapshot,
    GardenStatus,
)
from app.ui.main_window import MainWindow


RESULTS = ["blood frenzy", "click frenzy", "frenzy", "building special"]


def combo_snapshot(**changes):
    value = {
        "available": True,
        "screen": "game",
        "version": "2.053",
        "seed": "test-seed",
        "season": "valentines",
        "cookies": 1e60,
        "cookiesEarned": 1e61,
        "achievementWon": False,
        "lumps": 1200,
        "canRefillLump": True,
        "lumpRefillRemaining": 0,
        "spellsCastTotal": 10,
        "magic": 100.0,
        "magicM": 100.0,
        "skipSpellCost": 10.0,
        "wizardTowers": 601,
        "wizardTowerLevel": 10,
        "auras": [4, 13],
        "pantheonSwaps": 0,
        "pantheonSlots": [2, 8, 6],
        "officeLevel": 5,
        "goldenSwitchOn": False,
        "sugarFrenzyUsed": False,
        "buildings": [{"id": 0, "name": "Cursor", "amount": 601, "level": 15}],
        "buffs": [],
        "shimmers": [],
    }
    value.update(changes)
    return value


def mature_garden():
    return GardenSnapshot(
        status=GardenStatus(True, True, "Garden disponível"),
        soil_key="clay",
        unlocked_tiles=((0, 0), (1, 0)),
        seeds=(
            GardenSeed(0, "goldenClover", "Golden clover", True, True, 50),
            GardenSeed(1, "nursetulip", "Nursetulip", True, True, 50),
        ),
        plants=(
            GardenPlant(0, 0, 0, "goldenClover", "Golden clover", 100, 50, True),
            GardenPlant(1, 0, 1, "nursetulip", "Nursetulip", 100, 50, True),
        ),
    )


def empty_garden():
    garden = mature_garden()
    return GardenSnapshot(
        status=garden.status,
        soil_key="fertilizer",
        unlocked_tiles=garden.unlocked_tiles,
        seeds=garden.seeds,
        plants=(),
    )


def full_garden(clovers_mature=24, tulips_mature=12, empty_tiles=()):
    garden = mature_garden()
    tiles = tuple((x, y) for y in range(6) for x in range(6))
    plants = []
    counts = {"goldenClover": 0, "nursetulip": 0}
    mature_counts = {"goldenClover": clovers_mature, "nursetulip": tulips_mature}
    for x, y in tiles:
        key = "nursetulip" if x % 3 == 1 else "goldenClover"
        is_mature = counts[key] < mature_counts[key]
        counts[key] += 1
        if (x, y) in empty_tiles:
            continue
        plants.append(GardenPlant(
            x, y, int(key == "nursetulip"), key, key,
            60 if is_mature else 0, 50, is_mature,
        ))
    return replace(garden, unlocked_tiles=tiles, plants=tuple(plants))


def ready_buffs():
    return [
        {"name": "Frenzy", "type": "frenzy", "timeSeconds": 30},
        {"name": "Dragon Harvest", "type": "dragon harvest", "timeSeconds": 30},
        {"name": "High-five", "type": "building buff", "timeSeconds": 30, "buildingId": 0},
        {"name": "Congregation", "type": "building buff", "timeSeconds": 30, "buildingId": 6},
    ]


class FakeComboBridge:
    def __init__(self, snapshots=None):
        self.snapshots = list(snapshots or [combo_snapshot()])
        self.calls = []
        self.forecast = {
            "ok": True,
            "seed": "test-seed",
            "version": "2.053",
            "currentCast": 10,
            "startCast": 10,
            "skipCount": 0,
            "season": "valentines",
            "results": RESULTS,
            "spellBuildingSpecials": 1,
            "naturalBuildingSpecials": 2,
            "score": 500,
        }
        self.garden = mature_garden()
        self.quadcast_result = {"ok": True, "lumpsSpent": 2, "clickSeconds": 8}

    def get_combo_snapshot(self):
        self.calls.append(("snapshot",))
        if len(self.snapshots) > 1:
            return self.snapshots.pop(0)
        return self.snapshots[0]

    def forecast_combo_window(self, ahead, building_specials):
        self.calls.append(("forecast", ahead, building_specials))
        return dict(self.forecast)

    def get_garden_snapshot(self):
        self.calls.append(("garden",))
        return self.garden

    def change_garden_soil(self, soil):
        self.calls.append(("soil", soil))
        self.garden = replace(self.garden, soil_key=soil)
        return GardenActionResult(True, "soil", "Solo atualizado")

    def pop_combo_natural_shimmer(self, shimmer_id):
        self.calls.append(("pop", shimmer_id))
        return {"ok": True}

    def pop_combo_cookie_storm_drops(self):
        self.calls.append(("storm",))
        return {"ok": True, "count": 7}

    def cast_combo_skip(self, expected_cast, spell_id):
        self.calls.append(("skip", expected_cast, spell_id))
        return {"ok": True, "message": "skip confirmado"}

    def refill_combo_magic(self, expected_cast):
        self.calls.append(("refill", expected_cast))
        return {"ok": True, "lumpsSpent": 1}

    def execute_combo_quadcast(self, **kwargs):
        self.calls.append(("quadcast", kwargs))
        return dict(self.quadcast_result)

    def plant_garden_seed(self, seed_key, x, y):
        self.calls.append(("plant", seed_key, x, y))
        return GardenActionResult(True, "plant", "Plantio confirmado", x=x, y=y, seed_key=seed_key)

    def set_combo_wizard_towers(self, target):
        self.calls.append(("towers", target))
        return {"ok": True}

    def ensure_combo_building_minimum(self, building_id, minimum):
        self.calls.append(("minimum", building_id, minimum))
        return {"ok": True}


class ComboStateMachineTests(unittest.TestCase):
    def test_garden_grows_in_fertilizer_then_collects_in_clay(self):
        bridge = FakeComboBridge()
        bridge.garden = full_garden(3, 2)
        automation = ComboAutomation(bridge, ConfiguracaoCombo())
        self.assertEqual(automation.executar_passo().estado, EstadoCombo.PREPARANDO)
        self.assertIn(("soil", "fertilizer"), bridge.calls)
        bridge.garden = replace(full_garden(12, 6), soil_key="fertilizer")
        self.assertEqual(automation.executar_passo().estado, EstadoCombo.PREPARANDO)
        self.assertIn(("soil", "clay"), bridge.calls)

    def test_spell_frenzy_can_supply_missing_or_short_natural_frenzy(self):
        for frenzy in ([], [{"type": "frenzy", "timeSeconds": 1}]):
            bridge = FakeComboBridge([combo_snapshot(buffs=frenzy + ready_buffs()[1:3])])
            bridge.forecast.update(naturalBuildingSpecials=1)
            report = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()
            self.assertEqual(report.estado, EstadoCombo.CLICANDO)

    def test_no_spell_frenzy_still_requires_natural_frenzy(self):
        bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs()[1:])])
        bridge.forecast.update(results=["blood frenzy", "click frenzy", "building special", "building special"])
        report = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()
        self.assertEqual(report.estado, EstadoCombo.AGUARDANDO_BUFFS)
        self.assertIn("Frenzy", report.mensagem)

    def test_negative_buffs_and_dragonflight_wait_without_casting(self):
        for effect in ("clot", "building debuff", "cursed finger", "dragonflight"):
            bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs() + [{"type": effect, "timeSeconds": 4}])])
            report = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()
            self.assertEqual(report.estado, EstadoCombo.AGUARDANDO_BUFFS)
            self.assertNotIn("quadcast", [c[0] for c in bridge.calls])

    def test_timeout_stops_before_any_new_mutation_even_if_stack_is_ready(self):
        bridge = FakeComboBridge()
        now = [0.0]
        automation = ComboAutomation(bridge, ConfiguracaoCombo(tempo_maximo_espera=60), relogio=lambda: now[0])
        automation.executar_passo()
        bridge.calls.clear()
        bridge.snapshots[0] = combo_snapshot(buffs=ready_buffs())
        now[0] = 60
        report = automation.executar_passo()
        self.assertEqual(report.estado, EstadoCombo.INTERROMPIDO)
        self.assertEqual(bridge.calls, [("snapshot",)])

    def test_transient_preflight_failure_stops_clicker_but_keeps_waiting(self):
        bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs())])
        bridge.quadcast_result = {"ok": False, "retryable": True, "mutated": False, "message": "Buff expirou"}
        events = []
        automation = ComboAutomation(bridge, ConfiguracaoCombo(),
                                     habilitar_clicker=lambda: events.append("start") or True,
                                     desabilitar_clicker=lambda: events.append("stop") or True)
        report = automation.executar_passo()
        self.assertEqual(report.estado, EstadoCombo.AGUARDANDO_BUFFS)
        self.assertEqual(events, ["start", "stop"])
        self.assertEqual(report.lumps_gastos, 0)

    def test_clicker_must_start_before_quadcast_and_failure_prevents_spending(self):
        for accepted in (True, False):
            bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs())])
            events = []
            original = bridge.execute_combo_quadcast
            def quadcast(**kwargs):
                events.append("quadcast")
                return original(**kwargs)
            bridge.execute_combo_quadcast = quadcast
            report = ComboAutomation(bridge, ConfiguracaoCombo(),
                habilitar_clicker=lambda: events.append("start") or accepted).executar_passo()
            self.assertEqual(events, ["start", "quadcast"] if accepted else ["start"])
            self.assertEqual(report.estado, EstadoCombo.CLICANDO if accepted else EstadoCombo.ERRO_SEGURO)

    def test_target_does_not_waste_remaining_click_window(self):
        bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs())])
        now = [0.0]
        automation = ComboAutomation(bridge, ConfiguracaoCombo(), relogio=lambda: now[0])
        automation.executar_passo()
        bridge.snapshots[0] = combo_snapshot(cookiesEarned=1e73, buffs=[
            {"type": "blood frenzy"}, {"type": "click frenzy"},
        ])
        now[0] = 2
        self.assertEqual(automation.executar_passo().estado, EstadoCombo.CLICANDO)
        now[0] = 9
        self.assertEqual(automation.executar_passo().estado, EstadoCombo.CONCLUIDO)

    def test_preview_only_reads_snapshot_and_forecast(self):
        bridge = FakeComboBridge()
        report = ComboAutomation(bridge, ConfiguracaoCombo()).gerar_previa()

        self.assertEqual(report.estado, EstadoCombo.PREVIA)
        self.assertEqual(report.plano.cast_inicial, 10)
        self.assertEqual([call[0] for call in bridge.calls], ["snapshot", "forecast"])

    def test_stop_prevents_even_the_first_runtime_read(self):
        bridge = FakeComboBridge()
        automation = ComboAutomation(bridge, ConfiguracaoCombo())
        automation.parar()

        report = automation.executar_passo()

        self.assertEqual(report.estado, EstadoCombo.INTERROMPIDO)
        self.assertEqual(bridge.calls, [])

    def test_collects_only_the_natural_shimmer_selected_by_snapshot(self):
        bridge = FakeComboBridge([combo_snapshot(shimmers=[
            {"id": 41, "force": "", "wrath": False},
        ])])

        report = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()

        self.assertEqual(report.estado, EstadoCombo.PREPARANDO)
        self.assertIn(("pop", 41), bridge.calls)
        self.assertNotIn("quadcast", [call[0] for call in bridge.calls])

    def test_cookie_storm_drops_are_drained_without_stopping_combo(self):
        bridge = FakeComboBridge([combo_snapshot(shimmers=[
            {"id": 51, "force": "cookie storm drop", "wrath": False},
            {"id": 52, "force": "cookie storm drop", "wrath": False},
        ])])

        report = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()

        self.assertEqual(report.estado, EstadoCombo.PREPARANDO)
        self.assertFalse(report.terminal)
        self.assertIn(("storm",), bridge.calls)
        self.assertIn("7 drop(s)", report.mensagem)

    def test_non_storm_forced_shimmer_still_stops_combo_safely(self):
        bridge = FakeComboBridge([combo_snapshot(shimmers=[
            {"id": 53, "force": "click frenzy", "wrath": False},
        ])])

        report = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()

        self.assertEqual(report.estado, EstadoCombo.ERRO_SEGURO)
        self.assertNotIn(("storm",), bridge.calls)

    def test_alignment_casts_one_cheap_spell_and_replans_each_step(self):
        bridge = FakeComboBridge([combo_snapshot(spellsCastTotal=9)])
        bridge.forecast.update(currentCast=9, startCast=10, skipCount=1)

        report = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()

        self.assertEqual(report.estado, EstadoCombo.ALINHANDO)
        self.assertIn(("skip", 9, 4), bridge.calls)
        self.assertIn(("forecast", 5000, 2), bridge.calls)

    def test_alignment_waits_for_maximum_mana_before_casting_cheapest_safe_spell(self):
        bridge = FakeComboBridge([combo_snapshot(spellsCastTotal=9, magic=50, magicM=100, canRefillLump=False)])
        bridge.forecast.update(currentCast=9, startCast=10, skipCount=1)

        report = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()

        self.assertEqual(report.estado, EstadoCombo.ALINHANDO)
        self.assertIn("mana máxima", report.mensagem)
        self.assertNotIn("skip", [call[0] for call in bridge.calls])

    def test_alignment_drains_mana_before_refill_and_stops_at_planned_cast(self):
        bridge = FakeComboBridge([combo_snapshot(
            magic=108, magicM=108, skipSpellCost=20,
        )])
        bridge.forecast.update(startCast=16, skipCount=6)
        automation = ComboAutomation(bridge, ConfiguracaoCombo())
        state = bridge.snapshots[0]

        def cast_skip(expected_cast, spell_id):
            self.assertEqual(expected_cast, state["spellsCastTotal"])
            bridge.calls.append(("skip", expected_cast, spell_id))
            state["magic"] -= state["skipSpellCost"]
            state["spellsCastTotal"] += 1
            bridge.forecast.update(currentCast=state["spellsCastTotal"])
            return {"ok": True}

        def refill(expected_cast):
            self.assertLess(state["magic"], state["skipSpellCost"])
            bridge.calls.append(("refill", expected_cast))
            state["magic"] = min(state["magicM"], state["magic"] + 100)
            state["canRefillLump"] = False
            return {"ok": True, "lumpsSpent": 1}

        bridge.cast_combo_skip = cast_skip
        bridge.refill_combo_magic = refill

        for _ in range(6):
            report = automation.executar_passo()
            self.assertFalse(report.terminal)

        self.assertEqual(state["magic"], 108)
        self.assertEqual(state["spellsCastTotal"], 15)
        self.assertEqual(automation._lumps_gastos, 1)
        self.assertEqual(
            [call for call in bridge.calls if call[0] in {"skip", "refill"}],
            [("skip", cast, 4) for cast in range(10, 15)] + [("refill", 15)],
        )

        # Depois da recarga, chega à janela e preserva a mana restante.
        automation.executar_passo()
        report = automation.executar_passo()
        self.assertEqual(state["spellsCastTotal"], 16)
        self.assertEqual(state["magic"], 88)
        self.assertIn("mana", report.mensagem)
        self.assertEqual(len([c for c in bridge.calls if c[0] == "refill"]), 1)

    def test_alignment_preserves_full_bar_strategy_without_refill_resources(self):
        for budget, lumps, spent in [(0, 1200, 0), (1, 1200, 1), (64, 0, 0)]:
            with self.subTest(budget=budget, lumps=lumps, spent=spent):
                bridge = FakeComboBridge([combo_snapshot(magic=50, lumps=lumps)])
                bridge.forecast.update(startCast=20, skipCount=10)
                automation = ComboAutomation(
                    bridge, ConfiguracaoCombo(maximo_lumps_alinhamento=budget),
                )
                automation._lumps_gastos = spent

                report = automation.executar_passo()

                self.assertFalse(report.terminal)
                self.assertIn("mana máxima", report.mensagem)
                self.assertNotIn("skip", [c[0] for c in bridge.calls])
                self.assertNotIn("refill", [c[0] for c in bridge.calls])

    def test_optional_pause_blocks_all_mutations_with_three_or_fewer_skips(self):
        for remaining in (3, 2, 0):
            with self.subTest(remaining=remaining):
                bridge = FakeComboBridge([combo_snapshot(
                    magic=5, buffs=ready_buffs(),
                    shimmers=[{"id": 90, "force": ""}],
                )])
                bridge.forecast.update(startCast=10 + remaining, skipCount=remaining)
                automation = ComboAutomation(
                    bridge, ConfiguracaoCombo(pausar_antes_ultimos_skips=True),
                )

                report = automation.executar_passo()

                self.assertEqual(report.estado, EstadoCombo.PAUSADO)
                self.assertFalse(report.terminal)
                self.assertEqual([c[0] for c in bridge.calls], ["snapshot", "forecast"])
                # Uma nova previsão não libera a pausa sozinha durante a noite.
                bridge.calls.clear()
                bridge.forecast.update(ok=False)
                report = automation.executar_passo()
                self.assertEqual(report.estado, EstadoCombo.PAUSADO)
                self.assertEqual(bridge.calls, [("snapshot",)])

    def test_optional_pause_releases_only_on_resume_and_replans_before_cast(self):
        bridge = FakeComboBridge()
        bridge.forecast.update(startCast=13, skipCount=3)
        automation = ComboAutomation(
            bridge, ConfiguracaoCombo(pausar_antes_ultimos_skips=True),
        )
        automation.retomar()
        self.assertEqual(automation.executar_passo().estado, EstadoCombo.PAUSADO)
        bridge.calls.clear()
        bridge.forecast.update(startCast=14, skipCount=4)

        automation.retomar()
        report = automation.executar_passo()

        self.assertEqual(report.estado, EstadoCombo.ALINHANDO)
        self.assertEqual(report.plano.cast_inicial, 14)
        self.assertIn(("skip", 10, 4), bridge.calls)
        self.assertLess(
            [c[0] for c in bridge.calls].index("forecast"),
            [c[0] for c in bridge.calls].index("skip"),
        )
        bridge.snapshots[0] = combo_snapshot(spellsCastTotal=11)
        bridge.forecast.update(currentCast=11, skipCount=3)
        self.assertEqual(automation.executar_passo().estado, EstadoCombo.ALINHANDO)
        self.assertIn(("skip", 11, 4), bridge.calls)
        bridge.snapshots[0] = combo_snapshot(spellsCastTotal=14, buffs=ready_buffs())
        bridge.forecast.update(currentCast=14, skipCount=0)
        self.assertEqual(automation.executar_passo().estado, EstadoCombo.CLICANDO)

    def test_stop_while_paused_prevents_any_further_runtime_access(self):
        bridge = FakeComboBridge()
        bridge.forecast.update(startCast=13, skipCount=3)
        automation = ComboAutomation(
            bridge, ConfiguracaoCombo(pausar_antes_ultimos_skips=True),
        )
        automation.executar_passo()
        bridge.calls.clear()

        automation.parar()
        automation.retomar()
        report = automation.executar_passo()

        self.assertEqual(report.estado, EstadoCombo.INTERROMPIDO)
        self.assertEqual(bridge.calls, [])

    def test_pause_option_does_not_stop_earlier_alignment(self):
        bridge = FakeComboBridge()
        bridge.forecast.update(startCast=14, skipCount=4)
        report = ComboAutomation(
            bridge, ConfiguracaoCombo(pausar_antes_ultimos_skips=True),
        ).executar_passo()
        self.assertEqual(report.estado, EstadoCombo.ALINHANDO)
        self.assertIn(("skip", 10, 4), bridge.calls)

    def test_empty_garden_is_planted_in_one_fast_cycle(self):
        bridge = FakeComboBridge([combo_snapshot(spellsCastTotal=9)])
        bridge.forecast.update(currentCast=9, startCast=10, skipCount=1)
        bridge.garden = empty_garden()

        report = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()

        self.assertEqual(report.estado, EstadoCombo.PREPARANDO)
        self.assertIn("2 semente(s)", report.mensagem)
        self.assertEqual(
            [call for call in bridge.calls if call[0] == "plant"],
            [("plant", "goldenClover", 0, 0), ("plant", "nursetulip", 1, 0)],
        )

    def test_garden_maturity_never_gates_ready_quadcast(self):
        for clovers, tulips in ((0, 0), (10, 9), (11, 10), (23, 12)):
            with self.subTest(mature=clovers + tulips):
                bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs())])
                bridge.garden = full_garden(clovers, tulips)

                report = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()

                self.assertEqual(report.estado, EstadoCombo.CLICANDO)
                self.assertIn("quadcast", [call[0] for call in bridge.calls])
                self.assertNotIn("garden", [call[0] for call in bridge.calls])

    def test_garden_half_mature_does_not_delay_ready_quadcast(self):
        bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs())])
        bridge.garden = full_garden(10, 8)

        report = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()

        self.assertEqual(report.estado, EstadoCombo.CLICANDO)
        self.assertIn("quadcast", [call[0] for call in bridge.calls])

    def test_ready_quadcast_does_not_require_both_garden_species_mature(self):
        bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs())])
        bridge.garden = full_garden(20, 0)

        report = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()

        self.assertEqual(report.estado, EstadoCombo.CLICANDO)
        self.assertIn("quadcast", [call[0] for call in bridge.calls])

    def test_ready_combo_does_not_read_garden_or_replant_empty_tiles(self):
        bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs())])
        bridge.garden = full_garden(11, 10, empty_tiles=((0, 5), (2, 5), (5, 5)))

        report = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()

        self.assertEqual(report.estado, EstadoCombo.CLICANDO)
        self.assertNotIn("garden", [call[0] for call in bridge.calls])
        self.assertNotIn("plant", [call[0] for call in bridge.calls])

    def test_mature_majority_still_requires_natural_combo_buffs(self):
        bridge = FakeComboBridge()
        bridge.garden = full_garden(11, 10)

        report = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()

        self.assertEqual(report.estado, EstadoCombo.AGUARDANDO_BUFFS)
        self.assertEqual(report.garden_maduras, 21)
        self.assertNotIn("quadcast", [call[0] for call in bridge.calls])

    def test_empty_unavailable_or_locked_garden_never_blocks_ready_combo(self):
        for garden in (
            empty_garden(),
            GardenSnapshot(status=GardenStatus(False, False, "Garden indisponível")),
            replace(mature_garden(), seeds=()),
        ):
            with self.subTest(garden=garden):
                bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs())])
                bridge.garden = garden

                report = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()

                self.assertEqual(report.estado, EstadoCombo.CLICANDO)
                self.assertNotIn("garden", [call[0] for call in bridge.calls])
                self.assertNotIn("plant", [call[0] for call in bridge.calls])

    def test_optional_garden_failures_do_not_stop_alignment_or_buff_search(self):
        for remaining in (0, 1):
            for failure in ("unavailable", "read_exception", "plant_failure", "plant_exception"):
                with self.subTest(remaining=remaining, failure=failure):
                    bridge = FakeComboBridge()
                    bridge.forecast.update(startCast=10 + remaining, skipCount=remaining)
                    if failure == "unavailable":
                        bridge.garden = GardenSnapshot(status=GardenStatus(False, False, "Sem Garden"))
                    elif failure == "read_exception":
                        bridge.get_garden_snapshot = Mock(side_effect=RuntimeError("Falha na leitura"))
                    else:
                        bridge.garden = empty_garden()
                        bridge.plant_garden_seed = (
                            Mock(side_effect=RuntimeError("Falha no plantio"))
                            if failure == "plant_exception" else
                            Mock(return_value=GardenActionResult(False, "plant", "Caixa insuficiente"))
                        )

                    report = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()

                    self.assertFalse(report.terminal)
                    self.assertEqual(
                        report.estado,
                        EstadoCombo.ALINHANDO if remaining else EstadoCombo.AGUARDANDO_BUFFS,
                    )
                    self.assertNotIn("quadcast", [call[0] for call in bridge.calls])

    def test_stop_during_optional_planting_prevents_alignment_cast(self):
        bridge = FakeComboBridge()
        bridge.garden = empty_garden()
        bridge.forecast.update(startCast=11, skipCount=1)
        automation = ComboAutomation(bridge, ConfiguracaoCombo())

        def plant_and_stop(seed_key, x, y):
            automation.parar()
            return GardenActionResult(True, "plant", "Plantada", x=x, y=y)

        bridge.plant_garden_seed = plant_and_stop
        report = automation.executar_passo()

        self.assertEqual(report.estado, EstadoCombo.INTERROMPIDO)
        self.assertNotIn("skip", [call[0] for call in bridge.calls])
        self.assertNotIn("refill", [call[0] for call in bridge.calls])

    def test_cursors_are_rebuilt_after_office_sacrifices_before_other_preparation(self):
        bridge = FakeComboBridge([combo_snapshot(
            buildings=[{"id": 0, "name": "Cursor", "amount": 0, "level": 15}],
        )])

        report = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()

        self.assertEqual(report.estado, EstadoCombo.PREPARANDO)
        self.assertIn(("minimum", 0, 601), bridge.calls)
        self.assertNotIn("garden", [call[0] for call in bridge.calls])

    def test_ready_stack_executes_quadcast_and_starts_clicker(self):
        bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs())])
        clicker_calls = []
        automation = ComboAutomation(
            bridge,
            ConfiguracaoCombo(),
            habilitar_clicker=lambda: clicker_calls.append("start") or True,
            relogio=lambda: 100.0,
        )

        report = automation.executar_passo()

        self.assertEqual(report.estado, EstadoCombo.CLICANDO)
        self.assertEqual(clicker_calls, ["start"])
        quadcast = next(call[1] for call in bridge.calls if call[0] == "quadcast")
        self.assertEqual(quadcast["expected_results"], RESULTS)
        self.assertEqual(quadcast["required_natural_bs"], 2)
        self.assertEqual(report.lumps_gastos, 2)

    def test_wizard_tower_building_special_is_not_counted_as_natural(self):
        bridge = FakeComboBridge()
        automation = ComboAutomation(bridge, ConfiguracaoCombo())
        plan = PlanoCombo(
            "seed", "2.053", 10, 10, "valentines", tuple(RESULTS), 0, 1, 2, 0
        )
        snapshot = combo_snapshot(buffs=ready_buffs()[:2] + [
            {"name": "WT special", "type": "building buff", "timeSeconds": 30, "buildingId": 7},
            {"name": "Cursor special", "type": "building buff", "timeSeconds": 30, "buildingId": 0},
        ])

        ready, reason = automation._buffs_prontos(snapshot, plan)

        self.assertFalse(ready)
        self.assertIn("1 Building Special", reason)

    def test_aligned_window_waits_for_full_mana_and_lump_cooldown(self):
        bridge = FakeComboBridge([combo_snapshot(magic=99, magicM=100)])
        automation = ComboAutomation(bridge, ConfiguracaoCombo())

        mana_report = automation.executar_passo()

        self.assertEqual(mana_report.estado, EstadoCombo.ALINHANDO)
        self.assertIn("mana", mana_report.mensagem)
        self.assertNotIn("quadcast", [call[0] for call in bridge.calls])

        bridge = FakeComboBridge([combo_snapshot(canRefillLump=False, lumpRefillRemaining=500)])
        cooldown_report = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()

        self.assertEqual(cooldown_report.estado, EstadoCombo.ALINHANDO)
        self.assertIn("cooldown", cooldown_report.mensagem)
        self.assertNotIn("quadcast", [call[0] for call in bridge.calls])

    def test_partial_quadcast_failure_restores_original_towers_once(self):
        bridge = FakeComboBridge([
            combo_snapshot(buffs=ready_buffs(), wizardTowers=601),
            combo_snapshot(wizardTowers=1),
        ])
        bridge.quadcast_result = {"ok": False, "message": "cast 4 falhou", "lumpsSpent": 1}
        automation = ComboAutomation(bridge, ConfiguracaoCombo())
        automation._wizard_towers_originais = 726

        report = automation.executar_passo()

        self.assertEqual(report.estado, EstadoCombo.ERRO_SEGURO)
        self.assertEqual(report.lumps_gastos, 1)
        self.assertIn(("towers", 726), bridge.calls)

    def test_waiting_action_is_retried_instead_of_becoming_terminal(self):
        bridge = FakeComboBridge()
        automation = ComboAutomation(bridge, ConfiguracaoCombo())
        plan = PlanoCombo(
            "seed", "2.053", 10, 10, "valentines", tuple(RESULTS), 0, 1, 2, 0
        )

        report = automation._action_report(
            {"ok": False, "waiting": True, "message": "cooldown"},
            "feito",
            combo_snapshot(),
            plan,
            EstadoCombo.ALINHANDO,
        )

        self.assertEqual(report.estado, EstadoCombo.ALINHANDO)
        self.assertFalse(report.terminal)


class ComboBridgeTests(unittest.TestCase):
    class StubBridge(CookieClickerBridge):
        def __init__(self, responses):
            self.responses = list(responses)
            self.scripts = []

        def execute_js(self, code):
            self.scripts.append(code)
            return self.responses.pop(0)

    def test_game_save_uses_write_save_without_opening_export_prompt(self):
        bridge = self.StubBridge(["SAVE-CODE"])

        result = bridge.get_game_save()

        self.assertEqual(result, "SAVE-CODE")
        self.assertIn("Game.WriteSave(1)", bridge.scripts[0])
        self.assertNotIn("Game.ExportSave", bridge.scripts[0])

    def test_invalid_quadcast_arguments_never_reach_javascript(self):
        bridge = self.StubBridge([])

        result = bridge.execute_combo_quadcast(
            expected_cast=10,
            expected_results=["click frenzy"],
            minimum_buff_seconds=15,
            required_natural_bs=2,
            use_sugar_frenzy=True,
            use_loans=True,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(bridge.scripts, [])

    def test_quadcast_script_prices_rebuy_from_one_and_tracks_partial_lump(self):
        bridge = self.StubBridge([{"ok": True}])

        bridge.execute_combo_quadcast(
            expected_cast=10,
            expected_results=RESULTS,
            minimum_buff_seconds=15,
            required_natural_bs=2,
            use_sugar_frenzy=True,
            use_loans=True,
        )

        script = bridge.scripts[0]
        self.assertIn("for (let i=1;i<601;i++)", script)
        self.assertNotIn("tower.getSumPrice(600)", script)
        self.assertIn("Object.assign({},third,{lumpsSpent:1})", script)
        self.assertGreaterEqual(script.count("M.computeMagicM()"), 3)

    def test_invalid_building_minimum_never_reaches_javascript(self):
        bridge = self.StubBridge([])

        result = bridge.ensure_combo_building_minimum(-1, 601)

        self.assertFalse(result["ok"])
        self.assertEqual(bridge.scripts, [])

    def test_cookie_storm_drain_is_restricted_to_exact_storm_drop_force(self):
        bridge = self.StubBridge([{"ok": True, "count": 3}])

        result = bridge.pop_combo_cookie_storm_drops()

        self.assertTrue(result["ok"])
        self.assertIn("String(item.force||'')==='cookie storm drop'", bridge.scripts[0])

    def test_generic_golden_click_confirms_the_selected_id_not_an_empty_screen(self):
        bridge = self.StubBridge([{"id": 10}, True])

        result = bridge.pop_golden_cookie()

        self.assertTrue(result)
        self.assertIn("Number(s.id) === id", bridge.scripts[1])


class RunnerExclusiveModeTests(unittest.TestCase):
    def test_exclusive_owner_blocks_manual_toggle_until_release(self):
        with patch("app.core.run.InputHandler", return_value=Mock()):
            runner = AutomationRunner(1, Mock())
        runner._exclusive_lock = threading.RLock()
        runner.update_cookie_position = Mock(return_value=True)

        self.assertTrue(runner.acquire_exclusive("combo"))
        runner.toggle_clicker()
        self.assertFalse(runner.is_running)
        self.assertEqual(runner.exclusive_owner, "combo")
        self.assertTrue(runner.release_exclusive("combo"))

        runner.toggle_clicker()
        self.assertTrue(runner.is_running)


class ComboUiTests(unittest.TestCase):
    def test_old_preset_migrates_once_and_later_preferences_are_preserved(self):
        from app.config import settings as settings_module
        for revision, expected in ((0, 2), (2, 3)):
            values = {"combo_strategy_revision": revision,
                      "combo_required_building_specials": 3,
                      "combo_poll_interval_seconds": 1.0,
                      "combo_minimum_buff_seconds": 15.0}
            settings = Mock()
            settings.value.side_effect = lambda key, default=None, **kwargs: values.get(key, default)
            settings.setValue.side_effect = lambda key, value: values.update({key: value})
            config = AutomationConfig()
            with patch.object(settings_module, "QSettings", return_value=settings), patch.object(
                settings_module, "automation_config", config,
            ):
                settings_module.load_automation_settings()
            self.assertEqual(config.combo_required_building_specials, expected)
            self.assertEqual(config.combo_max_wait_minutes, 180)
            if revision == 0:
                self.assertEqual(config.combo_minimum_buff_seconds, 12)
                self.assertEqual(config.combo_poll_interval_seconds, .2)
                self.assertEqual(values['combo_strategy_revision'], 2)

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_tab_exposes_preview_real_opt_in_and_emergency_stop(self):
        window = MainWindow()
        tab_names = [window.tabs.tabText(index) for index in range(window.tabs.count())]

        self.assertIn("Combo", tab_names)
        self.assertEqual(window.combo_preview_button.text(), "Atualizar prévia")
        self.assertEqual(window.combo_stop_button.text(), "Parar imediatamente")
        self.assertFalse(window.combo_stop_button.isEnabled())
        self.assertTrue(window.combo_scroll_area.widgetResizable())
        self.assertTrue(all(field.minimumHeight() >= 32 for field in (
            window.combo_search_input,
            window.combo_lumps_input,
            window.combo_bs_input,
            window.combo_interval_input,
            window.combo_min_buff_input,
        )))
        window.close()

    def test_automation_configuration_defaults_to_disabled(self):
        config = AutomationConfig()
        self.assertFalse(config.enable_combo_automation)
        self.assertEqual(config.combo_target_cookies, 1e72)
        self.assertEqual(config.combo_required_building_specials, 2)
        self.assertFalse(config.combo_pause_before_last_skips)
        self.assertFalse(ConfiguracaoCombo().pausar_antes_ultimos_skips)

    def test_resume_control_releases_paused_worker_and_disables_on_finish(self):
        window = MainWindow()
        worker = Mock()
        worker.isRunning.return_value = True
        automation = Mock()
        window._combo_worker = worker
        window._combo_automation = automation
        try:
            self.assertFalse(window.combo_resume_button.isEnabled())
            window._set_combo_busy(True, preview=False)
            self.assertFalse(window.combo_pause_checkbox.isEnabled())
            window._display_combo_report(RelatorioCombo(
                EstadoCombo.PAUSADO, "Aguardando Retomar",
            ))
            self.assertTrue(window.combo_resume_button.isEnabled())

            window.combo_resume_button.click()

            automation.retomar.assert_called_once_with()
            self.assertFalse(window.combo_resume_button.isEnabled())
            window._set_combo_busy(False, preview=False)
            self.assertTrue(window.combo_pause_checkbox.isEnabled())
            self.assertFalse(window.combo_resume_button.isEnabled())
        finally:
            window._combo_worker = None
            window._combo_automation = None
            window.close()


if __name__ == "__main__":
    unittest.main()
