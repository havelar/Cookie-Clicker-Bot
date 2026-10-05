"""Verifica o estado aplicado e sua representação ingame no mesmo script."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from app.bridge.js_bridge import CookieClickerBridge


@unittest.skipUnless(shutil.which("node"), "Node.js necessário para o runtime isolado")
class VisualSyncRuntimeTests(unittest.TestCase):
    def run_action(self, action="soil", **options):
        class Capture(CookieClickerBridge):
            def __init__(self):
                pass

            def execute_js(self, code):
                self.script = code
                return {"ok": True}

        bridge = Capture()
        if action == "soil":
            bridge.change_garden_soil("fertilizer")
        elif action == "unfreeze":
            bridge.set_garden_frozen(False)
        elif action == "pantheon":
            bridge.configure_combo_pantheon([1, 0, 2])
        elif action == "auras":
            bridge.set_combo_auras(2, 3)
        elif action == "partial":
            bridge._execute_game_action("(() => { Game.Objects.Farm.minigame.soil=1; return {ok:false}; })()")
        elif action == "plot":
            bridge._execute_game_action("(() => { Game.Objects.Farm.minigame.toRebuild=true; return {ok:true}; })()")
        elif action == "store":
            bridge._execute_game_action("(() => { Game.storeToRefresh=1; Game.upgradesToRebuild=1; return {ok:true}; })()")
        runtime = Path(__file__).with_name("fixtures").joinpath("visual_sync_runtime.js").read_text(encoding="utf-8")
        # brokenUI is enabled after constructing the initial DOM.
        initial = dict(options, brokenUI=False)
        source = runtime.replace("OPTIONS", json.dumps(initial))
        if options.get("brokenUI"):
            source += "\noptions.brokenUI=true;"
        source += "\nconst result=" + bridge.script + ";"
        source += """
        console.log(JSON.stringify({result,events,soil:garden.soil,nextSoil:garden.nextSoil,
            soilOn:[0,1].map(i=>nodes['gardenSoil-'+i].classList.contains('on')),
            frozen:garden.freeze,freezeOn:nodes['gardenTool-1'].classList.contains('on'),
            frozenStyle:nodes.gardenContent.classList.contains('gardenFrozen'),
            slots:temple.slot,swaps:temple.swaps,
            parents:[0,1,2].map(i=>nodes['templeGod'+i].parentNode.id)}));
        """
        output = subprocess.run([shutil.which("node"), "-e", source], capture_output=True, text=True, check=True)
        return json.loads(output.stdout)

    def test_soil_changes_highlight_and_cooldown_once(self):
        data = self.run_action()
        self.assertTrue(data["result"]["ok"])
        self.assertEqual(data["soil"], 1)
        self.assertEqual(data["soilOn"], [False, True])
        self.assertEqual(data["events"].count("step"), 1)
        self.assertGreater(data["nextSoil"], 0)

    def test_cooldown_and_frozen_rejections_keep_old_highlight(self):
        for options in ({"cooldown": True}, {"frozen": True}):
            data = self.run_action(**options)
            self.assertFalse(data["result"]["ok"])
            self.assertEqual(data["soil"], 0)
            self.assertEqual(data["soilOn"], [True, False])
            self.assertNotIn("step", data["events"])

    def test_unfreeze_updates_button_and_frost_overlay(self):
        data = self.run_action("unfreeze", frozen=True)
        self.assertTrue(data["result"]["ok"])
        self.assertFalse(data["frozen"])
        self.assertFalse(data["freezeOn"])
        self.assertFalse(data["frozenStyle"])

    def test_pantheon_moves_both_swapped_spirits_with_one_swap(self):
        data = self.run_action("pantheon")
        self.assertTrue(data["result"]["ok"])
        self.assertEqual(data["parents"], ["templeSlot1", "templeSlot0", "templeSlot2"])
        self.assertEqual(data["slots"], [1, 0, 2])
        self.assertEqual(data["swaps"], 2)
        self.assertEqual(data["events"].count("swap"), 1)

    def test_auras_refresh_open_menu_but_do_not_open_closed_menu(self):
        self.assertIn("dragonMenu", self.run_action("auras")["events"])
        self.assertNotIn("dragonMenu", self.run_action("auras", closedDragon=True)["events"])

    def test_partial_action_updates_applied_state_without_retry(self):
        data = self.run_action("partial")
        self.assertFalse(data["result"]["ok"])
        self.assertEqual(data["soilOn"], [False, True])
        self.assertNotIn("step", data["events"])

    def test_dirty_plot_and_store_use_native_render_routines(self):
        self.assertEqual(self.run_action("plot")["events"].count("plot"), 1)
        data = self.run_action("store")
        self.assertIn("store", data["events"])
        self.assertIn("upgrades", data["events"])

    def test_hidden_dom_does_not_block_action(self):
        data = self.run_action(noDOM=True)
        self.assertTrue(data["result"]["ok"])
        self.assertEqual(data["soil"], 1)

    def test_visual_failure_reports_warning_without_repeating_action(self):
        data = self.run_action(brokenUI=True)
        self.assertTrue(data["result"]["ok"])
        self.assertTrue(data["result"]["uiWarnings"])
        self.assertEqual(data["events"].count("step"), 1)
