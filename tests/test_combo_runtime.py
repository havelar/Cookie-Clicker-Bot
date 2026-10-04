"""Executa o script Quadcast gerado contra um modelo JavaScript descartável."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from app.bridge.js_bridge import CookieClickerBridge


@unittest.skipUnless(shutil.which("node"), "Node.js necessário para o runtime isolado")
class ComboRuntimeTests(unittest.TestCase):
    def run_combo(self, **options):
        class Capture(CookieClickerBridge):
            def __init__(self):
                pass

            def execute_js(self, code):
                self.script = code
                return {"ok": True}

        bridge = Capture()
        bridge.execute_combo_quadcast(
            expected_cast=10,
            expected_results=['blood frenzy', 'click frenzy', 'frenzy', 'building special'],
            minimum_buff_seconds=12, required_natural_bs=1,
            use_sugar_frenzy=True, use_loans=True,
        )
        script = bridge.script
        runtime = Path(__file__).with_name('fixtures').joinpath('combo_runtime.js').read_text(encoding='utf-8')
        runtime = runtime.replace('OPTIONS', json.dumps(options))
        result = subprocess.run([shutil.which('node'), '-e', runtime + '\nconst result=' + script +
                                 ';console.log(JSON.stringify({result,events,lumps:Game.lumps,askLumps:Game.prefs.askLumps}));'],
                                capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def test_full_combo_protects_both_buildings_and_leaves_redundant_frenzy(self):
        data = self.run_combo()
        self.assertTrue(data['result']['ok'])
        self.assertEqual(data['result']['clickSeconds'], 9)
        self.assertEqual(data['lumps'], 8)
        self.assertTrue(data['result']['sugarFrenzy'])
        self.assertEqual(data['askLumps'], 1)
        self.assertEqual(data['result']['preserved'], [{'id': 2, 'force': 'frenzy'}])
        self.assertFalse(any(e[0] == 'sell' and e[1] in [6, 9] for e in data['events']))

    def test_missing_frenzy_activates_spell_frenzy(self):
        data = self.run_combo(noFrenzy=True)
        self.assertTrue(data['result']['ok'])
        self.assertIn(['pop', 'frenzy'], data['events'])
        self.assertEqual(data['result']['preserved'], [])

    def test_duplicate_bs_preserves_sugar_and_loans_after_partial_cast(self):
        data = self.run_combo(duplicate=True)
        self.assertFalse(data['result']['ok'])
        self.assertEqual(data['result']['lumpsSpent'], 1)
        self.assertEqual(data['lumps'], 9)
        self.assertFalse(any(e[0] in ['sugar', 'loan'] for e in data['events']))

    def test_expiring_or_negative_buff_has_no_side_effects(self):
        for options in ({'naturalTime': 11}, {'negative': 'cursed finger'}):
            with self.subTest(options=options):
                data = self.run_combo(**options)
                self.assertTrue(data['result']['retryable'])
                self.assertEqual(data['events'], [])
                self.assertEqual(data['lumps'], 10)

    def test_existing_godzamok_shortens_the_actual_window(self):
        data = self.run_combo(devastationTime=4)
        self.assertTrue(data['result']['ok'])
        self.assertEqual(data['result']['clickSeconds'], 3)

    def test_sugar_failure_is_reported_without_refunding_or_repeating(self):
        data = self.run_combo(sugarMissingBuff=True)
        self.assertFalse(data['result']['ok'])
        self.assertEqual(data['result']['lumpsSpent'], 2)
        self.assertEqual(data['lumps'], 8)
        self.assertEqual(data['askLumps'], 1)
        self.assertEqual(data['events'].count(['sugar']), 1)
        self.assertFalse(any(e[0] == 'loan' for e in data['events']))

    def test_loan_interest_blocks_before_any_cast(self):
        data = self.run_combo(loanInterest=True)
        self.assertTrue(data['result']['retryable'])
        self.assertEqual(data['events'], [])


if __name__ == '__main__':
    unittest.main()
