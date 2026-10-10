"""Regra de colheita comum e preservação de Sugar Lumps."""
import copy
import unittest
from unittest.mock import Mock
from app.config.settings import automation_config
from app.core.run import AutomationRunner

class SugarHarvestRuleTests(unittest.TestCase):
    def setUp(self):
        self.previous=copy.deepcopy(automation_config.__dict__)
        self.addCleanup(lambda:automation_config.__dict__.update(self.previous))
        automation_config.enable_sugar_lump_harvest=True
        self.runner=AutomationRunner.__new__(AutomationRunner)
        self.runner.bridge=Mock()
        self.runner.sugar_lumps_harvested=0
        self.runner.bridge.harvest_sugar_lump.return_value=True
    def test_normal_collects_at_maturity_and_passes_live_preservation_guards(self):
        self.runner.bridge.get_sugar_lump_status.return_value={'type':0,'mature':True,'ready':False}
        self.assertTrue(self.runner._run_sugar_lump_cycle())
        self.assertEqual(self.runner.sugar_lumps_harvested,1)
        self.assertIn(2,self.runner.bridge.harvest_sugar_lump.call_args.kwargs['preserved_types'])
    def test_golden_and_caramelized_wait_until_ripe(self):
        for t in (2,4):
            self.runner.bridge.get_sugar_lump_status.return_value={'type':t,'mature':True,'ready':False}
            self.assertFalse(self.runner._run_sugar_lump_cycle())
        self.runner.bridge.harvest_sugar_lump.assert_not_called()
        self.runner.bridge.get_sugar_lump_status.return_value={'type':2,'mature':True,'ready':True}
        self.assertTrue(self.runner._run_sugar_lump_cycle())
    def test_disabled_young_and_missing_status_never_collect(self):
        for status in (None,{'type':0,'mature':False}, {'type':0,'mature':True,'overripe':True}):
            self.runner.bridge.get_sugar_lump_status.return_value=status
            self.assertFalse(self.runner._run_sugar_lump_cycle())
        automation_config.enable_sugar_lump_harvest=False
        self.runner.bridge.get_sugar_lump_status.return_value={'type':0,'mature':True}
        self.assertFalse(self.runner._run_sugar_lump_cycle())
        self.runner.bridge.harvest_sugar_lump.assert_not_called()
