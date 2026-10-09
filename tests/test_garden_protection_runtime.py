"""Proteções executadas dentro do JS, independentes do planejador chamador."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import Mock
from app.bridge.js_bridge import CookieClickerBridge
from app.models.garden import GardenAction
from app.core.fazendeira import Fazendeira
from app.core.garden_catalog import TARGET_SEED_KEYS
from app.models.garden import GardenPlant
from tests.test_garden import snapshot, FakeGardenBridge


@unittest.skipUnless(shutil.which("node"), "Node.js necessário para o runtime isolado")
class GardenProtectionRuntimeTests(unittest.TestCase):
    def test_ring_renovation_waits_for_entire_budget_before_first_removal(self):
        ring=set(Fazendeira._neighbors((1,1)))
        plants=tuple(GardenPlant(x,y,2,'queenbeet','Queenbeet',70,50,True) for x,y in ring if (x,y)!=(0,0))
        current=snapshot(set(TARGET_SEED_KEYS)-{'queenbeetLump'},plants,tiles=tuple((x,y) for y in range(3) for x in range(3)))
        plan=Fazendeira(FakeGardenBridge(current)).build_plan(current)
        actions=tuple(a for a in plan.actions if a.kind in {'plant','harvest'})
        class Capture(CookieClickerBridge):
            def __init__(self): pass
            def execute_js(self,code): self.script=code; return []
        bridge=Capture()
        bridge.execute_garden_layout(actions)
        fixture=Path(__file__).with_name('fixtures').joinpath('garden_budget_runtime.js').read_text(encoding='utf-8')
        for cookies in (799,800):
            with self.subTest(cookies=cookies):
                source=fixture.replace('OPTIONS',json.dumps({'cookies':cookies,'occupied':False}))
                source+="\nconst q={id:2,key:'queenbeet',unlocked:true,plantable:true,cost:100,mature:50};seeds.push(q);M.plants.queenbeet=q;"
                for x,y in ring-{(0,0)}: source+=f'M.plot[{y}][{x}]=[3,70];'
                source+='\nconst result='+bridge.script+';console.log(JSON.stringify({result,events,plot:M.plot,cookies:Game.cookies}));'
                process=subprocess.run([shutil.which('node'),'-e',source],capture_output=True,text=True,check=True)
                data=json.loads(process.stdout)
                if cookies==799:
                    self.assertEqual(data['events'],[])
                    self.assertTrue(data['result'][0]['waiting'])
                    self.assertTrue(all(data['plot'][y][x]==[3,70] for x,y in ring-{(0,0)}))
                else:
                    self.assertEqual(len(data['events']),15)
                    self.assertTrue(all(data['plot'][y][x]==[3,0] for x,y in ring))
                    self.assertEqual(data['cookies'],0)

    def run_action(self, kind, *, key="unknownPlant", locked=False, unmapped=False):
        class Capture(CookieClickerBridge):
            def __init__(self): pass
            def execute_js(self, code):
                self.script=code
                return {"ok": True}
        bridge=Capture()
        if kind == "harvest": bridge.harvest_garden_tile(0,0, require_mature=True)
        elif kind == "cleanup": bridge.harvest_garden_tile(0,0, require_mature=False)
        elif kind == "layout":
            bridge.execute_garden_layout((GardenAction("harvest", "cleanup", x=0,y=0,seed_key="bakerWheat",require_mature=False),
                                         GardenAction("plant", "fill",x=0,y=0,seed_key="thumbcorn")))
        elif kind == "plant":
            bridge.execute_garden_layout((GardenAction("plant", "fill",x=0,y=0,seed_key="thumbcorn"),))
        elif kind == "ascend": bridge.start_ascension(1)
        runtime=Path(__file__).with_name('fixtures').joinpath('garden_budget_runtime.js').read_text(encoding='utf-8').replace('OPTIONS','{}')
        runtime += "\nseeds[0].key="+json.dumps(key)+";seeds[0].unlocked="+str(not locked).lower()+";M.plot[0][0]=[1,100];"
        if unmapped: runtime += "M.plot[0][0]=[999,100];"
        runtime += "Game.Ascend=()=>{events.push(['ascend']);Game.OnAscend=true;};Game.HowMuchPrestige=()=>100;"
        source=runtime+'\nconst result='+bridge.script+';console.log(JSON.stringify({result,events,plot:M.plot}));'
        process=subprocess.run([shutil.which('node'),'-e',source],capture_output=True,text=True,check=True)
        return json.loads(process.stdout)

    def test_unknown_species_cannot_be_harvested_or_cleaned_by_any_caller(self):
        for kind in ('harvest','cleanup','layout','plant','ascend'):
            with self.subTest(kind=kind):
                data=self.run_action(kind)
                self.assertEqual(data['events'],[])
                self.assertEqual(data['plot'][0][0],[1,100])

    def test_unmapped_occupied_tile_is_not_treated_as_empty(self):
        for kind in ('plant','ascend'):
            data=self.run_action(kind,unmapped=True)
            self.assertEqual(data['events'],[])
            self.assertEqual(data['plot'][0][0],[999,100])

    def test_locked_discovery_can_be_collected_mature_but_not_cleaned_or_ascended(self):
        for kind in ('cleanup','layout','ascend'):
            data=self.run_action(kind,key='bakerWheat',locked=True)
            self.assertEqual(data['events'],[])
        data=self.run_action('harvest',key='bakerWheat',locked=True)
        self.assertTrue(data['result']['ok'])
        self.assertEqual(data['events'],[['harvest',0,0]])


class GardenProtectionValidationTests(unittest.TestCase):
    def test_unknown_removal_rejects_entire_batch_before_entering_game(self):
        bridge=CookieClickerBridge()
        bridge.execute_js=Mock()
        result=bridge.execute_garden_layout((GardenAction('harvest','cleanup',x=0,y=0,seed_key='unknownPlant',require_mature=False),))
        self.assertFalse(result[0].success)
        bridge.execute_js.assert_not_called()
