"""Conquista oficial, orçamento, proteção de plantas e convivência do GC Farm."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication
from app.bridge.gc_farm_scripts import PREPARE, SNAPSHOT, COLLECT
from app.bridge.js_bridge import CookieClickerBridge
from app.config.settings import automation_config, load_automation_settings, save_automation_settings
from app.core.gc_farm import GCFarm
from app.core.garden_catalog import GARDEN_CATALOG
from app.core.run import AutomationRunner
from app.models.garden import GardenActionResult, GardenPlant, GardenSeed
from app.ui.main_window import MainWindow
from tests.test_combo import empty_garden


class GCFarmTests(unittest.TestCase):
    def setUp(self):
        self.now = [0]
        self.bridge = Mock()
        self.state = dict(available=True, seed='teste', count=100, cookies=1000, completed=False, chain=False)
        self.bridge.get_gc_farm_snapshot.side_effect = lambda: dict(self.state)
        self.bridge.prepare_gc_farm.return_value = dict(ok=True, message='Coletando.')
        self.bridge.get_garden_snapshot.return_value = replace(empty_garden(), game_seed='teste',
            next_tick_at=100, cookies=1000, unlocked_tiles=tuple((x,y) for y in range(6) for x in range(6)),
            seeds=tuple(GardenSeed(i,key,key,key!='queenbeetLump',True,50) for i,key in enumerate(GARDEN_CATALOG)))
        self.bridge.execute_garden_layout.return_value = (GardenActionResult(True,'layout','Plantado.'),)
        self.farm = GCFarm(self.bridge, clock=lambda:self.now[0])

    def test_taxa_e_previsao_usam_apenas_o_contador_oficial(self):
        first = self.farm.step()
        self.assertIsNone(first['eta'])
        self.now[0] = 3600
        self.state['count'] += 120
        result = self.farm.step()
        self.assertEqual(result['rate'], 120)
        self.assertEqual(result['gained'],120)
        self.assertEqual(result['eta'], (27777-220)*30)

    def test_contador_parado_nao_inventa_previsao(self):
        self.farm.step(); self.now[0] = 300
        result = self.farm.step()
        self.assertEqual(result['rate'],0)
        self.assertIsNone(result['eta'])

    def test_conquista_pronta_nao_faz_preparo_nem_garden(self):
        self.state['count'] = 27777
        result = self.farm.step()
        self.assertTrue(result['completed'])
        self.bridge.prepare_gc_farm.assert_not_called()
        self.bridge.get_garden_snapshot.assert_not_called()

    def test_ultimo_clique_manual_nao_encerra_nem_pausa_preparo(self):
        enabled = [True]
        self.farm.manual_last_click = lambda: enabled[0]
        self.state['count'] = 27776
        report = self.farm.step()
        self.assertTrue(report['waiting_manual'])
        self.assertFalse(report['terminal'])
        self.bridge.prepare_gc_farm.assert_called_once()
        enabled[0] = False
        self.assertFalse(self.farm.step()['waiting_manual'])
        self.state['count'] = 27777
        enabled[0] = True
        report = self.farm.step()
        self.assertFalse(report['waiting_manual'])
        self.assertTrue(report['completed'])

    def test_troca_de_save_ou_regressao_encerra_sem_mutacoes(self):
        for changes in ({'seed':'outro'}, {'count':99}):
            with self.subTest(changes=changes):
                self.setUp(); self.farm.step(); self.bridge.reset_mock()
                self.state.update(changes)
                self.assertTrue(self.farm.step()['terminal'])
                self.bridge.prepare_gc_farm.assert_not_called()

    def test_dados_invalidos_nao_mutam(self):
        for changes in ({'available':False},{'count':True},{'count':-1},{'count':None},{'seed':''}):
            with self.subTest(changes=changes):
                self.setUp(); self.state.update(changes)
                self.assertTrue(self.farm.step()['terminal'])
                self.bridge.prepare_gc_farm.assert_not_called()

    def test_corrente_adia_todo_o_preparo(self):
        self.state['chain'] = True
        self.farm.step()
        self.bridge.prepare_gc_farm.assert_not_called()
        self.bridge.get_garden_snapshot.assert_not_called()

    def test_acao_recusada_fica_clara_no_acompanhamento(self):
        self.bridge.prepare_gc_farm.return_value = dict(ok=False,changed=True,message='Trocar temporada.')
        self.assertIn('não confirmou',self.farm.step()['message'])

    def test_lote_de_36_casas_e_reserva_local(self):
        self.farm.step()
        args = self.bridge.execute_garden_layout.call_args
        actions = args.args[0]
        self.assertEqual(sum(a.seed_key=='goldenClover' for a in actions),18)
        self.assertEqual(sum(a.seed_key=='nursetulip' for a in actions),18)
        self.assertEqual(args.kwargs['cash_floor'],800)
        self.bridge.set_combo_cash_floor.assert_not_called()

    def test_um_lote_bem_sucedido_por_tick(self):
        self.farm.step(); self.now[0] = 11; self.farm.step()
        self.bridge.execute_garden_layout.assert_called_once()

    def test_falta_de_saldo_pode_tentar_novamente_sem_limpar(self):
        self.bridge.execute_garden_layout.return_value = (GardenActionResult(False,'layout','Aguardando dinheiro.'),)
        self.farm.step(); self.now[0] = 11; self.farm.step()
        self.assertEqual(self.bridge.execute_garden_layout.call_count,2)
        self.bridge.harvest_garden_tile.assert_not_called()

    def test_descobertas_e_plantas_desconhecidas_protegidas(self):
        garden = self.bridge.get_garden_snapshot.return_value
        garden = replace(garden, plants=(
            GardenPlant(0,0,20,'queenbeetLump','Juicy Queenbeet',90,80,True),
            GardenPlant(1,0,99,'desconhecida','Desconhecida',10,20,False)))
        self.bridge.get_garden_snapshot.return_value = garden
        self.farm.step()
        actions = self.bridge.execute_garden_layout.call_args.args[0]
        self.assertFalse(any((a.x,a.y) in ((0,0),(1,0)) for a in actions))

    def test_parada_impede_novas_leituras_e_mutacoes(self):
        farm = GCFarm(self.bridge, should_stop=lambda:True)
        self.assertTrue(farm.step()['terminal'])
        self.assertFalse(self.bridge.mock_calls)

    def test_garden_de_outro_save_nao_e_alterado(self):
        self.bridge.get_garden_snapshot.return_value = replace(self.bridge.get_garden_snapshot.return_value, game_seed='outro')
        self.farm.step()
        self.bridge.execute_garden_layout.assert_not_called()

    def test_taxa_movel_descarta_dados_antigos(self):
        for now,count in ((0,100),(1800,200),(3600,300),(5400,600)):
            self.now[0]=now;self.state['count']=count;result=self.farm.step()
        self.assertEqual(result['rate'],400)


class ConvivenciaGCTests(unittest.TestCase):
    def setUp(self):
        with patch('app.core.run.InputHandler'):
            self.runner = AutomationRunner(1,Mock())

    def test_reserva_bloqueia_outros_modos_e_libera_ao_parar(self):
        self.assertTrue(self.runner.acquire_gc_farm())
        self.assertFalse(self.runner.acquire_simple_farm())
        self.assertFalse(self.runner.acquire_exclusive('combo'))
        self.assertFalse(self.runner.acquire_exclusive('save_scum'))
        self.runner.release_gc_farm()
        self.assertTrue(self.runner.acquire_simple_farm())

    def test_farm_nao_invade_modo_ativo(self):
        self.runner.acquire_simple_farm()
        self.assertFalse(self.runner.acquire_gc_farm())

    def test_detector_mantem_torroes_e_coletas_sem_magias_ou_temporadas(self):
        self.runner.acquire_gc_farm()
        self.runner.activate_gc_farm_collection('teste')
        self.runner.bridge.collect_gc_farm.return_value = 2
        for name in ('_run_sugar_lump_cycle','_run_wrinkler_cycle','_run_krumblor_cycle','_run_grimoire_cycle','_run_season_cycle'):
            setattr(self.runner,name,Mock())
        self.runner._run_detector_cycle()
        self.runner._run_sugar_lump_cycle.assert_called_once()
        self.runner._run_wrinkler_cycle.assert_called_once()
        self.runner._run_krumblor_cycle.assert_called_once()
        self.runner._run_season_cycle.assert_not_called()
        self.runner._run_grimoire_cycle.assert_not_called()
        self.runner.bridge.pop_golden_cookie.assert_not_called()
        self.assertEqual(self.runner.golden_cookies_clicked,2)

    def test_coleta_aguarda_backup_e_primeira_leitura(self):
        self.runner.acquire_gc_farm()
        with patch.object(self.runner, '_run_sugar_lump_cycle'), patch.object(self.runner, '_run_wrinkler_cycle'), patch.object(self.runner, '_run_krumblor_cycle'):
            self.runner._run_detector_cycle()
        self.runner.bridge.collect_gc_farm.assert_not_called()


@unittest.skipUnless(shutil.which('node'),'Node.js necessário para o runtime isolado.')
class RuntimeGCTests(unittest.TestCase):
    def run_script(self, script=PREPARE, cycles=1, **options):
        fixture = Path(__file__).with_name('fixtures').joinpath('gc_farm_runtime.js').read_text(encoding='utf-8')
        source = fixture.replace('OPTIONS',json.dumps(options))
        script = script.replace('__RESERVE__',str(options.get('reserve',80))).replace('__SEED__',json.dumps(options.get('expectedSeed')))
        script = script.replace('__MANUAL_LAST__', json.dumps(options.get('manualLast', False)))
        source += '\nconst results=[];for(let i=0;i<'+str(cycles)+';i++)results.push('+script+');'
        source += 'console.log(JSON.stringify({results,events,count:G.goldenClicks,cookies:G.cookies,slots:P.slot,auras:[G.dragonAura,G.dragonAura2]}));'
        result = subprocess.run([shutil.which('node'),'-e',source],capture_output=True,text=True,encoding='utf-8',check=True)
        return json.loads(result.stdout)

    def test_coleta_apenas_naturais_e_vermelhos_validos(self):
        result = self.run_script(COLLECT)
        self.assertEqual(result['results'],[2])
        self.assertEqual(result['events'],['clique:natural','clique:vermelho'])

    def test_opcao_manual_bloqueia_somente_o_clique_27777(self):
        for count, clicked in ((27774,2),(27775,1),(27776,0),(27777,2),(27778,2)):
            with self.subTest(count=count):
                result = self.run_script(COLLECT,count=count,manualLast=True)
                self.assertEqual(result['results'],[clicked])
                self.assertEqual(result['count'],count+clicked)

    def test_opcao_desmarcada_permite_o_ultimo_clique(self):
        result = self.run_script(COLLECT,count=27776,manualLast=False)
        self.assertEqual(result['results'],[2])
        self.assertEqual(result['count'],27778)

    def test_corrente_ou_conquista_nao_fazem_preparo(self):
        for options in ({'chain':1},{'count':27777},{'completed':True},{'ascend':True}):
            self.assertEqual(self.run_script(primary=4,season='easter',**options)['events'],[])

    def test_reserva_impede_compra_de_temporada(self):
        result = self.run_script(season='easter',price=300)
        self.assertTrue(result['results'][0]['waiting'])
        self.assertEqual(result['events'],[])

    def test_preparo_nativo_corrige_interruptor_vovos_panteao_temporada_e_auras(self):
        result = self.run_script(cycles=8,switchOn=True,wrath=3,slots=[10,4,9],season='easter',primary=4,secondary=13)
        self.assertEqual(result['auras'],[9,18])
        self.assertEqual(result['slots'],[4,10,-1])
        self.assertEqual(result['events'].count('sacrifício'),2)
        self.assertIn('compra:Elder Pledge',result['events'])
        self.assertIn("compra:Fool's biscuit",result['events'])

    def test_auras_ja_otimas_em_ordem_inversa_nao_gastam(self):
        self.assertEqual(self.run_script(primary=18,secondary=9)['events'],[])

    def test_aguarda_troca_sem_gastar_torroes(self):
        result=self.run_script(slots=[10,4,9],swaps=0)
        self.assertTrue(result['results'][0]['waiting'])
        self.assertEqual(result['events'],[])

    def test_compra_melhoria_de_frequencia_e_respeita_cofre(self):
        name='Green yeast digestives'
        self.assertIn('compra:'+name,self.run_script(missingUpgrade=name)['events'])
        self.assertEqual(self.run_script(missingUpgrade=name,vaulted=name)['events'],[])

    def test_compra_recusada_nao_e_reportada_como_sucesso(self):
        self.assertFalse(self.run_script(season='easter',refuse=True)['results'][0]['ok'])

    def test_nao_compra_melhorias_celestiais_fora_da_ascensao(self):
        result=self.run_script(missingUpgrade='Startrade',prestige='Startrade')
        self.assertEqual(result['events'],[])

    def test_leitura_nao_muta(self):
        result=self.run_script(SNAPSHOT)
        self.assertEqual(result['events'],[])
        self.assertEqual(result['results'][0]['count'],100)

    def test_importacao_de_outro_save_bloqueia_acoes_e_coleta(self):
        self.assertEqual(self.run_script(expectedSeed='outro',season='easter')['events'],[])
        self.assertEqual(self.run_script(COLLECT,expectedSeed='outro')['results'],[0])

    def test_uma_aura_ja_correta_no_segundo_slot_e_reutilizada(self):
        result=self.run_script(primary=4,secondary=9)
        self.assertEqual(result['auras'],[18,9])
        self.assertEqual(result['events'].count('sacrifício'),1)

    def test_temporada_bloqueada_nao_impede_outros_ajustes(self):
        result=self.run_script(season='easter',locked="Fool's biscuit",primary=4)
        self.assertEqual(result['auras'],[9,18])
        self.assertNotIn("compra:Fool's biscuit",result['events'])


class InterfaceGCTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.window=MainWindow()
        self.addCleanup(self.window.close)

    def test_aba_com_seletor_futuro_desabilitado(self):
        self.assertIn('GC Farm',[self.window.tabs.tabText(i) for i in range(self.window.tabs.count())])
        tab=self.window.gc_farm_tab
        self.assertEqual(tab.strategy.currentData(),'golden')
        self.assertFalse(tab.strategy.model().item(1).isEnabled())
        self.assertFalse(tab.toggle.running)

    def test_inicio_cria_backup_pausa_garden_mas_mantem_banco(self):
        w=self.window;w.bridge=Mock();w.runner=Mock();w._bot_enabled=True
        w.runner.acquire_gc_farm.return_value=True
        w.bridge.get_game_save.return_value='save-de-teste'
        w.backup_manager=Mock()
        w.stock_toggle.setEnabled(True)
        w._garden_stop.clear()
        with patch.object(w,'_set_combo_keep_awake'):
            self.assertTrue(w.begin_gc_farm())
            self.assertTrue(w._garden_stop.is_set())
            self.assertFalse(w.garden_toggle.isEnabled())
            self.assertTrue(w.stock_toggle.isEnabled())
            w.backup_manager.create_backup.assert_called_once_with('save-de-teste','antes-do-gc-farm')
            w.end_gc_farm(False)
        self.assertFalse(w._garden_stop.is_set())
        self.assertFalse(w._gc_farm_active)

    def test_conquista_encerra_modo_e_mantem_garden_pausado(self):
        w=self.window;w.bridge=Mock();w.runner=Mock();w._bot_enabled=True;w.backup_manager=Mock()
        with patch.object(w,'_set_combo_keep_awake'):
            self.assertTrue(w.begin_gc_farm())
            w.end_gc_farm(True)
        self.assertTrue(w._garden_stop.is_set())
        w.runner.release_gc_farm.assert_called_once()

    def test_falha_no_backup_nao_deixa_reserva_presa(self):
        w=self.window;w.bridge=Mock();w.runner=Mock();w._bot_enabled=True
        w.bridge.get_game_save.return_value=None
        with patch.object(w,'_set_combo_keep_awake'):
            self.assertFalse(w.begin_gc_farm())
        self.assertFalse(w._gc_farm_active)
        w.runner.release_gc_farm.assert_called_once()

    def test_reserva_persiste_sem_iniciar_farm(self):
        previous=copy.deepcopy(automation_config.__dict__)
        values={}
        settings=Mock()
        settings.value.side_effect=lambda key,default=None,**kw:values.get(key,default)
        settings.setValue.side_effect=lambda key,value:values.update({key:value})
        try:
            with patch('app.config.settings.QSettings',return_value=settings):
                automation_config.gc_farm_reserve_percent=15
                automation_config.gc_farm_manual_last_click=True
                save_automation_settings()
                automation_config.gc_farm_reserve_percent=80
                automation_config.gc_farm_manual_last_click=False
                load_automation_settings()
            self.assertEqual(automation_config.gc_farm_reserve_percent,15)
            self.assertTrue(automation_config.gc_farm_manual_last_click)
            self.assertFalse(self.window.gc_farm_tab.active)
        finally:
            automation_config.__dict__.update(previous)

    def test_desligar_cancela_inicio_que_aguardava_outro_modo(self):
        tab=self.window.gc_farm_tab
        with patch.object(self.window,'begin_gc_farm',return_value=None), patch('app.ui.gc_farm_tab.QTimer.singleShot'):
            tab.request(True)
            self.assertTrue(tab.start_pending)
            tab.request(False)
            tab._retry_start()
        self.assertFalse(tab.start_pending)
        self.assertFalse(tab.active)

    def test_checkbox_do_ultimo_clique_pode_mudar_com_farm_ligado(self):
        previous = automation_config.gc_farm_manual_last_click
        tab = self.window.gc_farm_tab
        try:
            with patch('app.ui.gc_farm_tab.save_automation_settings') as save:
                tab.manual_last_click.setChecked(False)
                tab.toggle.set_running(True)
                tab.manual_last_click.setChecked(True)
                self.assertTrue(automation_config.gc_farm_manual_last_click)
                self.assertTrue(tab.manual_last_click.isEnabled())
                self.assertTrue(tab.toggle.running)
                save.assert_called()
        finally:
            automation_config.gc_farm_manual_last_click = previous

    def test_controles_e_ciclos_do_garden_nao_invadem_farm(self):
        w=self.window;w._gc_farm_active=True;w.fazendeira=Mock()
        try:
            w._on_garden_timer()
            w.refresh_garden()
            w.simulate_garden()
            w._toggle_garden_automation(True)
            w.fazendeira.run_cycle.assert_not_called()
            w._set_garden_busy(False)
            self.assertFalse(w.garden_strategy_combo.isEnabled())
        finally:
            w._gc_farm_active=False
