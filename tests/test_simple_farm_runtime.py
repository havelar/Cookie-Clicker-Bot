import json
from pathlib import Path
import shutil
import subprocess
import unittest

from app.bridge.js_bridge import CookieClickerBridge


@unittest.skipUnless(shutil.which('node'), 'Node.js required for isolated runtime')
class SimpleFarmRuntimeTests(unittest.TestCase):
    def run_action(self, action='reinvest', *, floor=80000, spent=0, **options):
        class Capture(CookieClickerBridge):
            def __init__(self):
                pass

            def execute_js(self, code):
                self.script = code
                return {'ok': True}

        bridge = Capture()
        if action == 'spell':
            bridge.execute_simple_farm_spell(expected_cast=10, minimum_buff_seconds=8, cash_floor=floor, spent_in_window=spent)
        elif action == 'forecast':
            bridge.forecast_simple_farm_spell(2, cash_floor=floor, spent_in_window=spent)
        elif action == 'snapshot':
            bridge.get_combo_snapshot(require_minigames=False)
        else:
            bridge.reinvest_simple_farm(floor, .05, .8)
        runtime = Path(__file__).with_name('fixtures').joinpath('simple_farm_runtime.js').read_text(encoding='utf-8')
        source = runtime.replace('OPTIONS', json.dumps(options)) + '\nconst result=' + bridge.script
        source += ';console.log(JSON.stringify({result,events,cookies:Game.cookies,lumps:Game.lumps,buyMode:Game.buyMode,towers:Game.Objects["Wizard tower"]?.amount,shimmers:Game.shimmers.length,pantheon:Game.Objects.Temple?.minigame.slot}));'
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

    def test_dual_cast_restores_towers_before_opening_and_preserves_reserve(self):
        for level, towers, aura in [(1, 321, 0), (10, 501, 0), (11, 726, 1)]:
            with self.subTest(level=level, towers=towers, aura=aura):
                data = self.run_action('spell', dualRuntime=True, buffs=['frenzy'],
                                       level=level, towers=towers, aura=aura)
                self.assertTrue(data['result']['ok'], data)
                self.assertTrue(data['result']['dualcast'])
                self.assertEqual(data['result']['casts'], 2)
                self.assertEqual(data['towers'], towers)
                self.assertEqual([e[0] for e in data['events']], ['cast', 'sell', 'cast', 'rebuy', 'pop', 'pop'])
                self.assertTrue(all(e[2] == towers for e in data['events'] if e[0] == 'pop'))
                self.assertGreaterEqual(data['cookies'], 95000)
                self.assertLessEqual(data['result']['rebuy'], 5000)
                self.assertEqual(data['lumps'], 10)
                self.assertEqual(data['buyMode'], -1)
                self.assertEqual(data['pantheon'], [8, 6, 10])
                self.assertEqual(data['shimmers'], 0)

    def test_forecast_selects_complementary_pair_in_both_orders_without_mutation(self):
        for effects in [['click frenzy', 'building special'], ['building special', 'click frenzy'],
                        ['blood frenzy', 'click frenzy'], ['click frenzy', 'blood frenzy']]:
            data = self.run_action('forecast', dualRuntime=True, effects=effects)
            self.assertEqual(data['result']['results'], effects)
            self.assertEqual(data['events'], [])
            self.assertEqual(data['towers'], 400)
            self.assertEqual(data['cookies'], 100000)
            self.assertLess(data['result']['dual']['targetTowers'], 400)
            cast = self.run_action('spell', dualRuntime=True, effects=effects, buffs=['frenzy'])
            self.assertTrue(cast['result']['dualcast'])
            self.assertTrue(cast['result']['ok'], cast)

    def test_unaffordable_or_redundant_pair_falls_back_to_single_without_sales(self):
        cases = [dict(basePrice=500), dict(cookies=79000), dict(cps=16.5),
                 dict(effects=['click frenzy', 'click frenzy']),
                 dict(effects=['click frenzy', 'frenzy']), dict(towers=30),
                 dict(formulaMismatch=True)]
        for options in cases:
            with self.subTest(options=options):
                data = self.run_action('spell', dualRuntime=True, buffs=['frenzy'], **options)
                self.assertTrue(data['result']['ok'], data)
                self.assertFalse(data['result']['dualcast'])
                self.assertEqual(data['result']['casts'], 1)
                self.assertEqual([e[0] for e in data['events']], ['cast', 'pop'])

    def test_recent_store_spending_does_not_block_dual_cast_that_preserves_reserve(self):
        data = self.run_action('spell', dualRuntime=True, buffs=['frenzy'], spent=4900)

        self.assertTrue(data['result']['ok'], data)
        self.assertTrue(data['result']['dualcast'])
        self.assertGreaterEqual(data['cookies'], data['result']['reserve'])

    def test_complementary_frenzy_only_when_natural_buff_is_different(self):
        data = self.run_action('spell', dualRuntime=True, buffs=['dragon harvest'],
                               effects=['click frenzy', 'frenzy'])
        self.assertTrue(data['result']['dualcast'])
        self.assertTrue(data['result']['ok'])

    def test_second_cast_failure_or_divergence_still_restores_towers(self):
        for options in [dict(rejectSecond=True), dict(wrongSecond=True), dict(partialSale=True)]:
            with self.subTest(options=options):
                data = self.run_action('spell', dualRuntime=True, buffs=['frenzy'], **options)
                self.assertFalse(data['result']['ok'])
                self.assertFalse(data['result']['waiting'])
                self.assertEqual(data['towers'], 400)
                self.assertEqual(data['buyMode'], -1)
                self.assertEqual(data['lumps'], 10)
                self.assertIn('rebuy', [e[0] for e in data['events']])
                self.assertNotIn('pop', [e[0] for e in data['events']])

    def test_rebuy_failure_is_reported_without_opening_cookies_or_hiding_error(self):
        data = self.run_action('spell', dualRuntime=True, buffs=['frenzy'], failRebuy=True)
        self.assertFalse(data['result']['ok'])
        self.assertFalse(data['result']['waiting'])
        self.assertIn('rebuy failure', data['result']['message'])
        self.assertEqual(data['buyMode'], -1)
        self.assertNotIn('pop', [e[0] for e in data['events']])

    def test_dual_waits_for_buff_mana_and_empty_screen(self):
        for options in [dict(buffs=[]), dict(buffs=['frenzy', 'click frenzy']),
                        dict(buffs=['frenzy'], magic=50), dict(buffs=['frenzy'], existingShimmer=True)]:
            data = self.run_action('spell', dualRuntime=True, **options)
            self.assertTrue(data['result']['waiting'])
            self.assertEqual(data['events'], [])

    def test_new_live_price_or_balance_prevents_support_first_pair_from_spending(self):
        forecast = self.run_action('forecast', dualRuntime=True, effects=['building special', 'click frenzy'])
        self.assertEqual(len(forecast['result']['results']), 2)
        for options in [dict(cookies=79000), dict(priceMultiplier=10)]:
            data = self.run_action('spell', dualRuntime=True, buffs=['frenzy'],
                                   effects=['building special', 'click frenzy'], **options)
            self.assertTrue(data['result']['waiting'])
            self.assertEqual(data['events'], [])

    def test_season_and_second_cookie_backfire_are_considered(self):
        for season in ['valentines', 'easter']:
            data = self.run_action('spell', dualRuntime=True, buffs=['frenzy'], season=season)
            self.assertTrue(data['result']['ok'])
            self.assertTrue(data['result']['dualcast'])
        # .8 succeeds at 15% fail but fails at 30% with the first cookie on screen.
        data = self.run_action('forecast', dualRuntime=True, successRoll=.8)
        self.assertEqual(data['result']['results'], ['click frenzy'])

    def test_snapshot_without_unlocked_minigames_still_allows_farming(self):
        data = self.run_action('snapshot', noMinigames=True)
        self.assertTrue(data['result']['available'])
        self.assertEqual(data['result']['magic'], 0)


if __name__ == '__main__':
    unittest.main()
