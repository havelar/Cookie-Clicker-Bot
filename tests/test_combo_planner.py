"""Previsões de FtHoF contra o código original e painel manual seguro."""
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
from app.ui.combo_planner import ComboPlanner
from app.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[1]


class PlannerRuntimeTests(unittest.TestCase):
    def execute(self, count=100, mode="current", **options):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node necessário para comparar a previsão ao Grimoire original")
        bridge = CookieClickerBridge()
        with patch.object(bridge, "execute_js", return_value={"ok": True}) as execute:
            bridge.forecast_fthof_planner(count, mode)
            options.update(script=execute.call_args.args[0], mode=mode)
        process = subprocess.run([node, str(ROOT / "tests/fixtures/planner_runtime.js")],
                                 input=json.dumps(options), capture_output=True, text=True, cwd=ROOT, timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr)
        value = json.loads(process.stdout)
        self.assertTrue(value["unchanged"], "A consulta não pode alterar o jogo nem consumir o RNG")
        self.assertEqual(value["mismatches"], [])
        return value

    def test_previsoes_coincidem_com_funcoes_originais_em_todas_temporadas(self):
        for season in ("", "christmas", "halloween", "fools", "easter", "valentines"):
            with self.subTest(temporada=season):
                value = self.execute(season=season)
                self.assertTrue(value["result"]["ok"])
                self.assertEqual(value["checked"], 400)

    def test_buffs_aura_e_poucas_construcoes_seguem_referencia(self):
        for buffs in (("Dragonflight",), ("Magic adept",), ("Magic inept",), ("Magic adept", "Magic inept")):
            for buildings in (9, 10):
                with self.subTest(buffs=buffs, construcoes=buildings):
                    self.execute(buffs=buffs, buildings=buildings, aura=1, visible=2, season="easter")

    def test_comparacao_de_temporadas_nao_troca_temporada_real(self):
        for mode in ("normal", "seasonal"):
            value = self.execute(mode=mode, season="fools", seed="outro-save", cast=700)
            self.assertEqual(value["result"]["season"], "fools")
            self.assertEqual(value["result"]["seasonal"], mode == "seasonal")

    def test_offset_zero_e_contador_acompanham_magia_manual(self):
        before = self.execute(cast=40)["result"]
        after = self.execute(cast=41)["result"]
        self.assertEqual(before["rows"][0]["offset"], 0)
        self.assertEqual(before["rows"][0]["cast"], 40)
        self.assertEqual(before["rows"][1]["outcomes"], after["rows"][0]["outcomes"])

    def test_indisponibilidade_e_dados_invalidos_nao_simulam(self):
        for options in ({"unavailable": True}, {"ascending": True}, {"cast": -1}, {"seed": ""}):
            with self.subTest(condicao=options):
                value = self.execute(**options)
                self.assertFalse(value["result"]["ok"])
                self.assertEqual(value["checked"], 0)

    def test_parametros_invalidos_nao_consultam_bridge(self):
        bridge = CookieClickerBridge()
        with patch.object(bridge, "execute_js") as execute:
            for count, mode in ((True, "current"), (0, "current"), (501, "current"), (100, "invalido")):
                self.assertFalse(bridge.forecast_fthof_planner(count, mode)["ok"])
            execute.assert_not_called()


def report(cast=100):
    return {"ok": True, "seed": "teste", "currentCast": cast, "visible": 1,
            "seasonal": False, "dragonflight": False,
            "rows": [{"offset": 0, "cast": cast, "outcomes": [
                {"effect": effect, "backfire": effect == "blood frenzy", "failChance": .15 + index * .15}
                for index, effect in enumerate(("frenzy", "click frenzy", "blood frenzy", "building special"))]}]}


class PlannerUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.bridge = Mock(connected=True)
        self.panel = ComboPlanner(lambda: self.bridge)
        self.panel._request = (self.bridge, *self.panel._options())
        self.addCleanup(self.panel.close)
        self.addCleanup(self.panel.shutdown)

    def test_tabela_legivel_e_coluna_atual_destacada(self):
        self.panel.display_result(report())
        self.assertEqual(self.panel.table.rowCount(), 1)
        self.assertEqual(self.panel.table.item(0, 0).text(), "0")
        self.assertEqual(self.panel.table.item(0, 1).text(), "100")
        self.assertEqual(self.panel.table.item(0, 3).text(), "Frenesi de cliques")
        self.assertIn("biscoito da ira", self.panel.table.item(0, 4).toolTip())
        self.assertEqual(self.panel.table.item(0, 3).background().color().name(), "#25354c")
        self.assertEqual(self.bridge.method_calls, [])

    def test_atualizacao_sem_mudancas_preserva_tabela(self):
        self.panel.display_result(report())
        with patch.object(self.panel.table, "setRowCount") as update:
            self.panel.display_result(report())
            update.assert_not_called()

    def test_resultado_antigo_de_outra_conexao_e_descartado(self):
        self.panel._request = (Mock(), *self.panel._options())
        self.panel.display_result(report())
        self.assertEqual(self.panel.table.rowCount(), 0)

    def test_desconexao_limpa_previsao_antiga(self):
        self.panel.display_result(report())
        self.bridge.connected = False
        self.panel.refresh()
        self.assertEqual(self.panel.table.rowCount(), 0)
        self.bridge.forecast_fthof_planner.assert_not_called()

    def test_timer_para_ao_ocultar_e_atualizacao_automatica_e_opcional(self):
        with patch.object(self.panel, "refresh"):
            self.panel.show()
            self.app.processEvents()
            self.assertTrue(self.panel.timer.isActive())
            self.panel.auto_refresh.setChecked(False)
            self.assertFalse(self.panel.timer.isActive())
            self.panel.auto_refresh.setChecked(True)
            self.assertTrue(self.panel.timer.isActive())
            self.panel.hide()
            self.assertFalse(self.panel.timer.isActive())

    def test_consulta_assincrona_apenas_leitura_e_encerramento_seguro(self):
        self.bridge.forecast_fthof_planner.return_value = report()
        self.panel.refresh()
        self.assertTrue(self.panel.worker.wait(3000))
        self.app.processEvents()
        self.bridge.forecast_fthof_planner.assert_called_once_with(100, "current")
        self.assertEqual(self.panel.table.rowCount(), 1)
        self.assertTrue(self.panel.shutdown())
        self.panel.refresh()
        self.assertEqual(self.bridge.forecast_fthof_planner.call_count, 1)

    def test_planner_fica_na_aba_combo(self):
        with patch("app.ui.main_window.QTimer.singleShot"):
            window = MainWindow()
            try:
                self.assertEqual(window.combo_mode_tabs.tabText(2), "Planejador")
                self.assertIs(window.combo_mode_tabs.widget(2), window.combo_planner)
                self.assertIsNone(window.combo_planner.bridge_provider())
            finally:
                window.close()
