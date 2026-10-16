"""Renovação de temporadas sem acessar o jogo ou configurações reais."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication
from app.bridge.js_bridge import CookieClickerBridge
from app.bridge.season_scripts import AUTO_SEASON_SCRIPT
from app.config.settings import automation_config, load_automation_settings, save_automation_settings
from app.core.run import AutomationRunner
from app.core.seasons import SEASONS
from app.ui.main_window import MainWindow

DRIVER = r"""
const fs=require('fs'), data=JSON.parse(fs.readFileSync(0,'utf8'));
let buys=0;
const G=globalThis.Game={ready:true,season:data.current??'',seasonT:data.time??0,fps:30,
 cookies:data.cookies??100,OnAscend:!!data.ascending,promptOn:!!data.prompt,
 Has:name=>!data.locked,seasons:{},Upgrades:{}};
for(const season of ['christmas','halloween','valentines','fools','easter']) {
 G.seasons[season]={trigger:season};
 G.Upgrades[season]={unlocked:!data.unavailable,bought:0,getPrice:()=>data.invalid?NaN:100,
 buy(){buys++;if(!data.fail){G.cookies-=100;G.season=season;G.seasonT=2592000;this.bought=1;}}};
}
const run=()=>eval(data.script), results=[run()];
if(data.repeat) results.push(run());
if(data.expire){G.season='';G.seasonT=-1;G.cookies=100;G.Upgrades[data.target].bought=0;results.push(run());}
console.log(JSON.stringify({results,buys,season:G.season,cookies:G.cookies,refresh:G.storeToRefresh}));
"""


class TemporadasRuntimeTests(unittest.TestCase):
    def execute(self, target="christmas", **values):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node necessário para testar o JavaScript das temporadas")
        values.update(target=target, script=AUTO_SEASON_SCRIPT.replace("__SEASON__", json.dumps(target)))
        result = subprocess.run([node, "-e", DRIVER], input=json.dumps(values), text=True,
                                capture_output=True, cwd=Path(__file__).resolve().parents[1], timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_ativa_cada_temporada_uma_vez_e_atualiza_loja(self):
        for season in SEASONS:
            with self.subTest(temporada=season):
                value = self.execute(target=season, repeat=True)
                self.assertEqual(value["season"], season)
                self.assertEqual(value["buys"], 1)
                self.assertEqual(value["cookies"], 0)
                self.assertEqual(value["refresh"], 1)
                self.assertEqual([r["reason"] for r in value["results"]], ["activated", "active"])

    def test_renova_apos_vencimento(self):
        value = self.execute(expire=True)
        self.assertEqual(value["buys"], 2)
        self.assertEqual([r["reason"] for r in value["results"]], ["activated", "activated"])

    def test_temporada_ativa_nunca_compra_inclusive_natural_ou_eterna(self):
        for time in (-1, 30, 2592000):
            value = self.execute(current="christmas", time=time)
            self.assertEqual(value["buys"], 0)
            self.assertEqual(value["results"][0]["reason"], "active")
        self.assertEqual(self.execute(current="christmas", time=30)["results"][0]["retryAfterMs"], 1100)

    def test_requisitos_saldo_e_confirmacoes_impedem_compra(self):
        for params, reason in (({"locked": True}, "locked"), ({"unavailable": True}, "unavailable"),
                               ({"cookies": 99}, "funds"), ({"prompt": True}, "busy"),
                               ({"ascending": True}, "busy"), ({"invalid": True}, "unavailable")):
            with self.subTest(condicao=params):
                value = self.execute(**params)
                self.assertEqual(value["buys"], 0)
                self.assertEqual(value["results"][0]["reason"], reason)

    def test_troca_temporada_diferente_e_confirma_falha(self):
        self.assertEqual(self.execute(current="easter")["season"], "christmas")
        value = self.execute(fail=True)
        self.assertEqual(value["results"][0]["reason"], "failed")
        self.assertEqual(value["cookies"], 100)


class TemporadasIntegracaoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        previous = copy.deepcopy(automation_config.__dict__)
        self.addCleanup(lambda: automation_config.__dict__.update(previous))
        automation_config.enable_auto_season = True
        automation_config.auto_season = "christmas"
        with patch("app.core.run.InputHandler"):
            self.runner = AutomationRunner(123, Mock())
        self.runner.bridge.maintain_season.return_value = {"reason": "active", "retryAfterMs": 60000}

    def test_agendamento_leve_e_reset_ao_retomar(self):
        self.runner._run_season_cycle(now=0)
        self.runner._run_season_cycle(now=59)
        self.runner.bridge.maintain_season.assert_called_once_with("christmas")
        self.runner._run_season_cycle(now=60)
        self.assertEqual(self.runner.bridge.maintain_season.call_count, 2)
        self.runner.set_paused(True)
        self.runner.set_paused(False)
        self.runner._run_season_cycle(now=61)
        self.assertEqual(self.runner.bridge.maintain_season.call_count, 3)

    def test_pausa_exclusividade_desligamento_e_parada(self):
        self.runner.set_paused(True)
        self.runner._run_season_cycle(now=0)
        self.runner.set_paused(False)
        self.runner.acquire_exclusive("combo")
        self.runner._run_season_cycle(now=1)
        self.runner.release_exclusive("combo")
        automation_config.enable_auto_season = False
        self.runner._run_season_cycle(now=2)
        automation_config.enable_auto_season = True
        self.runner.stop_event.set()
        self.runner._run_season_cycle(now=3)
        self.runner.bridge.maintain_season.assert_not_called()

    def test_funciona_junto_com_simple_farm_e_detector(self):
        self.runner._simple_farm_active = True
        self.runner._run_detector_cycle()
        self.runner.bridge.maintain_season.assert_called_once_with("christmas")

    def test_logs_nao_repetem_espera_por_saldo(self):
        self.runner.bridge.maintain_season.return_value = {"reason": "funds", "retryAfterMs": 10000}
        with patch("app.core.run.logger.info") as log:
            for now in (0, 10, 20):
                self.runner._run_season_cycle(now=now)
            log.assert_called_once()

    def test_restaurar_backup_reavalia_temporada_sem_aguardar_timer_antigo(self):
        self.runner._run_season_cycle(now=0)
        self.assertTrue(self.runner.acquire_exclusive("backup_restore"))
        self.runner.release_exclusive("backup_restore")
        self.runner._run_season_cycle(now=1)
        self.assertEqual(self.runner.bridge.maintain_season.call_count, 2)

    def test_bridge_rejeita_selecao_invalida_e_resposta_invalida(self):
        bridge = CookieClickerBridge()
        with patch.object(bridge, "_execute_game_action", return_value=None) as execute:
            self.assertEqual(bridge.maintain_season("invalida")["reason"], "invalid")
            execute.assert_not_called()
            self.assertEqual(bridge.maintain_season("christmas")["reason"], "unavailable")

    def test_checkbox_dropdown_e_persistencia_sem_gravar_configuracao_real(self):
        values = {}
        class Settings:
            def __init__(self, *args): pass
            def beginGroup(self, *args): pass
            def endGroup(self): pass
            def sync(self): pass
            def setValue(self, key, value): values[key] = value
            def value(self, key, default=None, type=None): return values.get(key, default)
        with patch("app.config.settings.QSettings", Settings), patch("app.ui.main_window.save_automation_settings"), patch("app.ui.main_window.QTimer.singleShot"):
            load_automation_settings()
            self.assertFalse(automation_config.enable_auto_season)
            window = MainWindow()
            try:
                self.assertTrue(window.tabs.widget(0).isAncestorOf(window.auto_season_checkbox))
                window.runner = self.runner
                window.auto_season_checkbox.setChecked(True)
                window.auto_season_combo.setCurrentIndex(window.auto_season_combo.findData("fools"))
                self.assertEqual(automation_config.auto_season, "fools")
                self.assertEqual(self.runner._next_season_check, 0)
                save_automation_settings()
                automation_config.auto_season = "easter"
                automation_config.enable_auto_season = False
                load_automation_settings()
                self.assertTrue(automation_config.enable_auto_season)
                self.assertEqual(automation_config.auto_season, "fools")
                values["auto_season"] = "invalida"
                load_automation_settings()
                self.assertEqual(automation_config.auto_season, "christmas")
            finally:
                window.close()
