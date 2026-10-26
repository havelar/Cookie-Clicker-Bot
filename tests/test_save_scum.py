"""Save scum com bridge falsa: nenhuma importação no jogo real."""
import copy
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from app.core.save_scum import SaveScumAutomation, SaveScumConfig
from app.config.settings import automation_config
from app.core.run import AutomationRunner

class FakeBridge:
    def __init__(self, types=(0,1,2)):
        self.types=list(types)
        self.events=[]
        self.status={'type':0,'started':100,'mature':True,'ready':True,'remainingAutoMs':100000}
        self.restored=True
        self.persisted=True
        self.fail_harvest=False
    def get_sugar_lump_status(self):return dict(self.status)
    def get_sugar_lump_checkpoint(self):return {'save':'checkpoint','seed':'test','status':dict(self.status)}
    def restore_sugar_lump_checkpoint(self,checkpoint):
        self.events.append('restore')
        if not self.restored:return {'ok':False,'message':'restore failed'}
        self.status=dict(checkpoint['status']);return {'ok':True}
    def harvest_sugar_lump_result(self,**kwargs):
        self.events.append(('harvest',kwargs))
        if self.fail_harvest:raise RuntimeError('bridge failed after click')
        self.status.update(type=self.types.pop(0),started=1000+len(self.events))
        return {'ok':True,'newType':self.status['type'],'newStart':self.status['started']}
    def persist_game_save(self):self.events.append('persist');return self.persisted

class SaveScumTests(unittest.TestCase):
    def make(self,bridge=None,**kwargs):
        bridge=bridge or FakeBridge()
        backups=Mock();backups.create_backup.return_value.file_path=Path('initial.txt')
        return SaveScumAutomation(bridge,backups,SaveScumConfig(interval_seconds=0.05,**kwargs)),bridge,backups

    def test_success_exports_once_restores_failed_results_and_saves_target(self):
        bot,bridge,backups=self.make()
        report=bot.executar()
        self.assertEqual(report.state,'alvo encontrado')
        self.assertEqual(report.attempts,3)
        self.assertEqual(bridge.status['type'],2)
        self.assertEqual(bridge.events.count('restore'),2)
        self.assertEqual(bridge.events[-1],'persist')
        self.assertEqual(backups.create_backup.call_count,2)
        calls=[e[1] for e in bridge.events if isinstance(e,tuple)]
        self.assertTrue(all(c['expected_start']==100 for c in calls))
        self.assertIsNone(calls[0]['after_start'])
        self.assertIsNotNone(calls[1]['after_start'])

    def test_limit_rolls_back_final_unwanted_candidate(self):
        bot,bridge,_=self.make(max_attempts=2)
        report=bot.executar()
        self.assertEqual(report.attempts,2)
        self.assertEqual(bridge.status['started'],100)
        self.assertEqual(bridge.events[-1],'restore')
        self.assertTrue(report.safe_to_resume)

    def test_user_stop_restores_before_resuming_automations(self):
        bot,bridge,_=self.make()
        def update(report):
            if report.attempts:bot.parar()
        report=bot.executar(update)
        self.assertEqual(report.attempts,1)
        self.assertEqual(bridge.events[-1],'restore')
        self.assertEqual(bridge.status['started'],100)

    def test_no_action_without_ready_checkpoint_backup_or_targets(self):
        for case in ('young','near_auto','already_target','backup_failed','no_targets'):
            with self.subTest(case=case):
                bot,bridge,backups=self.make(targets=() if case=='no_targets' else (2,4))
                if case=='young':bridge.status['mature']=False
                if case=='near_auto':bridge.status['remainingAutoMs']=100
                if case=='already_target':bridge.status['type']=4
                if case=='backup_failed':backups.create_backup.side_effect=OSError('disk failed')
                bot.executar()
                self.assertEqual(bridge.events,[])

    def test_transport_error_restores_even_when_click_confirmation_is_lost(self):
        bot,bridge,_=self.make();bridge.fail_harvest=True
        report=bot.executar()
        self.assertEqual(report.state,'erro')
        self.assertEqual(bridge.events[-1],'restore')
        self.assertTrue(report.safe_to_resume)

    def test_restore_failure_keeps_exclusivity_until_recovery(self):
        bot,bridge,_=self.make(max_attempts=1);bridge.restored=False
        report=bot.executar()
        self.assertFalse(report.safe_to_resume)
        self.assertEqual(report.state,'restauração pendente')
        bridge.restored=True
        self.assertTrue(bot.recuperar().safe_to_resume)
        self.assertEqual(bridge.status['started'],100)

    def test_persist_failure_rolls_back_target(self):
        bot,bridge,_=self.make(FakeBridge((2,)));bridge.persisted=False
        report=bot.executar()
        self.assertEqual(report.state,'erro')
        self.assertEqual(bridge.status['type'],0)

    def test_preview_never_exports_or_harvests(self):
        bot,bridge,backups=self.make()
        self.assertEqual(bot.gerar_previa().state,'pronto')
        self.assertEqual(bridge.events,[])
        backups.create_backup.assert_not_called()
