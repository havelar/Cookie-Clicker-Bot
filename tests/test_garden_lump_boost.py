"""Decisão de espera e recarga nativa para Juicy Queenbeet."""
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from app.bridge.js_bridge import CookieClickerBridge
from app.core.fazendeira import Fazendeira
from app.models.garden import GardenActionResult
from tests import test_queenbeet_rings as ring_fixture
from tests.test_garden import FakeGardenBridge


class JuicyBoostDecisionTests(unittest.TestCase):
    def current(self, ages=(70,10,10,10), *, immature=None, soil='fertilizer', cooldown=True):
        helper=ring_fixture.QueenbeetRingTests()
        plants=[]
        for i,center in enumerate(helper.centers):
            for pos in helper.ring(center):
                age=immature[1] if immature and pos==immature[0] else ages[i]
                plants.append(replace(helper.plant(pos,mature=age>=50),age=age,average_growth=1,maximum_growth=2))
        return replace(helper.current(plants),soil_key=soil,sugar_lumps=1000,can_refill_lump=cooldown,next_tick_at=100)

    def plan(self,current):
        return Fazendeira(FakeGardenBridge(current),clock=lambda:1).build_plan(current)

    def test_one_ready_ring_uses_woodchips_then_boost_with_others_young(self):
        plan=self.plan(self.current())
        self.assertEqual([a.kind for a in plan.actions],['change_soil','boost_mutation'])
        self.assertEqual(plan.actions[0].soil_key,'woodchips')

    def test_two_ready_rings_wait_for_third_if_eta_is_short_and_safe(self):
        plan=self.plan(self.current((70,70,48,10)))
        self.assertTrue(any(a.kind=='change_soil' and a.soil_key=='woodchips' for a in plan.actions))
        self.assertFalse(any(a.kind=='boost_mutation' for a in plan.actions))
        self.assertIn('2 tick(s)',plan.explanation)

    def test_two_ready_rings_do_not_wait_for_slow_third(self):
        plan=self.plan(self.current((70,70,40,10)))
        self.assertTrue(any(a.kind=='boost_mutation' for a in plan.actions))

    def test_do_not_wait_when_ready_parents_lack_life_margin(self):
        plan=self.plan(self.current((94,94,48,10)))
        self.assertTrue(any(a.kind=='boost_mutation' for a in plan.actions))

    def test_one_immature_parent_never_counts_as_ready_ring(self):
        plan=self.plan(self.current((70,10,10,10),immature=((0,0),49)))
        self.assertFalse(any(a.kind=='boost_mutation' for a in plan.actions))

    def test_soil_cooldown_waits_without_planning_a_lump(self):
        plan=self.plan(replace(self.current(),next_soil_at=100))
        self.assertFalse(any(a.kind in ('change_soil','boost_mutation') for a in plan.actions))
        self.assertIn('cooldown para mudar',plan.explanation)

    def test_cooldown_or_near_death_blocks_spending_but_keeps_woodchips(self):
        for current in (self.current(cooldown=False),self.current((99,10,10,10))):
            plan=self.plan(current)
            self.assertFalse(any(a.kind=='boost_mutation' for a in plan.actions))
            self.assertTrue(any(a.kind=='change_soil' and a.soil_key=='woodchips' for a in plan.actions))

    def test_spending_disabled_in_preview_and_runs_once_per_tick(self):
        current=self.current(soil='woodchips')
        bridge=FakeGardenBridge(current)
        spent=[]
        bridge.boost_juicy_queenbeet=lambda:spent.append(1) or GardenActionResult(True,'boost_mutation','Used')
        farmer=Fazendeira(bridge)
        farmer.run_cycle(dry_run=True,automation_enabled=True)
        farmer.run_cycle(dry_run=False,automation_enabled=False)
        self.assertEqual(spent,[])
        farmer.run_cycle(dry_run=False,automation_enabled=True)
        farmer.run_cycle(dry_run=False,automation_enabled=True)
        self.assertEqual(spent,[1])


@unittest.skipUnless(shutil.which('node'),'Node.js necessário para o runtime isolado')
class JuicyBoostRuntimeTests(unittest.TestCase):
    def run_boost(self, **options):
        class Capture(CookieClickerBridge):
            def __init__(self): pass
            def execute_js(self,code): self.script=code;return {'ok':True}
        bridge=Capture();bridge.boost_juicy_queenbeet()
        fixture=Path(__file__).with_name('fixtures').joinpath('garden_budget_runtime.js').read_text(encoding='utf-8').replace('OPTIONS','{"occupied":false}')
        source=fixture+'\nconst cfg='+json.dumps(options)+''';
        const q={id:2,key:'queenbeet',unlocked:true,plantable:true,cost:100,mature:50,ageTick:1,ageTickR:1};
        seeds.push(q);M.plants.queenbeet=q;M.plants.queenbeetLump={unlocked:!!cfg.found};
        M.soilsById=[{id:0,key:cfg.wrongSoil?'fertilizer':'woodchips'}];M.soil=0;M.loopsMult=cfg.pending?3:1;
        M.plotBoost=Array.from({length:6},()=>Array.from({length:6},()=>[1,1,1]));
        for(let y=0;y<3;y++)for(let x=0;x<3;x++)if(x!==1||y!==1)M.plot[y][x]=[3,cfg.old?99:70];
        if(cfg.immature)M.plot[0][0][1]=49;
        if(cfg.occupied)M.plot[1][1]=[1,70];
        if(cfg.protected){seeds[0].key='unknownPlant';M.plot[5][5]=[1,70];}
        Game.lumps=cfg.noLumps?0:1000;Game.prefs={askLumps:1};Game.auraMult=()=>0;Game.lumpRefill=0;
        Game.canRefillLump=()=>!cfg.cooldown&&!Game.lumpRefill;Game.getLumpRefillMax=()=>27000;
        Game.refillLump=(n,callback)=>{if(Game.prefs.askLumps)throw Error('unexpected prompt');if(Game.canRefillLump()&&Game.lumps>=n){Game.lumps-=n;Game.lumpRefill=27000;events.push(['refill']);callback();}};
        '''
        source+='\nconst result='+bridge.script+';console.log(JSON.stringify({result,events,lumps:Game.lumps,ask:Game.prefs.askLumps,loops:M.loopsMult,next:M.nextStep}));'
        process=subprocess.run([shutil.which('node'),'-e',source],capture_output=True,text=True,check=True)
        return json.loads(process.stdout)

    def test_native_refill_spends_exactly_one_and_restores_confirmation_setting(self):
        data=self.run_boost()
        self.assertTrue(data['result']['ok'])
        self.assertEqual(data['lumps'],999)
        self.assertEqual(data['events'],[['refill']])
        self.assertEqual(data['ask'],1)
        self.assertEqual(data['loops'],3)
        self.assertGreater(data['next'],0)

    def test_revalidate_live_ring_and_resources_before_spending(self):
        for name in ('wrongSoil','pending','found','old','immature','occupied','protected','cooldown','noLumps'):
            with self.subTest(reason=name):
                data=self.run_boost(**{name:True})
                self.assertFalse(data['result']['ok'])
                self.assertEqual(data['events'],[])
                self.assertEqual(data['lumps'],0 if name=='noLumps' else 1000)
                self.assertEqual(data['ask'],1)
