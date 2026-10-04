import json
from pathlib import Path
import shutil
import subprocess
import unittest

from app.bridge.js_bridge import CookieClickerBridge


@unittest.skipUnless(shutil.which('node'), 'Node.js required for isolated runtime')
class SimpleFarmRuntimeTests(unittest.TestCase):
    def run_action(self, action='reinvest', *, floor=80000, **options):
        class Capture(CookieClickerBridge):
            def __init__(self):
                pass

            def execute_js(self, code):
                self.script = code
                return {'ok': True}

        bridge = Capture()
        if action == 'spell':
            bridge.execute_simple_farm_spell(expected_cast=10, minimum_buff_seconds=8)
        elif action == 'forecast':
            bridge.forecast_simple_farm_spell(2)
        elif action == 'snapshot':
            bridge.get_combo_snapshot(require_minigames=False)
        else:
            bridge.reinvest_simple_farm(floor, .05, .8)
        runtime = Path(__file__).with_name('fixtures').joinpath('simple_farm_runtime.js').read_text(encoding='utf-8')
        source = runtime.replace('OPTIONS', json.dumps(options)) + '\nconst result=' + bridge.script
        source += ';console.log(JSON.stringify({result,events,cookies:Game.cookies,lumps:Game.lumps,buyMode:Game.buyMode}));'
        output = subprocess.run([shutil.which('node'), '-e', source], capture_output=True, text=True, check=True)
        return json.loads(output.stdout)

    def test_percent_upgrade_has_priority_and_buildings_share_same_budget(self):
        data = self.run_action(upgrades=[{'name':'Kitten helpers','pool':'','price':500}, {}],
                               buildings=[{'id':1}, {'id':2,'storedTotalCps':1000}])
        self.assertTrue(data['result']['ok'])
        self.assertEqual(data['events'][0], ['upgrade','Production cookie'])
        self.assertEqual(data['events'][1], ['building',2])
        self.assertGreater(data['result']['buildings'], 0)
        self.assertLessEqual(data['result']['spent'], 5000)
        self.assertGreaterEqual(data['cookies'], 95000)
        self.assertEqual(data['buyMode'], -1)
        self.assertEqual(data['lumps'], 10)

    def test_other_farm_spending_below_floor_prevents_purchase(self):
        data = self.run_action(cookies=79000, upgrades=[{}], buildings=[{}])
        self.assertTrue(data['result']['waiting'])
        self.assertEqual(data['events'], [])

    def test_live_balance_growth_recalculates_majority_reserve(self):
        data = self.run_action(cookies=200000, buildings=[{}])
        self.assertEqual(data['result']['reserve'], 160000)
        self.assertLessEqual(data['result']['spent'], 10000)

    def test_cheap_buildings_at_huge_balance_do_not_trigger_false_failure(self):
        data = self.run_action(cookies=1e58, buildings=[{'price':1}])
        self.assertTrue(data['result']['ok'])
        self.assertEqual(data['result']['buildings'], 25)

    def test_lucky_reserve_and_small_excess_limit_total_spending(self):
        data = self.run_action(cps=16.5, upgrades=[{'price':500}], buildings=[{'price':500}])
        self.assertEqual(data['result']['reserve'], 99000)
        self.assertGreaterEqual(data['cookies'], 99000)
        self.assertLessEqual(data['result']['spent'], 1000)

    def test_special_vaulted_and_lump_upgrades_are_never_bought(self):
        data = self.run_action(upgrades=[{'name':'Sugar frenzy','priceLumps':1},
            {'name':'Chocolate egg'}, {'vaulted':True}, {'clickFunction':True},
            {'pool':'toggle'}, {'name':'Unknown upgrade','pool':'','power':0}])
        self.assertEqual(data['events'], [])
        self.assertEqual(data['lumps'], 10)

    def test_live_buff_prevents_spending_after_stale_snapshot(self):
        data = self.run_action(buffs=['frenzy'], upgrades=[{}], buildings=[{}])
        self.assertEqual(data['events'], [])

    def test_single_spell_works_with_one_tower_without_spending_cookies(self):
        data = self.run_action('spell', buffs=['frenzy'])
        self.assertTrue(data['result']['ok'])
        self.assertEqual(data['events'], [['cast'], ['pop']])
        self.assertEqual(data['cookies'], 100000)
        self.assertEqual(data['lumps'], 10)

    def test_existing_click_buff_insufficient_mana_or_changed_forecast_do_not_cast(self):
        for options in [{'buffs':['frenzy','click frenzy']}, {'buffs':['frenzy','dragonflight']},
                        {'buffs':['frenzy'],'magic':20}, {'buffs':[]},
                        {'buffs':['frenzy'],'badForecast':True}]:
            with self.subTest(options=options):
                data = self.run_action('spell', **options)
                self.assertTrue(data['result']['waiting'])
                self.assertEqual(data['events'], [])

    def test_forecast_needs_no_dualcast_tower_level_or_amount(self):
        data = self.run_action('forecast')
        self.assertEqual(data['result']['results'], ['click frenzy'])
        self.assertEqual(data['result']['skipCount'], 0)
        self.assertEqual(data['events'], [])

    def test_snapshot_without_unlocked_minigames_still_allows_farming(self):
        data = self.run_action('snapshot', noMinigames=True)
        self.assertTrue(data['result']['available'])
        self.assertEqual(data['result']['magic'], 0)


if __name__ == '__main__':
    unittest.main()
