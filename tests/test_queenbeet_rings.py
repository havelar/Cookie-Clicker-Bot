"""Círculos completos e preservação de espécies desconhecidas no Garden."""
from dataclasses import replace
import unittest
from app.core.fazendeira import Fazendeira
from app.core.garden_catalog import TARGET_SEED_KEYS, GARDEN_CATALOG
from app.models.garden import GardenPlant
from tests.test_garden import snapshot, FakeGardenBridge


class QueenbeetRingTests(unittest.TestCase):
    tiles = tuple((x, y) for y in range(6) for x in range(6))
    centers = ((1, 1), (4, 1), (1, 4), (4, 4))
    unlocked = set(TARGET_SEED_KEYS) - {"queenbeetLump"}

    def plant(self, pos, key="queenbeet", mature=True):
        return GardenPlant(*pos, 1, key, key, 70 if mature else 10, 50, mature)

    def current(self, plants):
        return snapshot(self.unlocked, plants, tiles=self.tiles, soil="woodchips")

    def ring(self, center):
        return set(Fazendeira._neighbors(center))

    def plan(self, plants):
        current = self.current(plants)
        return Fazendeira(FakeGardenBridge(current)).build_plan(current)

    def test_dead_parent_replants_whole_quadrant_and_preserves_other_three(self):
        missing = (0, 0)
        plants = [self.plant(pos) for center in self.centers for pos in self.ring(center) if pos != missing]
        plan = self.plan(plants)
        harvests = {(a.x, a.y) for a in plan.actions if a.kind == "harvest"}
        plantings = {(a.x, a.y) for a in plan.actions if a.kind == "plant"}
        self.assertEqual(harvests, self.ring((1, 1)) - {missing})
        self.assertEqual(plantings, self.ring((1, 1)))
        self.assertFalse(any(a.kind == "change_soil" and a.soil_key == "fertilizer" for a in plan.actions))

    def test_complete_mixed_maturity_ring_waits_without_removing_parents(self):
        plants = [self.plant(pos, mature=pos != (0, 0)) for pos in self.ring((1, 1))]
        plan = self.plan(plants)
        self.assertFalse(any(a.kind == "harvest" for a in plan.actions))
        self.assertFalse(any(a.kind == "plant" and (a.x, a.y) in self.ring((1, 1)) for a in plan.actions))
        self.assertFalse(Fazendeira(None)._mutation_tile_is_ready(self.current(plants), (1, 1), GARDEN_CATALOG["queenbeetLump"]))

    def test_protected_species_blocks_whole_ring_without_partial_replant(self):
        plants = [self.plant(pos) for pos in self.ring((1, 1)) if pos != (0, 0)]
        plants.append(self.plant((0, 0), key="unknownPlant", mature=False))
        plan = self.plan(plants)
        self.assertFalse(any(a.kind in {"plant", "harvest"} and (a.x, a.y) in self.ring((1, 1)) for a in plan.actions))
        self.assertTrue(any(a.kind == "plant" and (a.x, a.y) in self.ring((4, 4)) for a in plan.actions))

    def test_locked_discovery_also_blocks_whole_ring_until_mature(self):
        current = self.current([self.plant(pos) for pos in self.ring((1, 1)) if pos != (0, 0)] +
                               [self.plant((0, 0), key="duketater", mature=False)])
        current = replace(current, seeds=tuple(replace(seed, unlocked=False) if seed.key == "duketater" else seed for seed in current.seeds))
        farmer = Fazendeira(FakeGardenBridge(current))
        desired = farmer.MAXIMUM_SPECIAL_LAYOUTS["queenbeetLump"]
        actions = farmer._reconcile_layout(current, desired)
        actions, _ = farmer._synchronize_queenbeet_rings(current, desired, self.centers, actions)
        self.assertFalse(any((a.x, a.y) in self.ring((1, 1)) for a in actions))

    def test_small_garden_renews_all_eight_in_one_ring(self):
        current = snapshot(self.unlocked)
        farmer = Fazendeira(FakeGardenBridge(current))
        center, desired = farmer._find_layout(current, GARDEN_CATALOG["queenbeetLump"])
        missing = next(iter(desired))
        current = replace(current, plants=tuple(self.plant(pos) for pos in desired if pos != missing))
        plan = farmer.build_plan(current)
        self.assertEqual(sum(a.kind == "harvest" for a in plan.actions), 7)
        self.assertEqual(sum(a.kind == "plant" for a in plan.actions), 8)

    def test_occupied_center_is_not_a_mutation_candidate(self):
        plants = [self.plant(pos) for pos in self.ring((1, 1))] + [self.plant((1, 1), key="unknownPlant")]
        self.assertFalse(Fazendeira(None)._mutation_tile_is_ready(self.current(plants), (1, 1), GARDEN_CATALOG["queenbeetLump"]))

    def test_unknown_species_survives_generic_and_thumbcorn_layouts(self):
        plant = self.plant((1, 1), key="unknownPlant")
        current = snapshot({"bakerWheat", "thumbcorn"}, [plant], green_aching_thumb_won=False, green_aching_thumb_progress=0)
        farmer = Fazendeira(FakeGardenBridge(current))
        for plan in (farmer.build_plan(current), farmer.build_plan(current, green_aching_thumb_enabled=True)):
            self.assertFalse(any(a.kind in {"plant", "harvest"} and (a.x, a.y) == (1, 1) for a in plan.actions))

    def test_combo_never_cleans_unknown_or_locked_discoveries(self):
        from tests.test_combo import FakeComboBridge, combo_snapshot, empty_garden
        from app.core.combo import ComboAutomation
        from app.models.combo import ConfiguracaoCombo
        for key in ("unknownPlant", "queenbeetLump"):
            bridge=FakeComboBridge([combo_snapshot(spellsCastTotal=9)])
            bridge.forecast.update(currentCast=9,startCast=10,skipCount=1)
            bridge.garden=replace(empty_garden(),plants=(self.plant((0,0),key=key,mature=False),))
            ComboAutomation(bridge,ConfiguracaoCombo()).executar_passo()
            self.assertFalse(any(call[0]=='harvest' for call in bridge.calls))
