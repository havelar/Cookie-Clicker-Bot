"""Faixas, RNG e carinho nativo do Krumblor sem executar o jogo real."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import unittest
from unittest.mock import Mock, patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication
from app.bridge.krumblor_scripts import KRUMBLOR_PET_SCRIPT
from app.config.settings import automation_config, load_automation_settings, save_automation_settings
from app.core.run import AutomationRunner
from app.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[1]
DRIVER = r"""
const fs=require('fs'), data=JSON.parse(fs.readFileSync(0,'utf8'));
const source=fs.readFileSync('reference/cookie-clicker/src/main.js','utf8');
const seedLine=source.split('\n').find(l=>l.includes('c.seedrandom=function')).trim().replace(')(this,[],Math',')(globalThis,[],Math');
globalThis.navigator={plugins:[]};
eval(seedLine);
const shuffleSource=source.match(/function shuffle\(array\)[\s\S]*?\n}/)[0];
globalThis.shuffle=eval('('+shuffleSource+')');
const RealDate=Date;
const date=new RealDate(2026,9,11,12,data.minute, data.second||0,0);
globalThis.Date=class extends RealDate {constructor(...args){super(...(args.length?args:[date.getTime()]));}static now(){return date.getTime();}};
const names=['Dragon scale','Dragon claw','Dragon fang','Dragon teddy bear'];
Math.seedrandom((data.seed||'test-seed')+'/dragonTime');
const expected=shuffle([...names])[Math.floor(data.minute/15)];
const owned=new Set(data.owned==='all'?names:data.owned==='current'?[expected]:[]);
const unlocked=new Set(data.unlocked==='current'?[expected]:[]);
let pics=!!data.open, pets=0;
const popup={classList:{contains:name=>pics&&name==='onScreen'}};
globalThis.document={getElementById:id=>id==='specialPopup'?popup:id==='specialPic'&&pics?{}:null};
globalThis.l=id=>document.getElementById(id);
globalThis.triggerAnim=()=>{};globalThis.PlaySound=()=>{};globalThis.loc=text=>text;
globalThis.Game={ready:true,seed:data.seed||'test-seed',dragonLevel:data.level??8,specialTab:data.open?'santa':'',promptOn:!!data.prompt,
 prefs:{particles:false}, Has:name=>name==='Pet the dragon'?!data.missing:owned.has(name),HasUnlocked:name=>unlocked.has(name),
 Unlock:name=>unlocked.add(name),Notify:()=>{},Upgrades:Object.fromEntries(names.map(n=>[n,{icon:[0,0]}])),
 ToggleSpecialMenu:on=>{if(on)pics=true;else if(Game.specialTab!==''){Game.specialTab='';pics=false;}}};
const native=source.match(/Game.ClickSpecialPic=function\(\)\s*(\{[\s\S]*?\n\t\t\})/)[1];
const nativePet=eval('(function()'+native+')');
Game.ClickSpecialPic=()=>{pets++;nativePet();};
const oldTab=Game.specialTab, oldPic=pics;
const random=()=>data.win?0:0.9;
Math.random=random;
const result=eval(data.script);
console.log(JSON.stringify({result,expected,pets,restored:Game.specialTab===oldTab&&pics===oldPic,
 rngUnchanged:Math.random===random,unlocked:[...unlocked]}));
"""

class KrumblorRuntimeTests(unittest.TestCase):
    def execute(self, **values):
        node=shutil.which('node')
        if not node: self.skipTest('Node necessário para validar o JavaScript nativo')
        values['script']=KRUMBLOR_PET_SCRIPT
        result=subprocess.run([node,'-e',DRIVER],input=json.dumps(values),text=True,capture_output=True,cwd=ROOT,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout)

    def test_slot_order_matches_native_shuffle_across_seeds_and_boundaries(self):
        for seed in ('test-seed','different-save','123456'):
            for minute in (0,14,15,29,30,44,45,59):
                with self.subTest(seed=seed,minute=minute):
                    value=self.execute(seed=seed,minute=minute,owned='current')
                    self.assertEqual(value['result']['drop'],value['expected'])
                    self.assertEqual(value['pets'],0)
                    self.assertTrue(value['rngUnchanged'])
                    self.assertEqual(value['result']['retryAfterMs'],(15-minute%15)*60000)

    def test_native_pet_unlocks_without_buying_and_restores_previous_panel(self):
        for opened in (False,True):
            value=self.execute(minute=15,win=True,open=opened)
            self.assertEqual(value['pets'],1)
            self.assertTrue(value['result']['unlocked'])
            self.assertIn(value['expected'],value['unlocked'])
            self.assertTrue(value['restored'])
            self.assertEqual(value['result']['reason'],'unlocked')

    def test_failed_roll_retries_once_per_second(self):
        value=self.execute(minute=14,second=59,win=False)
        self.assertEqual(value['pets'],1)
        self.assertFalse(value['result']['unlocked'])
        self.assertEqual(value['result']['retryAfterMs'],1000)
        self.assertTrue(value['restored'])

    def test_unlocked_or_all_collected_never_pet(self):
        for params, reason in (({'unlocked':'current'},'waiting_window'),({'owned':'all'},'complete')):
            value=self.execute(minute=0,**params)
            self.assertEqual(value['pets'],0)
            self.assertEqual(value['result']['reason'],reason)
            self.assertTrue(value['rngUnchanged'])

    def test_requirements_and_prompt_block_actions(self):
        for params,reason in (({'missing':True},'missing_upgrade'),({'level':7},'dragon_level'),({'prompt':True},'busy')):
            value=self.execute(minute=45,**params)
            self.assertEqual(value['pets'],0)
            self.assertEqual(value['result']['reason'],reason)

class KrumblorIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        previous=copy.deepcopy(automation_config.__dict__)
        self.addCleanup(lambda:automation_config.__dict__.update(previous))
        automation_config.enable_krumblor_upgrades=True
        with patch('app.core.run.InputHandler'):
            self.runner=AutomationRunner(123,Mock())

    def test_runner_waits_until_next_window_and_can_reset(self):
        self.runner.bridge.collect_krumblor_upgrade.return_value={'reason':'waiting_window','drop':'Dragon claw','retryAfterMs':900000}
        self.runner._run_krumblor_cycle(now=10)
        for now in (11,30,100,909):self.runner._run_krumblor_cycle(now=now)
        self.runner.bridge.collect_krumblor_upgrade.assert_called_once()
        self.runner._run_krumblor_cycle(now=910)
        self.assertEqual(self.runner.bridge.collect_krumblor_upgrade.call_count,2)
        self.runner.reset_krumblor_schedule()
        self.runner._run_krumblor_cycle(now=911)
        self.assertEqual(self.runner.bridge.collect_krumblor_upgrade.call_count,3)

    def test_configurable_interval_only_accelerates_active_pet_attempts(self):
        for interval in (0.05,0.1,0.5,5.0):
            with self.subTest(interval=interval):
                automation_config.krumblor_pet_interval_seconds=interval
                self.runner.reset_krumblor_schedule()
                self.runner.bridge.collect_krumblor_upgrade.return_value={'reason':'petting','retryAfterMs':1000,'windowRemainingMs':120000}
                self.runner._run_krumblor_cycle(now=10)
                self.assertAlmostEqual(self.runner._next_krumblor_check,10+interval)
        self.runner.reset_krumblor_schedule()
        self.runner.bridge.collect_krumblor_upgrade.return_value={'reason':'petting','retryAfterMs':10,'windowRemainingMs':10}
        self.runner._run_krumblor_cycle(now=20)
        self.assertAlmostEqual(self.runner._next_krumblor_check,20.05)

    def test_pause_exclusivity_and_disabled_checkbox_block_calls(self):
        self.runner.set_paused(True);self.runner._run_krumblor_cycle(now=0)
        self.runner.set_paused(False);self.runner.acquire_exclusive('test');self.runner._run_krumblor_cycle(now=1)
        self.runner.release_exclusive('test');automation_config.enable_krumblor_upgrades=False
        self.runner._run_krumblor_cycle(now=2)
        self.runner.bridge.collect_krumblor_upgrade.assert_not_called()

    def test_checkbox_is_in_automation_tab_and_persists(self):
        values={}
        class Settings:
            def __init__(self,*args):pass
            def beginGroup(self,*args):pass
            def endGroup(self):pass
            def sync(self):pass
            def setValue(self,k,v):values[k]=v
            def value(self,k,default=None,type=None):return values.get(k,default)
        with patch('app.config.settings.QSettings',Settings),patch('app.ui.main_window.save_automation_settings') as save:
            window=MainWindow()
            try:
                self.assertEqual(window.krumblor_checkbox.text(),'Coletar Krumblor Upgrades')
                self.assertTrue(window.tabs.widget(0).isAncestorOf(window.krumblor_checkbox))
                window.runner=self.runner
                window.krumblor_checkbox.setChecked(False)
                self.assertFalse(automation_config.enable_krumblor_upgrades)
                save.assert_called_once()
                window.krumblor_interval_input.setValue(0.25)
                self.assertEqual(automation_config.krumblor_pet_interval_seconds,0.25)
                save_automation_settings()
                automation_config.krumblor_pet_interval_seconds=5.0
                automation_config.enable_krumblor_upgrades=True
                load_automation_settings()
                self.assertFalse(automation_config.enable_krumblor_upgrades)
                self.assertEqual(automation_config.krumblor_pet_interval_seconds,0.25)
            finally:window.close()
