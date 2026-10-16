"""Drops, proteção do canteiro e parada dos objetivos finitos."""
import copy
import os
import unittest
from dataclasses import replace
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt5.QtWidgets import QApplication
from app.bridge.js_bridge import CookieClickerBridge
from app.config.settings import automation_config
from app.core.fazendeira import Fazendeira
from app.core.garden_catalog import TARGET_SEED_KEYS
from app.core.garden_strategies import GARDEN_DROPS
from app.models.garden import GardenUpgrade, GardenPlant, GardenCycleResult
from app.ui.main_window import MainWindow
from tests.test_garden import snapshot, FakeGardenBridge

FULL = tuple((x,y) for y in range(6) for x in range(6))


def current(pending=('Green yeast digestives',),plants=()):
    value=snapshot(set(TARGET_SEED_KEYS),plants,tiles=FULL,soil='fertilizer')
    return replace(value,upgrades=tuple(GardenUpgrade(name,key,name not in pending,False)
                                      for name,(key,rate) in GARDEN_DROPS.items()))


class DropBridge(FakeGardenBridge):
    def __init__(self,state,drop=True):
        super().__init__(state)
        self.drop=drop
        self.readable=True

    def harvest_garden_tile(self,x,y,**options):
        result=super().harvest_garden_tile(x,y,**options)
        self.current=replace(self.current,plants=tuple(p for p in self.current.plants if (p.x,p.y)!=(x,y)))
        if self.drop:
            self.current=replace(self.current,upgrades=tuple(replace(u,unlocked=True)
                if u.plant_key==options.get('expected_key') else u for u in self.current.upgrades))
        return result

    def get_garden_upgrades(self):
        return self.current.upgrades if self.readable else ()


class GardenUpgradesTests(unittest.TestCase):
    def plan(self,value):
        return Fazendeira(FakeGardenBridge(value)).build_plan(value,strategy='garden_upgrades')

    def test_all_seven_purchased_or_in_store_complete_without_actions(self):
        value=current(pending=())
        value=replace(value,upgrades=tuple(replace(u,unlocked=False,bought=True) if i%2 else u
                                          for i,u in enumerate(value.upgrades)))
        plan=self.plan(value)
        self.assertTrue(plan.completed)
        self.assertFalse(plan.actions)

    def test_only_missing_green_yeast_fills_plot_with_green_rot(self):
        plan=self.plan(current())
        self.assertFalse(plan.completed)
        self.assertEqual(plan.goal.target_name,'Green yeast digestives')
        self.assertEqual([(a.seed_key) for a in plan.actions if a.kind=='plant'],['greenRot']*36)
        self.assertFalse(any(a.kind=='boost_mutation' for a in plan.actions))

    def test_unknown_and_locked_discoveries_are_preserved(self):
        value=current(plants=(GardenPlant(0,0,999,'unknown','Unknown',1,50,False),
                              GardenPlant(1,1,32,'everdaisy','Everdaisy',1,71,False)))
        value=replace(value,seeds=tuple(replace(s,unlocked=False) if s.key=='everdaisy' else s for s in value.seeds))
        plan=self.plan(value)
        self.assertFalse(any((a.x,a.y) in {(0,0),(1,1)} for a in plan.actions))
        self.assertEqual(sum(a.kind=='plant' for a in plan.actions),34)

    def test_growing_drop_plants_are_kept_and_only_mature_ones_are_harvested(self):
        plants=(GardenPlant(0,0,0,'greenRot','Green rot',30,65,False),
                GardenPlant(1,0,0,'greenRot','Green rot',70,65,True))
        plan=self.plan(current(plants=plants))
        self.assertEqual([(a.kind,a.x,a.y,a.require_mature) for a in plan.actions],[('harvest',1,0,True)])

    def test_incidental_bakeberry_does_not_skip_missing_wheat_slims(self):
        plants=(GardenPlant(0,0,8,'bakeberry','Bakeberry',10,47.5,False),)
        value=current(pending=('Wheat slims','Bakeberry cookies'),plants=plants)
        plan=self.plan(value)
        self.assertEqual(plan.goal.target_name,'Wheat slims')
        self.assertTrue(all(a.seed_key=='bakerWheat' for a in plan.actions if a.kind=='plant'))
        self.assertEqual(sum(a.kind=='plant' for a in plan.actions),35)
        self.assertFalse(any((a.x,a.y)==(0,0) for a in plan.actions))
        self.assertIn('Aproveitar as plantas já presentes',plan.explanation)
        # Mesmo sem trigo restante no canteiro, o objetivo continua pendente.
        value=replace(value,plants=tuple(GardenPlant(x,y,8,'bakeberry','Bakeberry',10,47.5,False)
                                        for x,y in FULL))
        plan=self.plan(value)
        self.assertEqual(plan.goal.target_name,'Wheat slims')
        self.assertFalse(plan.actions)
        # Só a confirmação do drop permite avançar para Bakeberry cookies.
        value=replace(value,upgrades=tuple(replace(u,unlocked=True) if u.name=='Wheat slims' else u
                                          for u in value.upgrades))
        self.assertEqual(self.plan(value).goal.target_name,'Bakeberry cookies')

    def test_missing_upgrade_metadata_pauses_without_clearing(self):
        for upgrades in ((),current().upgrades[:-1]):
            plan=self.plan(replace(current(),upgrades=upgrades))
            self.assertFalse(plan.completed)
            self.assertFalse(plan.actions)
            self.assertIn('leitura completa',plan.explanation)

    def test_unavailable_required_seeds_pause_without_clearing(self):
        value=current()
        value=replace(value,seeds=tuple(replace(s,unlocked=False) if s.key=='greenRot' else s for s in value.seeds))
        plan=self.plan(value)
        self.assertFalse(plan.actions)
        self.assertFalse(plan.completed)
        self.assertEqual(plan.goal.pending_prerequisites,('Green rot',))

    def test_first_drop_stops_remaining_harvests_and_marks_complete_immediately(self):
        plants=tuple(GardenPlant(x,y,0,'greenRot','Green rot',70,65,True) for x,y in FULL)
        bridge=DropBridge(current(plants=plants))
        result=Fazendeira(bridge).run_cycle(dry_run=False,automation_enabled=True,strategy='garden_upgrades')
        self.assertTrue(result.plan.completed)
        self.assertEqual(len(bridge.mutable_calls),1)
        self.assertEqual(bridge.mutable_calls[0][0],'harvest')
        self.assertEqual(len(result.snapshot.plants),35)

    def test_failed_confirmation_stops_batch_without_claiming_success(self):
        plants=tuple(GardenPlant(x,y,0,'greenRot','Green rot',70,65,True) for x,y in FULL)
        bridge=DropBridge(current(plants=plants),drop=False)
        bridge.readable=False
        result=Fazendeira(bridge).run_cycle(dry_run=False,automation_enabled=True,strategy='garden_upgrades')
        self.assertFalse(result.plan.completed)
        self.assertEqual(len(bridge.mutable_calls),1)
        self.assertIn('confirmação',result.plan.explanation)

    def test_without_drop_all_mature_plants_are_tried_and_retry_is_needed(self):
        plants=tuple(GardenPlant(x,0,0,'greenRot','Green rot',70,65,True) for x in range(3))
        bridge=DropBridge(current(plants=plants),drop=False)
        result=Fazendeira(bridge).run_cycle(dry_run=False,automation_enabled=True,strategy='garden_upgrades')
        self.assertFalse(result.plan.completed)
        self.assertEqual(len(bridge.mutable_calls),3)

    def test_metadata_parser_rejects_missing_or_ambiguous_upgrade_status(self):
        payload=[dict(name=name,available=True,unlocked=False,bought=False) for name in GARDEN_DROPS]
        parsed=CookieClickerBridge._parse_garden_upgrades(payload)
        self.assertEqual(len(parsed),7)
        self.assertEqual({u.plant_key for u in parsed},{key for key,rate in GARDEN_DROPS.values()})
        for bad in (None,payload[:-1],payload+[payload[0]],
                    [dict(p,available=False) if i==0 else p for i,p in enumerate(payload)]):
            self.assertEqual(CookieClickerBridge._parse_garden_upgrades(bad),())

    def test_dry_run_does_not_harvest_or_change_garden(self):
        bridge=DropBridge(current())
        result=Fazendeira(bridge).run_cycle(strategy='garden_upgrades')
        self.assertTrue(result.dry_run)
        self.assertFalse(bridge.mutable_calls)

    def test_last_seed_is_confirmed_and_completed_in_the_harvest_cycle(self):
        plant=GardenPlant(0,0,0,'ichorpuff','Ichorpuff',70,50,True)
        value=replace(current(plants=(plant,)),seeds=tuple(replace(seed,unlocked=False)
                      if seed.key=='ichorpuff' else seed for seed in current().seeds))
        class Bridge(FakeGardenBridge):
            def harvest_garden_tile(self,x,y,**options):
                result=super().harvest_garden_tile(x,y,**options)
                self.current=replace(self.current,plants=(),seeds=tuple(replace(seed,unlocked=True)
                                     if seed.key=='ichorpuff' else seed for seed in self.current.seeds))
                return result
        bridge=Bridge(value)
        result=Fazendeira(bridge).run_cycle(dry_run=False,automation_enabled=True,strategy='plants')
        self.assertTrue(result.plan.completed)
        self.assertEqual(len(bridge.mutable_calls),1)

    def test_thumb_stops_at_1000_without_harvesting_the_rest_or_replanting(self):
        plants=tuple(GardenPlant(x,y,0,'thumbcorn','Thumbcorn',70,50,True) for x,y in FULL)
        value=replace(current(plants=plants),green_aching_thumb_won=False,green_aching_thumb_progress=999)
        class Bridge(FakeGardenBridge):
            def harvest_garden_tile(self,x,y,**options):
                result=super().harvest_garden_tile(x,y,**options)
                self.current=replace(self.current,green_aching_thumb_won=True,green_aching_thumb_progress=1000)
                return result
        bridge=Bridge(value)
        result=Fazendeira(bridge).run_cycle(dry_run=False,automation_enabled=True,strategy='green_aching_thumb')
        self.assertTrue(result.plan.completed)
        self.assertEqual(len(bridge.mutable_calls),1)

    def test_seed_collection_and_thumb_are_completed_only_on_game_confirmation(self):
        value=current()
        self.assertTrue(Fazendeira(FakeGardenBridge(value)).build_plan(value,strategy='plants').completed)
        value=replace(value,green_aching_thumb_won=True)
        self.assertTrue(Fazendeira(FakeGardenBridge(value)).build_plan(value,strategy='green_aching_thumb').completed)
        self.assertFalse(Fazendeira(FakeGardenBridge(value)).build_plan(value,strategy='golden_cookies').completed)


class GardenCompletionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QApplication.instance() or QApplication([])

    def setUp(self):
        previous=copy.deepcopy(automation_config.__dict__)
        self.addCleanup(lambda:automation_config.__dict__.update(previous))
        for target in ('app.ui.main_window.save_automation_settings','app.ui.main_window.QTimer.singleShot'):
            p=patch(target);p.start();self.addCleanup(p.stop)
        self.window=MainWindow()
        self.addCleanup(self.window.close)

    def test_each_finite_strategy_stops_only_garden_and_keeps_selection(self):
        window=self.window
        for strategy in ('plants','green_aching_thumb','garden_upgrades'):
            with self.subTest(strategy=strategy):
                window.garden_strategy_combo.setCurrentIndex(window.garden_strategy_combo.findData(strategy))
                window.garden_toggle.set_running(True)
                window.stock_toggle.set_running(True)
                window._bot_enabled=True
                automation_config.enable_garden_automation=True
                value=replace(current(pending=()),green_aching_thumb_won=True)
                plan=Fazendeira(FakeGardenBridge(value)).build_plan(value,strategy=strategy)
                self.assertTrue(plan.completed)
                window._display_garden_result(GardenCycleResult(value,plan,False,()))
                self.assertFalse(window.garden_toggle.running)
                self.assertFalse(automation_config.enable_garden_automation)
                self.assertTrue(window.stock_toggle.running)
                self.assertTrue(window._bot_enabled)
                self.assertEqual(window.garden_strategy_combo.currentData(),strategy)
                self.assertIn('Garden desligado',window.garden_feedback_label.text())

    def test_old_strategy_result_does_not_stop_newly_selected_golden_farm(self):
        window=self.window
        window.garden_strategy_combo.setCurrentIndex(window.garden_strategy_combo.findData('golden_cookies'))
        window.garden_toggle.set_running(True)
        value=replace(current(),green_aching_thumb_won=True)
        plan=Fazendeira(FakeGardenBridge(value)).build_plan(value,strategy='green_aching_thumb')
        window._display_garden_result(GardenCycleResult(value,plan,True,()))
        self.assertTrue(window.garden_toggle.running)
