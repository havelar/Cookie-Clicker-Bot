"""Policy tests run the same atomic script used by the bridge."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import Mock, patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from app.bridge.wrinkler_scripts import WRINKLER_SCRIPT
from app.config.settings import automation_config
from app.core.run import AutomationRunner

ROOT = Path(__file__).resolve().parents[1]
DRIVER = r"""
const fs=require('fs'), data=JSON.parse(fs.readFileSync(0,'utf8'));
globalThis.Game={ready:true,seed:'save-a',cookies:data.cookies||0,OnAscend:!!data.ascend,
 wrinklers:data.wrinklers,getWrinklersMax:()=>data.capacity||10,
 Has:n=>(data.upgrades||[]).includes(n),auraMult:()=>data.aura||0,hasGod:()=>data.scorn||0};
Math.random=()=>{throw new Error('RNG should not be called by policy')};
Game.UpdateWrinklers=()=>{throw new Error('Native update should run only on its own frame')};
const before=JSON.stringify(Game.wrinklers.filter(w=>w.type===1));
const first=eval(data.script), second=eval(data.script);
console.log(JSON.stringify({first,second,wrinklers:Game.wrinklers,
 shinyUntouched:before===JSON.stringify(Game.wrinklers.filter(w=>w.type===1)),cookies:Game.cookies}));
"""

def normal(amount=100, phase=2, **extra):
    return dict(type=0,hp=3,phase=phase,sucked=amount,**extra)

class WrinklerRuntimeTests(unittest.TestCase):
    def execute(self, wrinklers, slots=1, requests=(), **values):
        node=shutil.which('node')
        if not node: self.skipTest('Node required')
        values.update(wrinklers=wrinklers,script=WRINKLER_SCRIPT.replace('__OPTIONS__',
            json.dumps(dict(freeSlots=slots,requests=requests))))
        result=subprocess.run([node,'-e',DRIVER],input=json.dumps(values),text=True,
                              capture_output=True,cwd=ROOT,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        result=json.loads(result.stdout)
        self.assertTrue(result['shinyUntouched'])
        self.assertEqual(result['cookies'],values.get('cookies',0))
        return result

    def request(self,target,seed='save-a',source='Garden'):
        return dict(target=target,seed=seed,source=source)

    def test_full_population_pops_lowest_normal_only(self):
        ws=[normal(100+i) for i in range(10)]
        ws[2]['type']=1;ws[2]['sucked']=0
        v=self.execute(ws)
        self.assertEqual(v['first']['popped'],[dict(index=0,reason='vacancy',estimatedCookies=110.00000000000001)])
        self.assertEqual(v['second']['popped'],[])
        self.assertEqual(v['first']['freeSlots'],1)

    def test_existing_vacancies_leave_accumulated_normals_alone(self):
        v=self.execute([normal()]*8+[normal(0,phase=0)]*6)
        self.assertEqual(v['first']['popped'],[])
        self.assertEqual(v['first']['freeSlots'],2)

    def test_approaching_normal_can_make_room(self):
        v=self.execute([normal(100)]*9+[normal(0,phase=1)])
        self.assertEqual(v['first']['popped'][0]['index'],9)

    def test_three_vacancies_and_changed_capacity(self):
        v=self.execute([normal(i) for i in range(12)],slots=3,capacity=12)
        self.assertEqual([p['index'] for p in v['first']['popped']],[0,1,2])
        self.assertEqual(v['first']['freeSlots'],3)
        self.assertEqual(v['second']['popped'],[])

    def test_twelve_free_slots_pops_all_normals(self):
        v=self.execute([normal(i) for i in range(12)],slots=12,capacity=12)
        self.assertEqual(len(v['first']['popped']),12)
        self.assertEqual(v['first']['freeSlots'],12)
        self.assertEqual(v['second']['popped'],[])

    def test_requested_slots_are_limited_by_current_capacity(self):
        v=self.execute([normal(i) for i in range(10)],slots=12,capacity=10)
        self.assertEqual(v['first']['desiredSlots'],10)
        self.assertEqual(v['first']['freeSlots'],10)
        self.assertEqual(len(v['first']['popped']),10)

    def test_twelve_slots_still_preserves_shiny(self):
        ws=[normal(i) for i in range(12)]
        ws[0]['type']=1
        v=self.execute(ws,slots=12,capacity=12)
        self.assertEqual(len(v['first']['popped']),11)
        self.assertEqual(v['first']['freeSlots'],11)
        self.assertTrue(v['first']['blocked'])

    def test_all_shiny_never_popped_even_when_capacity_shrinks(self):
        ws=[dict(normal(),type=1) for _ in range(12)]
        v=self.execute(ws,capacity=10)
        self.assertTrue(v['first']['blocked'])
        self.assertEqual(v['first']['popped'],[])

    def test_cash_selects_richest_and_stops_at_target(self):
        v=self.execute([normal(10),normal(500),normal(100)],requests=[self.request(550)])
        self.assertEqual([p['index'] for p in v['first']['popped']],[1])
        self.assertEqual(v['first']['popped'][0]['reason'],'cash')
        self.assertEqual(v['first']['funded'],['Garden'])
        self.assertEqual(v['second']['popped'],[])

    def test_vacancy_payout_can_already_fund_action(self):
        v=self.execute([normal(100)]*10,requests=[self.request(100)])
        self.assertEqual(len(v['first']['popped']),1)
        self.assertEqual(v['first']['popped'][0]['reason'],'vacancy')

    def test_impossible_target_does_not_empty_population(self):
        v=self.execute([normal(100)]*9,requests=[self.request(10000)])
        self.assertEqual(v['first']['popped'],[])

    def test_cash_keeps_at_least_one_normal(self):
        v=self.execute([normal(100)]*3,requests=[self.request(220)])
        self.assertEqual(len(v['first']['popped']),2)
        self.assertEqual(v['second']['popped'],[])

    def test_stale_save_request_and_already_affordable_never_pop(self):
        for request,cookies in [(self.request(500,'old-save'),0),(self.request(500),600)]:
            v=self.execute([normal(1000)]*3,requests=[request],cookies=cookies)
            self.assertEqual(v['first']['popped'],[])

    def test_unaffordable_large_request_does_not_block_small_request(self):
        v=self.execute([normal(1000)]*3,requests=[self.request(100000),self.request(100,source='Banco')])
        self.assertEqual(v['first']['funded'],['Banco'])
        self.assertEqual(len(v['first']['popped']),1)

    def test_payout_accounts_for_owned_bonuses(self):
        v=self.execute([normal(100)]*10,upgrades=['Sacrilegious corruption','Wrinklerspawn'],aura=1,scorn=1)
        self.assertAlmostEqual(v['first']['popped'][0]['estimatedCookies'],100*1.1*1.05*1.2*1.05*1.15)

    def test_inactive_slots_and_unknown_types_never_popped(self):
        ws=[normal(100,phase=0)]*10
        v=self.execute(ws)
        self.assertEqual(v['first']['popped'],[])
        v=self.execute([dict(normal(),type=2)]*10)
        self.assertEqual(v['first']['popped'],[])
        self.assertTrue(v['first']['blocked'])

    def test_ascension_blocks_all_changes(self):
        v=self.execute([normal()]*10,ascend=True)
        self.assertIsNone(v['first'])

class WrinklerRunnerTests(unittest.TestCase):
    def setUp(self):
        self.old=copy.deepcopy(automation_config)
        automation_config.enable_wrinkler_popper=True
        self.bridge=Mock()
        self.bridge.manage_wrinklers.return_value=dict(popped=[],funded=[],blocked=False)
        with patch('app.core.run.InputHandler'):
            self.runner=AutomationRunner(0,self.bridge)
    def tearDown(self):
        automation_config.__dict__.update(self.old.__dict__)
    def test_paused_disabled_exclusive_and_stopped_do_not_act(self):
        for mode in ('pause','disabled','exclusive','stop'):
            with self.subTest(mode=mode):
                self.runner.paused.clear();self.runner.stop_event.clear();self.runner._exclusive_owner=None
                automation_config.enable_wrinkler_popper=True
                if mode=='pause':self.runner.paused.set()
                if mode=='disabled':automation_config.enable_wrinkler_popper=False
                if mode=='exclusive':self.runner._exclusive_owner='save_scum'
                if mode=='stop':self.runner.stop_event.set()
                self.assertFalse(self.runner._run_wrinkler_cycle())
        self.bridge.manage_wrinklers.assert_not_called()
    def test_poll_throttled_even_during_fast_krumblor_loop(self):
        self.runner._run_wrinkler_cycle(now=100)
        self.runner._run_wrinkler_cycle(now=100.1)
        self.runner._run_wrinkler_cycle(now=102)
        self.assertEqual(self.bridge.manage_wrinklers.call_count,2)
    def test_cash_requests_expire_clear_on_pause_and_restore(self):
        with patch('app.core.run.time.monotonic',return_value=100):
            self.runner.request_wrinkler_cash('Garden',100,'save-a',ttl=2)
        self.runner._run_wrinkler_cycle(now=103)
        self.assertEqual(self.bridge.manage_wrinklers.call_args.args[1],[])
        self.runner.request_wrinkler_cash('Garden',100,'save-a')
        self.runner.set_paused(True)
        self.assertEqual(self.runner._cash_requests,{})
        self.runner.set_paused(False)
        self.runner.request_wrinkler_cash('Garden',100,'save-a')
        self.runner._exclusive_owner='backup_restore'
        self.runner.release_exclusive('backup_restore')
        self.assertEqual(self.runner._cash_requests,{})
    def test_counter_and_grouped_logs_include_each_pop(self):
        self.bridge.manage_wrinklers.return_value=dict(popped=[dict(reason='vacancy'),dict(reason='vacancy')],funded=[],blocked=False)
        self.assertTrue(self.runner._run_wrinkler_cycle(now=1))
        self.assertEqual(self.runner.wrinklers_popped,2)
    def test_funded_request_removed_without_repeating(self):
        self.runner.request_wrinkler_cash('Garden',100,'save-a')
        self.bridge.manage_wrinklers.return_value=dict(popped=[],funded=['Garden'],blocked=False)
        self.runner._run_wrinkler_cycle()
        self.assertEqual(self.runner._cash_requests,{})

class WrinklerUISettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.old=copy.deepcopy(automation_config.__dict__)
        self.addCleanup(lambda:automation_config.__dict__.update(self.old))
    def test_existing_checkbox_and_slot_preference_persist(self):
        from app.ui.main_window import MainWindow
        from app.config.settings import load_automation_settings,save_automation_settings
        values={}
        class Settings:
            def __init__(self,*args):pass
            def beginGroup(self,*args):pass
            def endGroup(self):pass
            def sync(self):pass
            def setValue(self,k,v):values[k]=v
            def value(self,k,default=None,type=None):return values.get(k,default)
        with patch('app.config.settings.QSettings',Settings),patch('app.ui.main_window.save_automation_settings'):
            window=MainWindow()
            try:
                self.assertEqual(window.wrinkler_checkbox.text(),'Wrinklers inteligentes')
                self.assertTrue(window.tabs.widget(0).isAncestorOf(window.wrinkler_checkbox))
                self.assertTrue(window.wrinkler_checkbox.toolTip())
                window.wrinkler_checkbox.setChecked(True)
                window.wrinkler_free_slots_input.setValue(12)
                self.assertTrue(window.wrinkler_free_slots_input.isEnabled())
                save_automation_settings()
                automation_config.wrinkler_free_slots=1
                load_automation_settings()
                self.assertEqual(automation_config.wrinkler_free_slots,12)
                self.assertTrue(automation_config.enable_wrinkler_popper)
                values['wrinkler_free_slots']=99
                load_automation_settings()
                self.assertEqual(automation_config.wrinkler_free_slots,12)
                values['wrinkler_free_slots']=0
                load_automation_settings()
                self.assertEqual(automation_config.wrinkler_free_slots,1)
            finally:window.close()
    def test_paused_stock_read_only_cycle_does_not_request_cash(self):
        from app.ui.main_window import MainWindow
        from app.models.stock_market import StockMarketAutomationResult,StockMarketSnapshot,StockMarketStatus,StockAsset,StockMarketSignal
        with patch('app.ui.main_window.save_automation_settings'):
            window=MainWindow()
            try:
                window.runner=Mock()
                window._bot_enabled=False
                window.stock_toggle.set_running(True)
                asset=StockAsset(0,'Cereals','CRL',10,0,100)
                snapshot=StockMarketSnapshot(StockMarketStatus(True,True,''),cookies=0,highest_raw_cps=100,
                    broker_overhead=1.2,game_seed='save-a',assets=(asset,))
                signal=StockMarketSignal(0,'CRL',10,None,True,None,False)
                value=StockMarketAutomationResult(snapshot,signals=(signal,),tick_changed=True)
                window._display_stock_automation_result(value)
                self.assertEqual(window.runner.request_wrinkler_cash.call_args.args[1],0)
                window._bot_enabled=True;window._stock_stop.clear()
                window._display_stock_automation_result(value)
                self.assertEqual(window.runner.request_wrinkler_cash.call_args.args[1],1200)
                window._toggle_stock_auto_trade(False)
                window.runner.request_wrinkler_cash.assert_called_with('Banco')
            finally:window.close()

    def test_garden_only_requests_real_blocked_layout_and_cancels_on_stop(self):
        from app.ui.main_window import MainWindow
        from app.models.garden import GardenCycleResult,GardenSnapshot,GardenStatus,GardenPlan,GardenActionResult
        with patch('app.ui.main_window.save_automation_settings'):
            window=MainWindow()
            try:
                window.runner=Mock();window._bot_enabled=True
                window.garden_toggle.set_running(True);window._garden_stop.clear()
                snapshot=GardenSnapshot(GardenStatus(True,True,''),game_seed='save-a')
                wait=GardenActionResult(False,'plant','waiting',waiting=True,reason='insufficient_funds',
                                       required_cookies=400,available_cookies=300)
                plan=GardenPlan(None)
                window._display_garden_result(GardenCycleResult(snapshot,plan,False,(wait,)))
                window.runner.request_wrinkler_cash.assert_called_with('Garden',400,'save-a',ttl=600)
                window._display_garden_result(GardenCycleResult(snapshot,plan,True,(wait,)))
                window.runner.request_wrinkler_cash.assert_called_with('Garden',0,'save-a',ttl=600)
                window._toggle_garden_automation(False)
                window.runner.request_wrinkler_cash.assert_called_with('Garden')
            finally:window.close()
