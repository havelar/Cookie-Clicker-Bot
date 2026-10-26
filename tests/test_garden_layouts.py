"""Receitas ocupam o canteiro com pais e espaços de mutação, sem remover protegidas."""
import unittest
from dataclasses import replace
from collections import Counter
from app.core.fazendeira import Fazendeira
from app.core.garden_catalog import GARDEN_CATALOG,TARGET_SEED_KEYS
from app.core.garden_layouts import full_plot_layout
from app.models.garden import GardenPlant
from tests.test_garden import snapshot,FakeGardenBridge

FULL = tuple((x,y) for y in range(6) for x in range(6))


class FullGardenLayoutTests(unittest.TestCase):
    def ichorpuff_transition(self, *, mature=False):
        elders = {(5,1), *((x,2) for x in range(6)), (5,3), *((x,5) for x in range(5))}
        plants = [GardenPlant(x,y,7,'elderwort','Elderwort',90,85.5,True,immortal=True)
                  for x,y in elders]
        plants.extend((
            GardenPlant(1,1,32,'everdaisy','Everdaisy',80 if mature else 10,50,mature),
            GardenPlant(0,0,31,'tidygrass','Tidygrass',60,40,True),
            GardenPlant(3,3,23,'crumbspore','Crumbspore',55,50,True),
            GardenPlant(4,4,999,'unknown','Unknown',10,50,False),
        ))
        return snapshot(set(TARGET_SEED_KEYS)-{'everdaisy','ichorpuff'},plants,tiles=FULL),elders

    def test_ichorpuff_preserves_existing_parents_and_immature_everdaisy(self):
        current,elders = self.ichorpuff_transition()
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        self.assertEqual(plan.goal.target_key,'everdaisy')
        self.assertFalse(any((a.x,a.y) in elders | {(1,1),(3,3),(4,4)}
                             for a in plan.actions if a.kind in {'plant','harvest'}))
        self.assertTrue(any(a.kind=='plant' and a.seed_key=='crumbspore' for a in plan.actions))
        self.assertIn('aproveitando os pais existentes',plan.explanation)

    def test_mature_everdaisy_is_harvested_without_removing_existing_parents(self):
        current,elders = self.ichorpuff_transition(mature=True)
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        harvests = [a for a in plan.actions if a.kind=='harvest' and (a.x,a.y)==(1,1)]
        self.assertEqual(len(harvests),1)
        self.assertTrue(harvests[0].require_mature)
        self.assertFalse(any((a.x,a.y) in elders | {(3,3),(4,4)}
                             for a in plan.actions if a.kind in {'plant','harvest'}))

    def test_ichorpuff_parent_preservation_survives_replanning_and_fungus_death(self):
        current,elders = self.ichorpuff_transition()
        recipe = GARDEN_CATALOG['ichorpuff']
        desired,centers = full_plot_layout(current,recipe,preserve_parent_keys={'elderwort','crumbspore'})
        self.assertGreater(len(centers),1)
        self.assertTrue(elders <= set(desired))
        self.assertFalse({(1,1),(4,4)} & (set(desired)|set(centers)))
        for center in centers:
            neighbors = Counter(desired[p] for p in Fazendeira._neighbors(center) if p in desired)
            self.assertGreaterEqual(neighbors['elderwort'],1)
            self.assertGreaterEqual(neighbors['crumbspore'],1)
        protected = tuple(p for p in current.plants if p.key in {'everdaisy','unknown'})
        for cycle in range(3):
            # Uma Crumbspore expira; todos os pais restantes devem ficar onde estão.
            existing = tuple(GardenPlant(x,y,0,key,key,30,50,False)
                             for (x,y),key in desired.items() if not (key=='crumbspore' and x==cycle))
            current = replace(current,plants=existing+protected)
            plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
            positions = {(p.x,p.y) for p in current.plants}
            self.assertFalse(any((a.x,a.y) in positions for a in plan.actions if a.kind in {'plant','harvest'}))
            desired,centers = full_plot_layout(current,recipe,preserve_parent_keys={'elderwort','crumbspore'})

    def test_ichorpuff_preserves_parents_after_everdaisy_unlock(self):
        current,elders = self.ichorpuff_transition()
        current = replace(current,plants=tuple(p for p in current.plants if p.key!='everdaisy'),
                          seeds=tuple(replace(s,unlocked=True) if s.key=='everdaisy' else s for s in current.seeds))
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        self.assertEqual(plan.goal.target_key,'ichorpuff')
        self.assertFalse(any((a.x,a.y) in elders | {(3,3),(4,4)}
                             for a in plan.actions if a.kind in {'plant','harvest'}))

    def current(self, *, plants=(), tiles=FULL):
        return snapshot(set(TARGET_SEED_KEYS),plants,tiles=tiles)

    def verify_recipe(self, current, recipe, layout):
        desired,centers = layout
        self.assertTrue(centers)
        self.assertTrue(set(desired)<=set(current.unlocked_tiles))
        self.assertTrue(set(centers)<=set(current.unlocked_tiles))
        self.assertFalse(set(centers)&set(desired))
        occupied = {(p.x,p.y):p for p in current.plants if p.key not in current.unlocked_seed_keys or p.key not in GARDEN_CATALOG}
        self.assertFalse(set(desired)&set(occupied))
        self.assertFalse(set(centers)&set(occupied))
        for center in centers:
            neighbors = set(Fazendeira._neighbors(center))
            counts = Counter(desired[pos] for pos in neighbors if pos in desired)
            counts.update(occupied[pos].key for pos in neighbors if pos in occupied)
            self.assertTrue(all(counts[r.key]>=r.count for r in recipe.parents))
            self.assertTrue(all(counts[key]<=maximum for key,maximum in recipe.maximum_neighbors))

    def test_shriekbulb_uses_full_garden_instead_of_one_center(self):
        current=self.current()
        layout=full_plot_layout(current,GARDEN_CATALOG['shriekbulb'])
        self.verify_recipe(current,GARDEN_CATALOG['shriekbulb'],layout)
        self.assertGreaterEqual(len(layout[1]),16)
        self.assertEqual(set(layout[0])|set(layout[1]),set(FULL))

    def test_everdaisy_uses_all_cells_with_repeated_mixed_parent_groups(self):
        current=self.current()
        layout=full_plot_layout(current,GARDEN_CATALOG['everdaisy'])
        self.verify_recipe(current,GARDEN_CATALOG['everdaisy'],layout)
        self.assertGreaterEqual(len(layout[1]),8)
        self.assertEqual(set(layout[0])|set(layout[1]),set(FULL))

    def test_fungus_spread_uses_multiple_anchors(self):
        current=self.current()
        layout=full_plot_layout(current,GARDEN_CATALOG['whiteMildew'])
        self.verify_recipe(current,GARDEN_CATALOG['whiteMildew'],layout)
        self.assertEqual(len(layout[0]),4)
        self.assertEqual(len(layout[1]),32)

    def test_all_mutation_recipes_and_garden_sizes_have_valid_expanded_layouts(self):
        for width,height in ((2,2),(3,2),(3,3),(4,3),(4,4),(5,4),(5,5),(6,5),(6,6)):
            current=self.current(tiles=tuple((x,y) for y in range(height) for x in range(width)))
            for recipe in GARDEN_CATALOG.values():
                if not recipe.parents or recipe.key=='queenbeetLump' or recipe.strategy=='derivado_erva':continue
                with self.subTest(size=(width,height),recipe=recipe.key):
                    layout=full_plot_layout(current,recipe)
                    if layout:self.verify_recipe(current,recipe,layout)
                    else:self.assertLess(max(len(set(Fazendeira._neighbors(p))&set(current.unlocked_tiles)) for p in current.unlocked_tiles),sum(r.count for r in recipe.parents))

    def test_protected_discoveries_and_unknown_species_are_excluded_from_layout(self):
        plants=(GardenPlant(5,2,28,'wrinklegill','Wrinklegill',1,60,False),
                GardenPlant(1,4,999,'unknown','Unknown',50,70,False))
        current=self.current(plants=plants)
        current=replace(current,seeds=tuple(replace(s,unlocked=False) if s.key=='wrinklegill' else s for s in current.seeds))
        recipe=GARDEN_CATALOG['shriekbulb']
        layout=full_plot_layout(current,recipe)
        self.verify_recipe(current,recipe,layout)
        self.assertGreater(len(layout[1]),1)
        farmer=Fazendeira(FakeGardenBridge(current))
        actions,_=farmer._plan_parent_layout(current,recipe)
        self.assertFalse(any((a.x,a.y) in {(5,2),(1,4)} for a in actions if a.kind in {'plant','harvest'}))

    def test_small_or_offset_plots_do_not_depend_on_top_left_origin(self):
        current=self.current(tiles=tuple((x,y) for y in range(2,5) for x in range(1,5)))
        recipe=GARDEN_CATALOG['shriekbulb']
        layout=full_plot_layout(current,recipe)
        self.verify_recipe(current,recipe,layout)
        self.assertGreater(len(layout[1]),1)

    def test_meddleweed_derivatives_fill_every_unprotected_cell(self):
        protected=GardenPlant(5,2,28,'wrinklegill','Wrinklegill',1,60,False)
        current=self.current(plants=(protected,))
        current=replace(current,seeds=tuple(replace(s,unlocked=False) if s.key=='wrinklegill' else s for s in current.seeds))
        farmer=Fazendeira(FakeGardenBridge(current))
        for key in ('brownMold','crumbspore'):
            actions,_=farmer._estrategia_derivado_erva(current,GARDEN_CATALOG[key])
            plantings=[a for a in actions if a.kind=='plant']
            self.assertEqual(len(plantings),35)
            self.assertEqual({a.seed_key for a in plantings},{'meddleweed'})
            self.assertFalse(any((a.x,a.y)==(5,2) for a in actions))

    def test_all_mature_weeds_are_harvested_and_young_weeds_are_kept(self):
        weeds=(GardenPlant(0,0,0,'meddleweed','Meddleweed',60,50,True),
               GardenPlant(1,0,0,'meddleweed','Meddleweed',75,50,True),
               GardenPlant(2,0,0,'meddleweed','Meddleweed',20,50,False))
        current=self.current(plants=weeds)
        actions,_=Fazendeira(FakeGardenBridge(current))._estrategia_derivado_erva(current,GARDEN_CATALOG['crumbspore'])
        self.assertEqual({(a.x,a.y) for a in actions if a.kind=='harvest'},{(0,0),(1,0)})
        self.assertFalse(any(a.kind=='plant' and (a.x,a.y) in {(0,0),(1,0),(2,0)} for a in actions))

    def test_no_replanting_when_the_current_expanded_layout_is_already_present(self):
        current=self.current()
        recipe=GARDEN_CATALOG['shriekbulb']
        layout=full_plot_layout(current,recipe)
        plants=tuple(GardenPlant(x,y,0,key,key,10,90,False) for (x,y),key in layout[0].items())
        current=replace(current,plants=plants)
        layout2=full_plot_layout(current,recipe,layout[0])
        self.assertEqual(layout2[0],layout[0])
        actions=Fazendeira(FakeGardenBridge(current))._reconcile_layout(current,layout2[0])
        self.assertEqual(actions,())
        planned,_=Fazendeira(FakeGardenBridge(current))._plan_parent_layout(current,recipe)
        self.assertFalse(any(a.kind in {"plant","harvest"} for a in planned))
