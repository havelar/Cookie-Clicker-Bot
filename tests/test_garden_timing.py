"""Sincronização de pais e janelas de mutação, sem alterar o jogo."""
import unittest
from dataclasses import replace
from app.bridge.js_bridge import CookieClickerBridge
from app.core.fazendeira import Fazendeira
from app.core.garden_catalog import GARDEN_CATALOG, TARGET_SEED_KEYS, GardenRecipe, ParentRequirement
from app.core.garden_timing import ParentWindow, _windows, schedule_parent_plantings
from app.models.garden import GardenAction, GardenPlant, GardenGoal
from tests.test_garden import snapshot, FakeGardenBridge


class TimingTests(unittest.TestCase):
    def test_fast_parent_uses_mature_immortal_without_waiting_for_young_anchors(self):
        current = snapshot({'elderwort','crumbspore'},tiles=tuple((x,y) for y in range(4) for x in range(4)))
        current = replace(current,seeds=tuple(replace(s,mature_age=50,
                          average_growth=1 if s.key=='elderwort' else 10,
                          immortal=s.key=='elderwort') for s in current.seeds),
                          plants=(GardenPlant(0,0,7,'elderwort','Elderwort',0,50,False,
                                              immortal=True,average_growth=1),
                                  GardenPlant(1,2,7,'elderwort','Elderwort',80,50,True,
                                              immortal=True,average_growth=1)))
        desired = {(0,0):'elderwort',(1,2):'elderwort',(1,1):'crumbspore'}
        farm = Fazendeira(FakeGardenBridge(current))
        actions,message = schedule_parent_plantings(current,GARDEN_CATALOG['ichorpuff'],desired,
                         ((0,1),(1,0),(2,1),(2,2)),farm._reconcile_layout(current,desired))
        self.assertEqual([(a.kind,a.seed_key,a.x,a.y) for a in actions],[('plant','crumbspore',1,1)])
        self.assertEqual(message,'')
        current = replace(current,plants=current.plants[:1])
        desired.pop((1,2))
        actions,message = schedule_parent_plantings(current,GARDEN_CATALOG['ichorpuff'],desired,
                         ((0,1),(1,0)),farm._reconcile_layout(current,desired))
        self.assertFalse(any(a.kind=='plant' for a in actions))
        self.assertIn('aguardar',message)

    def setup_pair(self, *, slow_age=None, fast_age=None, slow_rate=1, fast_rate=10):
        self.recipe = GardenRecipe('foolBolete', "Fool's bolete",
                                   (ParentRequirement('doughshroom'), ParentRequirement('greenRot')))
        self.desired = {(1, 1): 'doughshroom', (2, 1): 'greenRot'}
        self.center = (1, 2)
        current = snapshot({'doughshroom', 'greenRot'}, soil='fertilizer')
        current = replace(current, seeds=tuple(replace(s, mature_age=60 if s.key=='doughshroom' else 50,
                           average_growth=slow_rate if s.key=='doughshroom' else fast_rate) for s in current.seeds),
                           tick_seconds=180)
        plants = []
        for (x, y), key in self.desired.items():
            age = slow_age if key=='doughshroom' else fast_age
            if age is not None:
                seed = next(s for s in current.seeds if s.key==key)
                plants.append(GardenPlant(x, y, seed.seed_id, key, seed.name, age, seed.mature_age,
                              age>=seed.mature_age, average_growth=seed.average_growth))
        return replace(current, plants=tuple(plants))

    def plan(self, current):
        farm = Fazendeira(FakeGardenBridge(current))
        actions = farm._reconcile_layout(current, self.desired)
        return schedule_parent_plantings(current, self.recipe, self.desired, (self.center,), actions)

    def test_empty_plot_plants_slow_parent_and_waits_for_fast(self):
        actions, message = self.plan(self.setup_pair())
        self.assertEqual([a.seed_key for a in actions], ['doughshroom'])
        self.assertIn('Green rot', message)
        self.assertIn('165 min', message)

    def test_wait_is_recomputed_from_actual_age_then_released(self):
        actions, message = self.plan(self.setup_pair(slow_age=40))
        self.assertEqual(actions, ())
        self.assertIn('45 min', message)
        actions, message = self.plan(self.setup_pair(slow_age=55))
        self.assertEqual([a.seed_key for a in actions], ['greenRot'])
        self.assertEqual(message, '')

    def test_actual_tile_growth_modifier_changes_wait(self):
        current = self.setup_pair(slow_age=40)
        current = replace(current, growth_multipliers=((2, 1, 0.5),))
        _, message = self.plan(current)
        self.assertIn('30 min', message)

    def test_existing_plants_are_never_removed_to_force_alignment(self):
        current = self.setup_pair(slow_age=10, fast_age=65)
        actions, _ = self.plan(current)
        self.assertFalse(any(a.kind=='harvest' for a in actions))

    def test_same_species_is_planted_as_one_cohort(self):
        current = self.setup_pair()
        self.recipe = GARDEN_CATALOG['thumbcorn']
        self.desired = {(1, 1): 'bakerWheat', (2, 1): 'bakerWheat'}
        actions, message = self.plan(current)
        self.assertEqual(len(actions), 2)
        self.assertEqual(message, '')

    def test_recipe_not_requiring_maturity_does_not_wait(self):
        current = self.setup_pair()
        self.recipe = GARDEN_CATALOG['shriekbulb']
        self.desired = {(1, 1): 'duketater', (2, 1): 'duketater', (2, 2): 'duketater'}
        actions, message = self.plan(current)
        self.assertEqual(len(actions), 3)
        self.assertEqual(message, '')

    def test_immortal_anchors_and_three_fast_parents_are_scheduled_together(self):
        current = self.setup_pair()
        self.recipe = GARDEN_CATALOG['everdaisy']
        ring = [(0, 0), (1, 0), (2, 0), (0, 1), (2, 1), (0, 2)]
        self.center = (1, 1)
        self.desired = {p: 'elderwort' if i<3 else 'tidygrass' for i, p in enumerate(ring)}
        current = replace(current, seeds=tuple(replace(s, mature_age=50, average_growth=1 if s.key=='elderwort' else 10,
                          immortal=s.key=='elderwort') for s in current.seeds))
        actions, message = self.plan(current)
        self.assertEqual([a.seed_key for a in actions], ['elderwort']*3)
        self.assertIn('135 min', message)

    def test_unavailable_growth_data_falls_back_without_inventing_wait(self):
        current = self.setup_pair()
        current = replace(current, seeds=tuple(replace(s, average_growth=None) for s in current.seeds))
        actions, message = self.plan(current)
        self.assertEqual(len(actions), 2)
        self.assertEqual(message, '')

    def test_juicy_actions_are_identical(self):
        current = self.setup_pair()
        recipe = GARDEN_CATALOG['queenbeetLump']
        actions = (GardenAction('boost_mutation', 'Usar lump'), GardenAction('plant', 'Plantar', x=1, y=1, seed_key='queenbeet'))
        result, message = schedule_parent_plantings(current, recipe, {}, (), actions)
        self.assertEqual(result, actions)
        self.assertEqual(message, '')

    def test_unknown_plant_is_preserved_and_blocks_its_position(self):
        current = self.setup_pair(slow_age=50)
        unknown = GardenPlant(2, 1, 999, 'alien', 'Desconhecida', 20, 50, False)
        current = replace(current, plants=current.plants+(unknown,))
        actions, _ = self.plan(current)
        self.assertFalse(any(a.kind=='harvest' for a in actions))
        self.assertFalse(any(a.kind=='plant' for a in actions))

    def test_expected_shared_window_is_longer_than_simultaneous_planting(self):
        self.setup_pair()
        naive = {(1, 1): ParentWindow('doughshroom', 60, 100), (2, 1): ParentWindow('greenRot', 5, 10)}
        delayed = dict(naive)
        delayed[(2, 1)] = ParentWindow('greenRot', 60, 65, 55)
        self.assertEqual(_windows(self.recipe, self.center, naive, 110), [])
        self.assertEqual(_windows(self.recipe, self.center, delayed, 110), [(60, 65)])

    def test_maximum_neighbor_limit_uses_planting_and_death_times(self):
        recipe = GardenRecipe('test', 'Test', (ParentRequirement('a'),), maximum_neighbors=(('b', 0),))
        forecasts = {(1, 1): ParentWindow('a', 1, 10), (2, 1): ParentWindow('b', 6, 9, 5)}
        self.assertEqual(_windows(recipe, (1, 2), forecasts, 10), [(1, 5), (9, 10)])

    def test_all_catalog_recipes_can_use_runtime_timing(self):
        current = self.setup_pair()
        farm = Fazendeira(FakeGardenBridge(current))
        for recipe in GARDEN_CATALOG.values():
            with self.subTest(recipe=recipe.key):
                if not recipe.parents:
                    continue
                center, desired = farm._find_layout(current, recipe)
                if center is None:
                    continue
                actions = farm._reconcile_layout(current, desired)
                result, _ = schedule_parent_plantings(current, recipe, desired, (center,), actions)
                self.assertTrue(all(a.seed_key in GARDEN_CATALOG for a in result if a.kind=='plant'))

    def test_plan_explains_wait_instead_of_claiming_layout_is_complete(self):
        current = self.setup_pair(slow_age=40)
        farm = Fazendeira(FakeGardenBridge(current))
        actions, explanation = farm._plan_mutation_layout(current, self.recipe, self.desired, (self.center,), 'layout de teste')
        self.assertFalse(any(a.kind=='plant' for a in actions))
        self.assertIn('aguardar para plantar Green rot', explanation)

    def test_live_recipe_doughshroom_green_rot_waits_for_current_slow_parents(self):
        current = self.setup_pair(slow_age=55, slow_rate=2.1, fast_rate=19.425)
        current = replace(current, seeds=tuple(replace(s, mature_age=80.75 if s.key=='doughshroom' else 61.75)
                                               for s in current.seeds),
                          plants=tuple(replace(p, mature_age=80.75) for p in current.plants))
        actions, message = self.plan(current)
        self.assertEqual(actions, ())
        self.assertIn('27 min', message)
        current = replace(current, plants=tuple(replace(p, age=74) for p in current.plants))
        actions, _ = self.plan(current)
        self.assertEqual([a.seed_key for a in actions], ['greenRot'])

    def test_ready_pairs_keep_woodchips_while_other_pairs_are_replanted(self):
        tiles = tuple((x,y) for y in range(6) for x in range(6))
        current = self.setup_pair(slow_rate=10, fast_rate=10)
        current = replace(current, unlocked_tiles=tiles, soil_key='woodchips', plants=(
            GardenPlant(0,1,0,'doughshroom','Doughshroom',70,60,True,average_growth=10),
            GardenPlant(1,1,1,'greenRot','Green rot',70,50,True,average_growth=10)))
        farm = Fazendeira(FakeGardenBridge(current))
        goal = GardenGoal('foolBolete', "Fool's bolete", ('doughshroom','greenRot'), ('Doughshroom','Green rot'), '', (), '', 'mutacao_adjacente')
        farm.select_next_goal = lambda _: goal
        actions = (GardenAction('plant','Repor pai',x=4,y=4,seed_key='greenRot'),)
        result = farm._prepend_operational_actions(current, actions)
        self.assertFalse(any(a.kind=='change_soil' for a in result))

    def test_group_timing_does_not_add_sugar_lump_actions(self):
        current = self.setup_pair()
        actions, _ = self.plan(current)
        self.assertFalse(any(a.kind=='boost_mutation' for a in actions))

    def test_bridge_reads_seed_rates_and_ignores_invalid_tile_boosts(self):
        payload = {'status': {'available': True, 'unlocked': True},
                   'seeds': [{'id': 0, 'key': 'bakerWheat', 'matureAge': 35,
                              'averageGrowth': 8, 'maximumGrowth': 9}],
                   'growthMultipliers': [[1, 1, 1.5], [99, 1, 1], [2, 2, -1], [1], ['x', 1, 1]],
                   'plants': [], 'unlockedTiles': [[1, 1]]}
        parsed = CookieClickerBridge()._parse_garden_snapshot(payload)
        self.assertEqual(parsed.seeds[0].average_growth, 8)
        self.assertEqual(parsed.seeds[0].maximum_growth, 9)
        self.assertEqual(parsed.growth_multipliers, ((1, 1, 1.5),))

    def test_zero_growth_cannot_create_infinite_wait(self):
        current = self.setup_pair(slow_rate=0)
        actions, message = self.plan(current)
        self.assertEqual(len(actions), 2)
        self.assertEqual(message, '')

    def test_wait_is_visible_while_a_discovery_grows_and_next_recipe_is_prepared(self):
        current = self.setup_pair(slow_rate=1, fast_rate=10)
        current = replace(current, unlocked_tiles=tuple((x,y) for y in range(6) for x in range(6)),
                          seeds=tuple(replace(s, unlocked=s.key in set(TARGET_SEED_KEYS)-{'thumbcorn','foolBolete'})
                                      for s in current.seeds),
                          plants=(GardenPlant(3,3,1,'thumbcorn','Thumbcorn',1,50,False,average_growth=10),))
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        self.assertEqual(plan.goal.target_key, 'thumbcorn')
        self.assertIn('Green rot', plan.explanation)
        self.assertIn('aguardar para plantar', plan.explanation)
        self.assertFalse(any(a.kind=='harvest' and (a.x,a.y)==(3,3) for a in plan.actions))
