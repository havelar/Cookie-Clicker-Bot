"""Farm contínuo, orçamento da sessão e compras com saldo protegido."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import Mock, patch

from app.bridge.js_bridge import CookieClickerBridge
from app.core.combo import ComboAutomation
from app.models.combo import ConfiguracaoCombo, EstadoCombo
from tests.test_combo import FakeComboBridge, combo_snapshot, ready_buffs
from tests import test_combo_runtime as combo_runtime
from tests import test_garden_budget_runtime as garden_runtime


class ComboContinuoTests(unittest.TestCase):
    def test_dois_combos_compartilham_um_unico_orcamento(self):
        bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs(), achievementWon=True, cookiesEarned=1e100)])
        now = [0]
        automation = ComboAutomation(bridge, ConfiguracaoCombo(maximo_lumps_total=3), relogio=lambda: now[0])
        def execute(**kwargs):
            bridge.calls.append(('quadcast', kwargs))
            bridge.snapshots[0]['spellsCastTotal'] += 4
            if kwargs['use_sugar_frenzy']:
                bridge.snapshots[0]['sugarFrenzyUsed'] = True
            return {'ok': True, 'lumpsSpent': 1+int(kwargs['use_sugar_frenzy']), 'clickSeconds': 8}
        bridge.execute_combo_quadcast = execute
        self.assertEqual(automation.executar_passo().estado, EstadoCombo.CLICANDO)
        now[0] = 9
        result = automation.executar_passo()
        self.assertEqual(result.estado, EstadoCombo.PREPARANDO)
        self.assertEqual(result.ciclos_concluidos, 1)
        self.assertEqual(result.lumps_gastos, 2)
        bridge.forecast.update(startCast=14, currentCast=14, skipCount=0)
        now[0] = 10
        self.assertEqual(automation.executar_passo().estado, EstadoCombo.CLICANDO)
        now[0] = 19
        result = automation.executar_passo()
        self.assertEqual(result.ciclos_concluidos, 2)
        self.assertEqual(result.lumps_gastos, 3)
        self.assertEqual(automation.executar_passo().estado, EstadoCombo.INTERROMPIDO)
        casts = [c[1] for c in bridge.calls if c[0] == 'quadcast']
        self.assertEqual([c['use_sugar_frenzy'] for c in casts], [True, False])
        self.assertEqual(len(casts), 2)

    def test_um_torrao_permite_tentativa_sem_frenesi_de_acucar(self):
        bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs())])
        bridge.quadcast_result['lumpsSpent'] = 1
        automation = ComboAutomation(bridge, ConfiguracaoCombo(maximo_lumps_total=1))
        self.assertEqual(automation.executar_passo().estado, EstadoCombo.CLICANDO)
        cast = next(c[1] for c in bridge.calls if c[0] == 'quadcast')
        self.assertFalse(cast['use_sugar_frenzy'])
        self.assertEqual(automation._lumps_gastos, 1)

    def test_limite_zero_nao_executa_mutacoes(self):
        bridge = FakeComboBridge()
        result = ComboAutomation(bridge, ConfiguracaoCombo(maximo_lumps_total=0)).executar_passo()
        self.assertTrue(result.terminal)
        self.assertEqual(bridge.calls, [('snapshot',)])

    def test_garden_desautorizado_nao_e_lido_nem_alterado(self):
        bridge = FakeComboBridge()
        automation = ComboAutomation(bridge, ConfiguracaoCombo())
        automation.executar_passo()
        self.assertFalse(any(c[0] in {'garden','plant','soil','layout'} for c in bridge.calls))
        bridge.snapshots[0]['buffs'] = ready_buffs()
        automation.executar_passo()
        cast = next(c[1] for c in bridge.calls if c[0] == 'quadcast')
        self.assertFalse(cast['optimize_garden'])

    def test_so_coleta_residuos_identificados_e_restaura_antes_de_recomecar(self):
        bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs())])
        expected = [{'id':55, 'force':'frenzy'}]
        bridge.quadcast_result['preserved'] = expected
        bridge.collect_combo_leftovers = Mock(return_value={'ok':True})
        now = [0]
        automation = ComboAutomation(bridge, ConfiguracaoCombo(), relogio=lambda:now[0])
        automation.executar_passo()
        now[0] = 10
        bridge.snapshots[0]['wizardTowers'] = 1
        result = automation.executar_passo()
        self.assertEqual(result.estado, EstadoCombo.PREPARANDO)
        bridge.collect_combo_leftovers.assert_called_once_with(tuple(expected))
        self.assertIn(('towers',601), bridge.calls)
        self.assertIsNone(automation._click_deadline)

    def test_falha_parcial_nao_reinicia_automaticamente(self):
        bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs())])
        bridge.quadcast_result = {'ok':False, 'mutated':True, 'lumpsSpent':1, 'message':'Resultado divergente'}
        result = ComboAutomation(bridge, ConfiguracaoCombo()).executar_passo()
        self.assertEqual(result.estado, EstadoCombo.ERRO_SEGURO)
        self.assertEqual(result.lumps_gastos, 1)

    def test_falha_ao_restaurar_torres_bloqueia_proximo_ciclo(self):
        bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs())])
        now = [0]
        automation = ComboAutomation(bridge, ConfiguracaoCombo(), relogio=lambda:now[0])
        automation.executar_passo()
        now[0] = 10
        bridge.snapshots[0]['wizardTowers'] = 1
        bridge.set_combo_wizard_towers = Mock(return_value={'ok':False})
        self.assertEqual(automation.executar_passo().estado, EstadoCombo.ERRO_SEGURO)
        self.assertEqual(sum(c[0] == 'quadcast' for c in bridge.calls), 1)

    def test_orcamento_do_bridge_e_liberado_ao_parar(self):
        bridge = FakeComboBridge()
        bridge.set_combo_cash_floor = Mock()
        automation = ComboAutomation(bridge, ConfiguracaoCombo())
        automation.parar()
        automation.executar()
        bridge.set_combo_cash_floor.assert_called_once_with(0)

    def test_recompoe_predios_vendidos_antes_de_abrir_outro_ciclo(self):
        buildings = [{'id':0,'amount':601}, {'id':2,'amount':1000}]
        bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs(), buildings=buildings)])
        bridge.quadcast_result['sold'] = [[2,600]]
        now = [0]
        automation = ComboAutomation(bridge, ConfiguracaoCombo(), relogio=lambda:now[0])
        automation.executar_passo()
        now[0] = 10
        result = automation.executar_passo()
        self.assertEqual(result.ciclos_concluidos, 1)
        self.assertIn(('minimum',2,1000), bridge.calls)
        self.assertEqual(automation._rebuild, {})

    def test_falta_de_saldo_na_recomposicao_aguarda_sem_repetir_combo(self):
        bridge = FakeComboBridge([combo_snapshot(buffs=ready_buffs())])
        now = [0]
        automation = ComboAutomation(bridge, ConfiguracaoCombo(), relogio=lambda:now[0])
        automation.executar_passo()
        now[0] = 10
        bridge.snapshots[0]['wizardTowers'] = 1
        bridge.set_combo_wizard_towers = Mock(return_value={'ok':False,'waiting':True})
        result = automation.executar_passo()
        self.assertEqual(result.estado, EstadoCombo.PREPARANDO)
        self.assertFalse(result.terminal)
        self.assertEqual(automation._ciclos_concluidos, 0)
        self.assertEqual(sum(c[0] == 'quadcast' for c in bridge.calls), 1)


class ReservasNativasTests(unittest.TestCase):
    def test_reserva_impede_quadcast_antes_de_gastar(self):
        value = combo_runtime.ComboRuntimeTests().run_combo(cashFloor=1e100)
        self.assertFalse(value['result']['ok'])
        self.assertTrue(value['result']['retryable'])
        self.assertEqual(value['events'], [])
        self.assertEqual(value['lumps'], 10)

    def test_reserva_do_garden_preserva_plantas_quando_lote_nao_cabe(self):
        runtime = garden_runtime.GardenBudgetRuntimeTests()
        blocked = runtime.run_layout(cookies=500, cashFloor=101)
        self.assertTrue(blocked['result'][0]['waiting'])
        self.assertEqual(blocked['events'], [])
        accepted = runtime.run_layout(cookies=500, cashFloor=100)
        self.assertTrue(all(r['ok'] for r in accepted['result']))
        self.assertEqual(accepted['cookies'], 100)

    def test_residuos_divergentes_nao_sao_coletados(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node necessário para conferir a coleta segura')
        bridge = CookieClickerBridge()
        with patch.object(bridge, 'execute_js', return_value={'ok':True}) as capture:
            bridge.collect_combo_leftovers([{'id':7,'force':'frenzy'}])
            script = capture.call_args.args[0]
        for force, count in (('frenzy',1), ('click frenzy',0)):
            source = "let n=0;globalThis.Game={shimmers:[{id:7,type:'golden',force:" + json.dumps(force) + ",pop(){n++;}}]};const result=" + script + ";console.log(JSON.stringify({result,n}));"
            process = subprocess.run([node,'-e',source],text=True,capture_output=True,timeout=10)
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertEqual(json.loads(process.stdout)['n'],count)
