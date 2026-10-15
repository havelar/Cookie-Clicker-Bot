"""Layout, manutenção, solos e integração do modo de Golden Cookies."""
import copy
import os
import unittest
from collections import Counter
from dataclasses import replace
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt5.QtWidgets import QApplication
from app.config.settings import automation_config, load_automation_settings, save_automation_settings
from app.core.fazendeira import Fazendeira
from app.core.garden_catalog import TARGET_SEED_KEYS
from app.core.garden_golden import golden_layout, frequency_bonus, GOLDEN, NURSE
from app.models.garden import GardenPlant, GardenSoil
from app.ui.garden_presentation import current_state
from app.ui.main_window import MainWindow
from tests.test_garden import snapshot, FakeGardenBridge

FULL = tuple((x,y) for y in range(6) for x in range(6))


class GoldenGardenTests(unittest.TestCase):
    def current(self, *, age=None, soil='fertilizer'):
        current = snapshot(set(TARGET_SEED_KEYS),tiles=FULL,soil=soil)
        current = replace(current,soils=current.soils+(GardenSoil(2,'clay','Clay',100,15,True),))
        if age is not None:
            current = replace(current,plants=tuple(GardenPlant(x,y,0,key,key,age,50,age>=50)
                              for (x,y),key in golden_layout(FULL)))
        return current

    def plan(self,current):
        return Fazendeira(FakeGardenBridge(current),clock=lambda:1000).build_plan(current,golden_cookies_enabled=True)

    def test_full_garden_has_18_of_each_and_matches_game_frequency_formula(self):
        layout = dict(golden_layout(FULL))
        self.assertEqual(Counter(layout.values()),{GOLDEN:18,NURSE:18})
        self.assertAlmostEqual(frequency_bonus({p:(key,1) for p,key in layout.items()}),1.9207763671875)
        self.assertAlmostEqual(frequency_bonus({p:(GOLDEN,1) for p in FULL}),1.35)
        self.assertEqual(set(layout),set(FULL))

    def test_tiny_garden_uses_clovers_when_tulips_would_reduce_frequency(self):
        layout = dict(golden_layout(((0,0),(1,0),(0,1),(1,1))))
        self.assertEqual(set(layout.values()),{GOLDEN})

    def test_offset_plot_and_protected_cells_are_supported(self):
        tiles = tuple((x,y) for y in range(2,5) for x in range(1,5))
        layout = dict(golden_layout(tiles,((2,3),)))
        self.assertEqual(set(layout),set(tiles)-{(2,3)})
        self.assertGreater(frequency_bonus({p:(key,1) for p,key in layout.items()}),0)

    def test_new_setup_uses_fertilizer_fills_plot_and_never_uses_lumps(self):
        plan = self.plan(self.current(soil='woodchips'))
        self.assertEqual(plan.mode,'golden_cookies')
        self.assertEqual(sum(a.kind=='plant' for a in plan.actions),36)
        self.assertEqual([a.soil_key for a in plan.actions if a.kind=='change_soil'],['fertilizer'])
        self.assertFalse(any(a.kind=='boost_mutation' for a in plan.actions))

    def test_mature_garden_moves_to_clay_without_harvesting_healthy_plants(self):
        plan = self.plan(self.current(age=70))
        self.assertEqual([(a.kind,a.soil_key) for a in plan.actions],[('change_soil','clay')])

    def test_one_missing_clover_is_replanted_without_leaving_clay(self):
        current = self.current(age=70,soil='clay')
        removed = next(p for p in current.plants if p.key==GOLDEN)
        current = replace(current,plants=tuple(p for p in current.plants if p!=removed))
        plan = self.plan(current)
        self.assertEqual([(a.kind,a.seed_key,a.x,a.y) for a in plan.actions],
                         [('plant',GOLDEN,removed.x,removed.y)])

    def test_young_garden_recovers_in_fertilizer_and_honors_soil_cooldown(self):
        current = self.current(age=0,soil='clay')
        self.assertEqual([a.soil_key for a in self.plan(current).actions],['fertilizer'])
        current = replace(current,next_soil_at=1500)
        plan = self.plan(current)
        self.assertFalse(plan.actions)
        self.assertIn('recarga',plan.explanation)

    def test_partial_maturation_is_enough_for_clay(self):
        current = self.current(age=70)
        current = replace(current,plants=tuple(replace(p,age=0,mature=False) if i%8==0 else p
                                               for i,p in enumerate(current.plants)))
        self.assertEqual([a.soil_key for a in self.plan(current).actions],['clay'])

    def test_unknown_and_locked_discoveries_are_never_removed_or_overplanted(self):
        current = self.current()
        current = replace(current,plants=(GardenPlant(1,1,999,'unknown','Unknown',0,50,False),
                                         GardenPlant(4,4,32,'everdaisy','Everdaisy',1,70,False)),
                          seeds=tuple(replace(s,unlocked=False) if s.key=='everdaisy' else s for s in current.seeds))
        plan = self.plan(current)
        self.assertFalse(any((a.x,a.y) in {(1,1),(4,4)} for a in plan.actions))
        self.assertEqual(sum(a.kind=='plant' for a in plan.actions),34)

    def test_missing_required_seed_pauses_without_cleaning_garden(self):
        current = self.current(age=70)
        current = replace(current,seeds=tuple(replace(s,unlocked=False) if s.key==NURSE else s for s in current.seeds))
        self.assertFalse(self.plan(current).actions)
        self.assertEqual(self.plan(current).goal.pending_prerequisites,('Nursetulip',))

    def test_completed_collection_is_untouched_when_mode_is_off(self):
        current = self.current(age=70)
        plan = Fazendeira(FakeGardenBridge(current)).build_plan(current)
        self.assertIsNone(plan.goal)
        self.assertFalse(plan.actions)

    def test_frozen_garden_resumes_without_illegal_simultaneous_soil_change(self):
        plan = self.plan(replace(self.current(age=70),frozen=True))
        self.assertEqual([(a.kind,a.freeze) for a in plan.actions],[('set_freeze',False)])

    def test_dry_run_and_stop_never_execute_and_present_correct_state(self):
        current = self.current(age=70,soil='clay')
        bridge = FakeGardenBridge(current)
        farm = Fazendeira(bridge)
        result = farm.run_cycle(golden_cookies_enabled=True)
        self.assertFalse(bridge.mutable_calls)
        self.assertEqual(current_state(current,result.plan)[0],'Aproveitando o bônus dos trevos')
        farm.run_cycle(dry_run=False,automation_enabled=True,golden_cookies_enabled=True,should_stop=lambda:True)
        self.assertFalse(bridge.mutable_calls)


class GoldenGardenUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QApplication.instance() or QApplication([])

    def setUp(self):
        previous = copy.deepcopy(automation_config.__dict__)
        self.addCleanup(lambda:automation_config.__dict__.update(previous))
        automation_config.enable_green_aching_thumb=False
        automation_config.enable_garden_golden_cookies=False
        for target in ('app.ui.main_window.save_automation_settings','app.ui.main_window.QTimer.singleShot'):
            p=patch(target); p.start(); self.addCleanup(p.stop)
        self.window=MainWindow()
        self.addCleanup(self.window.close)

    def test_checkbox_selects_one_strategy_and_saves_without_starting_automation(self):
        window=self.window
        window.garden_thumbcorn_checkbox.setChecked(True)
        window.garden_golden_checkbox.setChecked(True)
        self.assertFalse(window.garden_thumbcorn_checkbox.isChecked())
        self.assertTrue(automation_config.enable_garden_golden_cookies)
        self.assertFalse(automation_config.enable_green_aching_thumb)
        window.garden_thumbcorn_checkbox.setChecked(True)
        self.assertFalse(window.garden_golden_checkbox.isChecked())
        self.assertFalse(automation_config.enable_garden_golden_cookies)
        self.assertTrue(automation_config.enable_green_aching_thumb)

    def test_preview_and_timer_pass_selected_strategy_to_worker(self):
        window=self.window
        window.fazendeira=Mock()
        window.garden_golden_checkbox.setChecked(True)
        with patch.object(window,'_run_garden_task') as worker:
            for method in (window.refresh_garden,window.simulate_garden,window._on_garden_timer):
                method()
                operation=worker.call_args.args[0]
                operation()
                self.assertTrue(window.fazendeira.run_cycle.call_args.kwargs['golden_cookies_enabled'])

    def test_setting_roundtrip_and_conflicting_modes_have_one_winner(self):
        values={}
        class Settings:
            def __init__(self,*args):pass
            def beginGroup(self,*args):pass
            def endGroup(self):pass
            def sync(self):pass
            def setValue(self,key,value):values[key]=value
            def value(self,key,default=None,type=None):return values.get(key,default)
        with patch('app.config.settings.QSettings',Settings):
            for enabled in (True,False):
                automation_config.enable_garden_golden_cookies=enabled
                save_automation_settings()
                automation_config.enable_garden_golden_cookies=not enabled
                load_automation_settings()
                self.assertEqual(automation_config.enable_garden_golden_cookies,enabled)
            values.update(enable_green_aching_thumb=True,enable_garden_golden_cookies=True)
            load_automation_settings()
            self.assertFalse(automation_config.enable_green_aching_thumb)
            self.assertTrue(automation_config.enable_garden_golden_cookies)
