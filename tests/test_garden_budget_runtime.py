import json
from pathlib import Path
import shutil
import subprocess
import unittest

from app.bridge.js_bridge import CookieClickerBridge
from app.models.garden import GardenAction


@unittest.skipUnless(shutil.which("node"), "Node.js required for isolated Garden runtime")
class GardenBudgetRuntimeTests(unittest.TestCase):
    def run_layout(self, *, single=False, cleanup_only=False, **options):
        class Capture(CookieClickerBridge):
            def __init__(self):
                pass

            def execute_js(self, code):
                self.script = code
                return []

        bridge = Capture()
        if single:
            bridge.plant_garden_seed("thumbcorn", 1, 0)
        elif cleanup_only:
            bridge.execute_garden_layout((GardenAction("harvest", "weed mutation", x=0, y=0,
                seed_key="bakerWheat", require_mature=False),))
        else:
            bridge.execute_garden_layout((
                GardenAction("harvest", "replace", x=0, y=0, seed_key="bakerWheat", require_mature=False),
                GardenAction("plant", "replace", x=0, y=0, seed_key="thumbcorn"),
                GardenAction("plant", "fill", x=1, y=0, seed_key="thumbcorn"),
            ))
        runtime = Path(__file__).with_name("fixtures").joinpath("garden_budget_runtime.js").read_text(encoding="utf-8")
        source = runtime.replace("OPTIONS", json.dumps(options)) + "\nconst result=" + bridge.script
        source += ";console.log(JSON.stringify({result,events,cookies:Game.cookies,plot:M.plot}));"
        output = subprocess.run([shutil.which("node"), "-e", source], capture_output=True, text=True, check=True)
        return json.loads(output.stdout)

    def test_shortage_preserves_plants_even_when_one_seed_is_affordable(self):
        data = self.run_layout(cookies=300)
        self.assertEqual(data["events"], [])
        self.assertEqual(data["plot"][0][0], [1,10])
        self.assertTrue(data["result"][0]["waiting"])
        self.assertEqual(data["result"][0]["requiredCookies"], 400)
        self.assertEqual(data["result"][0]["availableCookies"], 300)

    def test_funded_layout_clears_and_fills_in_one_call(self):
        data = self.run_layout(cookies=400)
        self.assertTrue(all(item["ok"] for item in data["result"]))
        self.assertEqual(data["events"], [["harvest",0,0],["plant","thumbcorn",0,0],["plant","thumbcorn",1,0]])
        self.assertEqual(data["cookies"], 0)

    def test_live_price_and_balance_are_used_before_any_removal(self):
        for options in ({"cookies":100}, {"cookies":1000,"multiplier":7}):
            with self.subTest(options=options):
                data = self.run_layout(**options)
                self.assertTrue(data["result"][0]["waiting"])
                self.assertEqual(data["events"], [])

    def test_free_seeds_can_be_planted_at_zero_balance(self):
        data = self.run_layout(cookies=0, free=True)
        self.assertEqual(len(data["events"]), 3)
        self.assertTrue(all(item["ok"] for item in data["result"]))

    def test_changed_plot_locked_seed_or_invalid_price_preserves_layout(self):
        for options in ({"changed":True}, {"locked":True}, {"invalidCost":True}):
            with self.subTest(options=options):
                data = self.run_layout(**options)
                self.assertFalse(data["result"][0]["ok"])
                self.assertEqual(data["events"], [])

    def test_cleanup_can_generate_new_plant_without_being_misreported_as_failure(self):
        data = self.run_layout(cleanup_only=True, cookies=0, spawn=True)
        self.assertTrue(data["result"][0]["ok"])
        self.assertEqual(data["plot"][0][0], [2,0])
        self.assertEqual(data["events"], [["harvest",0,0]])

    def test_unexpected_spawn_is_not_harvested_again_to_force_a_replant(self):
        data = self.run_layout(spawn=True)
        self.assertFalse(data["result"][-1]["ok"])
        self.assertEqual(data["plot"][0][0], [2,0])
        self.assertEqual(data["events"], [["harvest",0,0]])

    def test_individual_planting_reports_shortage_as_waiting(self):
        data = self.run_layout(single=True, cookies=0)
        self.assertFalse(data["result"]["ok"])
        self.assertTrue(data["result"]["waiting"])
        self.assertEqual(data["result"]["reason"], "insufficient_funds")
        self.assertEqual(data["events"], [])


if __name__ == "__main__":
    unittest.main()
