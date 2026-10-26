"""Meta, seleção, cache, recursos e preservação do Garden no Combo avançado."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication
from app.bridge.js_bridge import CookieClickerBridge
from app.config.settings import automation_config, load_automation_settings, save_automation_settings
from app.core.combo import ComboAutomation
from app.core.combo_planning import choose, estimate
from app.models.combo import ConfiguracaoCombo, EstadoCombo
from app.models.garden import GardenPlant
from app.ui.main_window import MainWindow
from tests.test_combo import FakeComboBridge, combo_snapshot, ready_buffs, empty_garden, full_garden
from tests import test_combo_runtime as runtime_tests

ROOT = Path(__file__).resolve().parents[1]


class RevisaoComboTests(unittest.TestCase):
    def test_conquista_historica_nao_encerra_farm(self):
        bridge = FakeComboBridge([combo_snapshot(achievementWon=True)])
        result = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()
        self.assertFalse(result.terminal)

    def test_saldo_alto_nao_encerra_farm(self):
        bridge = FakeComboBridge([combo_snapshot(cookies=1e100, cookiesEarned=1e100)])
        self.assertFalse(ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo().terminal)

    def test_fim_dos_cliques_recomeca_mesmo_com_conquista_e_saldo_alto(self):
        bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs())])
        now = [0]
        automation = ComboAutomation(bridge, ConfiguracaoCombo(), relogio=lambda: now[0])
        self.assertEqual(automation.executar_passo().estado, EstadoCombo.CLICANDO)
        bridge.snapshots[0] = combo_snapshot(achievementWon=True, cookiesEarned=1e73, cookies=1e60)
        now[0] = 10
        self.assertEqual(automation.executar_passo().estado, EstadoCombo.PREPARANDO)

    def test_cache_mantem_sequencia_e_invalida_quando_muda_a_falha(self):
        bridge = FakeComboBridge()
        bridge.forecast.update(startCast=20, skipCount=10)
        automation = ComboAutomation(bridge, ConfiguracaoCombo())
        snapshot = combo_snapshot(fthofFailBase=.15)
        first = automation._planejar(snapshot)
        second = automation._planejar(dict(snapshot, spellsCastTotal=11, magic=30))
        self.assertEqual(first.cast_inicial, second.cast_inicial)
        self.assertEqual(second.spells_a_pular, 9)
        self.assertEqual(sum(c[0] == 'forecast' for c in bridge.calls), 1)
        automation._planejar(dict(snapshot, fthofFailBase=.015))
        self.assertEqual(sum(c[0] == 'forecast' for c in bridge.calls), 2)

    def test_lavoura_atual_e_descobertas_sao_preservadas_por_padrao(self):
        for key, unlocked, allowed in (('ichorpuff', True, False), ('desconhecida', False, True),
                                        ('queenbeetLump', False, True)):
            bridge = FakeComboBridge()
            garden = empty_garden()
            plant = GardenPlant(0, 0, 50, key, key, 60, 50, True)
            bridge.garden = replace(garden, plants=(plant,))
            automation = ComboAutomation(bridge, ConfiguracaoCombo(permitir_converter_garden=allowed))
            automation.executar_passo()
            actions = [a for c in bridge.calls if c[0] == 'layout' for a in c[1]]
            self.assertFalse(any(a.x == 0 and a.y == 0 for a in actions))

    def test_conversao_autorizada_usa_lote_e_canteiro_otimizado(self):
        bridge = FakeComboBridge()
        bridge.garden = replace(full_garden(), plants=(), soil_key="fertilizer")
        automation = ComboAutomation(bridge, ConfiguracaoCombo(permitir_converter_garden=True))
        automation.executar_passo()
        actions = next(c[1] for c in bridge.calls if c[0] == 'layout')
        self.assertEqual(sum(a.seed_key == 'nursetulip' for a in actions), 18)
        self.assertEqual(sum(a.seed_key == 'goldenClover' for a in actions), 18)

    def test_mesmo_tick_nao_executa_outro_lote_e_nao_consulta_a_cada_ciclo(self):
        bridge = FakeComboBridge()
        bridge.garden = replace(empty_garden(), next_tick_at=123)
        now = [0]
        automation = ComboAutomation(bridge, ConfiguracaoCombo(permitir_converter_garden=True), relogio=lambda: now[0])
        automation.executar_passo()
        automation.executar_passo()
        now[0] = 11
        automation.executar_passo()
        self.assertEqual(sum(c[0] == 'layout' for c in bridge.calls), 1)
        self.assertEqual(sum(c[0] == 'garden' for c in bridge.calls), 2)

    def test_reserva_lumps_para_tentativa_final(self):
        bridge = FakeComboBridge([combo_snapshot(magic=0, lumps=2)])
        bridge.forecast.update(startCast=20, skipCount=10)
        ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()
        self.assertFalse(any(c[0] == 'refill' for c in bridge.calls))

    def test_preparo_da_pilha_nao_consume_prazo_da_busca_armada(self):
        bridge = FakeComboBridge()
        now = [0]
        automation = ComboAutomation(bridge, ConfiguracaoCombo(), relogio=lambda: now[0])
        bridge.snapshots[0]['magic'] = 0
        automation.executar_passo()
        now[0] = 300
        bridge.snapshots[0]['magic'] = 100
        automation.executar_passo()
        self.assertEqual(automation._inicio_espera, 300)

    def test_ganho_estimado_baixo_nao_bloqueia_farm(self):
        bridge = FakeComboBridge([combo_snapshot(mouseCps=1, buffs=ready_buffs())])
        self.assertEqual(ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo().estado, EstadoCombo.CLICANDO)

    def test_selecao_compara_ganho_por_tempo(self):
        bridge = FakeComboBridge()
        first = dict(bridge.forecast, startCast=15, skipCount=5)
        later = dict(first, startCast=300, skipCount=290, spellBuildingSpecials=2, naturalBuildingSpecials=1)
        config = ConfiguracaoCombo()
        snapshot = combo_snapshot(mouseCps=1e20)
        self.assertEqual(choose([later, first], snapshot, config)['startCast'], 15)
        self.assertIsNone(estimate(first, combo_snapshot(), config)['estimatedGain'])

    def test_busca_nova_nao_modifica_rng_e_confere_com_funcoes_originais(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node necessário para validar a busca isolada')
        bridge = CookieClickerBridge()
        with patch.object(bridge, 'execute_js', return_value={'ok': True}) as execute:
            bridge.forecast_combo_candidates(5000, 2)
            script = execute.call_args.args[0]
        for season in ('christmas', 'valentines'):
            process = subprocess.run([node, str(ROOT/'tests/fixtures/planner_runtime.js')],
                                     input=json.dumps({'script': script, 'season': season}),
                                     text=True, capture_output=True, cwd=ROOT, timeout=15)
            self.assertEqual(process.returncode, 0, process.stderr)
            value = json.loads(process.stdout)
            self.assertTrue(value['unchanged'])
            self.assertEqual(value['mismatches'], [])
            self.assertEqual({c['season'] for c in value['result']['candidates']}, {'christmas', 'valentines'})


class GardenFinalTests(unittest.TestCase):
    def test_remove_apenas_tulipas_de_canteiro_exclusivo_de_coleta(self):
        runtime = runtime_tests.ComboRuntimeTests()
        for options, count in (({'garden':['goldenClover','nursetulip']}, 1),
                                ({'garden':['ichorpuff','nursetulip']}, 0),
                                ({'garden':['desconhecida','nursetulip']}, 0),
                                ({'garden':['goldenClover','nursetulip'], 'lockedTulip':True}, 0),
                                ({'garden':['goldenClover','nursetulip'], 'frozen':True}, 0),
                                ({'garden':['goldenClover','nursetulip'], 'optimizeGarden':False}, 0)):
            with self.subTest(condicoes=options):
                value = runtime.run_combo(**options)
                self.assertTrue(value['result']['ok'])
                removed = [e for e in value['events'] if e[0] == 'gardenHarvest']
                self.assertEqual(len(removed), count)
                if removed:
                    self.assertEqual(removed, [['gardenHarvest', 1, 0]])
                    self.assertLess(value['events'].index(removed[0]), value['events'].index(['pop','blood frenzy']))


class ConfiguracaoRevisadaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_configuracao_simplificada_persiste_limites_e_garden(self):
        previous = copy.deepcopy(automation_config.__dict__)
        self.addCleanup(lambda: automation_config.__dict__.update(previous))
        values = {}
        class Settings:
            def __init__(self,*args): pass
            def beginGroup(self,*args): pass
            def endGroup(self): pass
            def sync(self): pass
            def value(self,key,default=None,type=None): return values.get(key,default)
            def setValue(self,key,value): values[key]=value
        with patch('app.config.settings.QSettings',Settings), patch('app.ui.main_window.QTimer.singleShot'):
            window = MainWindow()
            try:
                window.combo_lumps_input.setValue(7)
                window.combo_reserve_input.setValue(85)
                window.combo_garden_checkbox.setChecked(True)
                window._save_combo_settings()
                config = window._combo_configuration()
                self.assertEqual(config.maximo_lumps_total, 7)
                self.assertTrue(config.permitir_converter_garden)
                self.assertEqual(config.reserva_caixa_percentual, 85)
                save_automation_settings()
                automation_config.combo_cash_reserve_percent = 0
                load_automation_settings()
                self.assertEqual(automation_config.combo_cash_reserve_percent, 85)
                self.assertFalse(hasattr(window, 'combo_target_input'))
                self.assertFalse(window.combo_advanced_group.isChecked())
                self.assertTrue(window.combo_advanced_body.isHidden())
            finally:
                window.close()
