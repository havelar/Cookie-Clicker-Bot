"""Testes da máquina de estados, bridge e política da Auto Ascensão."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from app.bridge.js_bridge import CookieClickerBridge
from app.core.auto_ascensao import (
    AutoAscensao,
    ConfiguracaoAutoAscensao,
    planejar_lote_construcoes,
)
from app.models.auto_ascensao import (
    Construcao,
    EstadoAutoAscensao,
    ResultadoAcaoAscensao,
    SnapshotAscensao,
    UpgradeNormal,
)
from app.config.settings import AutomationConfig
from app.ui.main_window import MainWindow


def snapshot(screen="ascensao", gain=0, *, available=True, buildings=(), upgrades=()):
    return SnapshotAscensao(
        disponivel=available,
        tela=screen if available else "indisponivel",
        mensagem="Estado disponível" if available else "Bridge desconectada",
        ganho_prestigio=gain,
        construcoes=tuple(buildings),
        upgrades_normais=tuple(upgrades),
    )


def success(action):
    return ResultadoAcaoAscensao(True, action, "Operação verificada", quantidade_executada=1)


class FakeBridge:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.calls = []

    def get_ascension_snapshot(self):
        return self.snapshots.pop(0)

    def buy_heavenly_upgrade(self, upgrade_id):
        self.calls.append(("heavenly", upgrade_id))
        return success("comprar_heavenly")

    def reincarnate(self):
        self.calls.append(("reincarnate",))
        return success("reencarnar")

    def buy_all_normal_upgrades(self):
        self.calls.append(("upgrade_all",))
        return success("comprar_todos_upgrades")

    def buy_buildings_batch(self, building_ids, quantity_limit):
        self.calls.append(("buildings_batch", tuple(building_ids), quantity_limit))
        return success("comprar_lote_construcoes")

    def start_ascension(self, minimum):
        self.calls.append(("ascend", minimum))
        return success("ascender")


def configuration(*, cycles=1, gain=10, timeout=100, simulation=False):
    return ConfiguracaoAutoAscensao(cycles, gain, 1.0, timeout, simulation)


class AutoAscensaoStateMachineTests(unittest.TestCase):
    def test_complete_cycle_stops_at_cycle_limit(self):
        bridge = FakeBridge([
            snapshot(), snapshot(), snapshot(), snapshot("jogo"),
            snapshot("jogo", 10), snapshot("jogo", 10), snapshot(),
        ])
        production_calls = []
        stop_calls = []
        automation = AutoAscensao(
            bridge, configuration(),
            habilitar_producao=lambda: production_calls.append(True) or True,
            desabilitar_producao=lambda: stop_calls.append(True) or True,
        )

        automation.iniciar()
        for _ in range(6):
            report = automation.executar_passo()

        self.assertEqual(report.estado, EstadoAutoAscensao.CONCLUIDO)
        self.assertEqual(report.ciclo_atual, 1)
        self.assertEqual(production_calls, [True])
        self.assertGreaterEqual(len(stop_calls), 2)
        self.assertEqual(bridge.calls, [("reincarnate",), ("ascend", 10)])
        self.assertIn("Limite configurado", report.motivo_parada)

        repeated = automation.iniciar()
        self.assertEqual(repeated.estado, EstadoAutoAscensao.CONCLUIDO)
        self.assertEqual(bridge.calls, [("reincarnate",), ("ascend", 10)])

    def test_insufficient_prestige_waits_without_ascending(self):
        bridge = FakeBridge([
            snapshot(), snapshot(), snapshot(), snapshot("jogo"), snapshot("jogo", 9),
        ])
        automation = AutoAscensao(bridge, configuration(gain=10))
        automation.iniciar()
        automation.executar_passo()
        automation.executar_passo()
        automation.executar_passo()
        report = automation.executar_passo()

        self.assertEqual(report.estado, EstadoAutoAscensao.AGUARDANDO_PRESTIGIO)
        self.assertNotIn("ascend", [call[0] for call in bridge.calls])

    def test_timeout_stops_without_forced_ascension(self):
        clock_values = iter((0.0, 101.0))
        bridge = FakeBridge([snapshot()])
        automation = AutoAscensao(
            bridge, configuration(timeout=100), relogio=lambda: next(clock_values)
        )

        automation.iniciar()
        report = automation.executar_passo()

        self.assertEqual(report.estado, EstadoAutoAscensao.INTERROMPIDO)
        self.assertIn("Tempo máximo", report.motivo_parada)
        self.assertEqual(bridge.calls, [])

    def test_manual_stop_prevents_new_mutations_and_keeps_snapshot(self):
        initial = snapshot()
        bridge = FakeBridge([initial])
        automation = AutoAscensao(bridge, configuration())
        automation.iniciar()

        automation.parar()
        report = automation.executar_passo()

        self.assertEqual(report.estado, EstadoAutoAscensao.INTERROMPIDO)
        self.assertIs(report.snapshot, initial)
        self.assertEqual(bridge.calls, [])

    def test_bridge_failure_enters_safe_error(self):
        bridge = FakeBridge([snapshot(available=False)])
        automation = AutoAscensao(bridge, configuration())

        report = automation.iniciar()

        self.assertEqual(report.estado, EstadoAutoAscensao.ERRO_SEGURO)
        self.assertIn("Bridge desconectada", report.motivo_parada)
        self.assertEqual(bridge.calls, [])

    def test_unexpected_screen_enters_safe_error(self):
        bridge = FakeBridge([snapshot(), snapshot("jogo")])
        automation = AutoAscensao(bridge, configuration())
        automation.iniciar()

        report = automation.executar_passo()

        self.assertEqual(report.estado, EstadoAutoAscensao.ERRO_SEGURO)
        self.assertIn("Tela inesperada", report.motivo_parada)

    def test_simulation_never_calls_mutable_operations(self):
        building = Construcao(5, "Banco", 0, 100, 3)
        bridge = FakeBridge([snapshot("jogo", 2, buildings=(building,))])
        automation = AutoAscensao(bridge, configuration(simulation=True))

        report = automation.executar()

        self.assertEqual(report.estado, EstadoAutoAscensao.PREVIA)
        self.assertTrue(report.simulacao)
        self.assertIn("Banco", report.proximo_passo)
        self.assertEqual(bridge.calls, [])

    def test_native_buy_all_precedes_building_purchase(self):
        upgrade = UpgradeNormal(12, "Upgrade", 10, True)
        building = Construcao(5, "Banco", 0, 100, 3)
        bridge = FakeBridge([
            snapshot(), snapshot(), snapshot(), snapshot("jogo"),
            snapshot("jogo", 2, buildings=(building,), upgrades=(upgrade,)),
        ])
        automation = AutoAscensao(bridge, configuration())
        automation.iniciar()
        automation.executar_passo()
        automation.executar_passo()
        automation.executar_passo()

        automation.executar_passo()

        self.assertIn(("upgrade_all",), bridge.calls)
        self.assertNotIn(("buildings_batch", (5,), 100), bridge.calls)

    def test_building_batch_includes_every_affordable_building_in_priority_order(self):
        buildings = (
            Construcao(1, "Avó", 0, 10, 500),
            Construcao(8, "Prisma", 0, 1000, 2),
            Construcao(6, "Templo", 0, 500, 40),
        )
        bridge = FakeBridge([
            snapshot(), snapshot(), snapshot(), snapshot("jogo"),
            snapshot("jogo", 2, buildings=buildings),
        ])
        automation = AutoAscensao(bridge, configuration())
        automation.iniciar()
        automation.executar_passo()
        automation.executar_passo()
        automation.executar_passo()

        automation.executar_passo()

        self.assertIn(("buildings_batch", (8, 6, 1), 100), bridge.calls)


class BuildingPolicyTests(unittest.TestCase):
    def test_plans_every_affordable_building_with_best_first_and_batches_of_100(self):
        plan = planejar_lote_construcoes((
            Construcao(1, "Avó", 10, 10, 250),
            Construcao(8, "Prisma", 0, 1000, 0),
            Construcao(6, "Templo", 0, 500, 4),
            Construcao(9, "Bloqueada", 0, 100, 10, desbloqueada=False),
        ))

        self.assertEqual([item.id for item in plan], [6, 1])
        self.assertEqual([item.quantidade for item in plan], [4, 100])
        self.assertTrue(all("prioridade" in item.motivo for item in plan))

    def test_returns_empty_plan_without_useful_quantity(self):
        self.assertEqual(planejar_lote_construcoes((
            Construcao(1, "Avó", 0, 10, 0),
        )), ())


class AscensionBridgeTests(unittest.TestCase):
    class StubBridge(CookieClickerBridge):
        def __init__(self, responses):
            self.responses = list(responses)
            self.scripts = []

        def execute_js(self, code):
            self.scripts.append(code)
            return self.responses.pop(0)

    def test_snapshot_parser_rejects_invalid_payload(self):
        bridge = self.StubBridge([None])

        result = bridge.get_ascension_snapshot()

        self.assertFalse(result.disponivel)
        self.assertEqual(result.tela, "indisponivel")

    def test_building_batch_preserves_partial_context_on_ambiguous_result(self):
        bridge = self.StubBridge([{
            "ok": False,
            "reason": "ambiguous_result",
            "message": "O jogo não confirmou o lote",
            "quantity": 35,
            "before": 10,
            "after": 45,
        }])

        result = bridge.buy_buildings_batch([2, 5, 1], 100)

        self.assertFalse(result.sucesso)
        self.assertEqual(result.quantidade_executada, 35)
        self.assertIn("const ids=[5, 2, 1], limit=100", bridge.scripts[0])
        self.assertIn("object.buy(limit)", bridge.scripts[0])

    def test_invalid_action_is_rejected_before_javascript(self):
        bridge = self.StubBridge([])

        result = bridge.buy_buildings_batch([], 100)

        self.assertFalse(result.sucesso)
        self.assertEqual(bridge.scripts, [])

    def test_buy_all_uses_native_runtime_button_once(self):
        bridge = self.StubBridge([{
            "ok": True,
            "reason": "verified",
            "message": "3 upgrades comprados e verificados",
            "quantity": 3,
            "before": 10,
            "after": 13,
        }])

        result = bridge.buy_all_normal_upgrades()

        self.assertTrue(result.sucesso)
        self.assertEqual(result.quantidade_executada, 3)
        self.assertEqual(bridge.scripts[0].count("Game.storeBuyAll();"), 1)
        self.assertNotIn("querySelector", bridge.scripts[0])


class AutoAscensaoUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_tab_exposes_preview_safety_controls_and_progress(self):
        window = MainWindow()
        tab_names = [window.tabs.tabText(index) for index in range(window.tabs.count())]

        self.assertIn("Auto Ascensão", tab_names)
        self.assertTrue(window.auto_ascension_simulation_checkbox.isChecked())
        self.assertEqual(window.auto_ascension_preview_button.text(), "Atualizar prévia")
        self.assertEqual(window.auto_ascension_stop_button.text(), "Parar imediatamente")
        self.assertFalse(window.auto_ascension_stop_button.isEnabled())
        window.close()

    def test_automation_configuration_default_is_disabled(self):
        config = AutomationConfig()
        self.assertFalse(config.enable_auto_ascension)
        self.assertEqual(config.auto_ascension_poll_interval_seconds, 0.1)


if __name__ == "__main__":
    unittest.main()
