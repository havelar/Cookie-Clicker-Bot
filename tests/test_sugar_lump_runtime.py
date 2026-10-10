"""Ações reais da bridge executadas em runtime isolado, sem tocar o jogo aberto."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from app.bridge.js_bridge import CookieClickerBridge

ROOT = Path(__file__).resolve().parents[1]

class CaptureBridge(CookieClickerBridge):
    def __init__(self):
        self.script = ''
    def execute_js(self, code):
        self.script = code
        return {}
    def _execute_game_action(self, code):
        return self.execute_js(code)

@unittest.skipUnless(shutil.which('node'), 'Node necessário para runtime isolado')
class SugarLumpRuntimeTests(unittest.TestCase):
    def run_script(self, method, options=None, **kwargs):
        bridge = CaptureBridge()
        getattr(bridge, method)(**kwargs)
        source=(ROOT/'reference/cookie-clicker/src/main.js').read_text(encoding='utf-8')
        native_click=source[source.index('Game.clickLump=function'):source.index('Game.harvestLumps=function')]
        setup = r'''
const cfg=OPTIONS, now=1000000000000;
Date.now=()=>now;
const events=[];
globalThis.triggerAnim=()=>{};globalThis.l=()=>({});
const Game=globalThis.Game={lumps:100,lumpT:now-(cfg.young?100:cfg.matureOnly?1500:2500),
    lumpCurrentType:cfg.type??0,lumpMatureAge:1000,lumpRipeAge:2000,lumpOverripeAge:4000,
    seed:'example',version:2.053,SaveTo:'test',canLumps:()=>!cfg.unavailable,Win:()=>{},
    harvestLumps(n){events.push(['harvest',n]);this.lumpT=Date.now();this.lumps+=n;},
    computeLumpType(){events.push(['compute']);this.lumpCurrentType=4;}};
if(cfg.overripe)Game.lumpT=now-5000;
if(cfg.ascend)Game.OnAscend=true;
const choose=()=>cfg.botched?0:1;
const raw=()=>{const stats=['0','0','0','bakery',Game.seed],v=Array(47).fill('0');v[44]=String(Game.lumpT);v[46]=String(Game.lumpCurrentType);return '2.053||'+stats.join(';')+'||'+v.join(';');};
let stored='';
Game.WriteSave=(mode)=>{Game.lastSaveData=raw();const data=Buffer.from(raw()).toString('base64')+'!END!';events.push(['save',mode??0]);if(mode===1)return data;stored=data;};
globalThis.localStorageGet=()=>stored;
globalThis.b64_to_utf8=v=>Buffer.from(v,'base64').toString();
Game.LoadSave=save=>{events.push(['load']);if(cfg.reject)return false;const parts=b64_to_utf8(unescape(save).split('!END!')[0]).split('|'),v=parts[4].split(';');Game.seed=parts[2].split(';')[4];Game.lumpT=Number(v[44]);Game.lumpCurrentType=cfg.diverge?1:Number(v[46]);return true;};
'''.replace('OPTIONS',json.dumps(options or {}))
        script=setup+'\n'+native_click+'\nconst result='+bridge.script+'; console.log(JSON.stringify({result,events,lumps:Game.lumps,started:Game.lumpT,type:Game.lumpCurrentType}));'
        result=subprocess.run([shutil.which('node'),'-e',script],capture_output=True,text=True,check=True)
        return json.loads(result.stdout)

    def test_scalar_balance_and_all_five_types_are_read_correctly(self):
        for t in range(5):
            with self.subTest(t=t):
                data=self.run_script('get_sugar_lump_status',{'type':t})
                self.assertEqual(data['result']['type'],t)
                self.assertTrue(data['result']['ready'])
                self.assertEqual(data['result']['lumps'],100)
                self.assertEqual(data['events'],[])

    def test_growth_maturity_and_unavailable_states(self):
        self.assertFalse(self.run_script('get_sugar_lump_status',{'young':True})['result']['mature'])
        self.assertTrue(self.run_script('get_sugar_lump_status',{'matureOnly':True})['result']['mature'])
        self.assertFalse(self.run_script('get_sugar_lump_status',{'matureOnly':True})['result']['ready'])
        for cfg in ({'unavailable':True},{'ascend':True}):
            self.assertIsNone(self.run_script('get_sugar_lump_status',cfg)['result'])

    def test_native_click_rotates_type_and_start(self):
        result=self.run_script('harvest_sugar_lump_result')
        self.assertTrue(result['result']['ok'])
        self.assertEqual(result['result']['newType'],4)
        self.assertEqual(result['events'],[['harvest',1],['compute']])

    def test_botched_early_harvest_still_generates_next_lump(self):
        result=self.run_script('harvest_sugar_lump_result',{'matureOnly':True,'botched':True})
        self.assertTrue(result['result']['ok'])
        self.assertEqual(result['result']['gained'],0)
        self.assertEqual(result['result']['newType'],4)

    def test_guards_do_not_click_or_open_generic_buttons(self):
        cases=[({'young':True},{}),({'overripe':True},{}),({'ascend':True},{}),
               ({'matureOnly':True,'type':2},{'preserved_types':(2,4)}),
               ({'matureOnly':True,'type':4},{'preserved_types':(2,4)}),
               ({},{'expected_start':1}),({},{'after_start':1000000000000})]
        for options,kwargs in cases:
            with self.subTest(options=options,kwargs=kwargs):
                result=self.run_script('harvest_sugar_lump_result',options,**kwargs)
                self.assertFalse(result['result']['ok'])
                self.assertEqual(result['events'],[])

    def test_preserved_ripe_lump_is_harvested(self):
        result=self.run_script('harvest_sugar_lump_result',{'type':2},preserved_types=(2,4))
        self.assertTrue(result['result']['ok'])
