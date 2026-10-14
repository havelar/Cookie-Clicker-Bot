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
