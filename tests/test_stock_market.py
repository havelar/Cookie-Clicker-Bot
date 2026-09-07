"""Testes da integração manual com o Stock Market."""
import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from app.bridge.js_bridge import CookieClickerBridge
from app.core.stock_market import StockMarketAutomation
from app.models.stock_market import (
    StockAsset,
    StockMarketAutomationResult,
    StockMarketSnapshot,
    StockMarketStatus,
    StockTradeResult,
)
from app.ui.main_window import MainWindow


class StubBridge(CookieClickerBridge):
    def __init__(self, responses):
        self.responses = list(responses)
        self.scripts = []

    def execute_js(self, code):
        self.scripts.append(code)
        return self.responses.pop(0)


class UndefinedRuntime:
    @staticmethod
    def evaluate(**_kwargs):
        return {"result": {"type": "undefined"}}


class UndefinedTab:
    Runtime = UndefinedRuntime()


class AutomationBridge:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.calls = []

    def get_stock_market_snapshot(self):
        return self.snapshots.pop(0)

    def buy_stock_max(self, asset_id):
        self.calls.append(("buy", asset_id))
        return StockTradeResult(True, "buy", asset_id, 10_000, 5, "Compra máxima executada", is_maximum_order=True)

    def sell_stock_max(self, asset_id):
        self.calls.append(("sell", asset_id))
        return StockTradeResult(True, "sell", asset_id, 10_000, 3, "Venda máxima executada", is_maximum_order=True)


class StockMarketBridgeTests(unittest.TestCase):
    def test_undefined_javascript_result_is_not_a_cdp_error(self):
        bridge = object.__new__(CookieClickerBridge)
        bridge.connected = True
        bridge.tab = UndefinedTab()
        bridge._runtime_lock = threading.RLock()

        self.assertIsNone(bridge.execute_js("void 0"))

    def test_status_reports_unlocked_but_not_loaded(self):
        bridge = StubBridge([{
            "available": False,
            "unlocked": True,
            "message": "Stock Market desbloqueado, mas ainda não carregado",
        }])

        status = bridge.get_stock_market_status()

        self.assertFalse(status.available)
        self.assertTrue(status.unlocked)
        self.assertIn("não carregado", status.message)

    def test_snapshot_is_parsed_into_immutable_domain_models(self):
        bridge = StubBridge([{
            "status": {"available": True, "unlocked": True, "message": "disponível"},
            "cookies": 1000.0,
            "highestRawCps": 10.0,
            "tradingFunds": 100.0,
            "brokers": 3,
            "brokerOverhead": 1.17,
            "profit": 5.5,
            "assets": [{
                "id": 2, "name": "Salt", "symbol": "SLT", "price": 12.5,
                "priceChangePercent": -2.75, "owned": 4, "capacity": 20,
            }],
        }])

        snapshot = bridge.get_stock_market_snapshot()

        self.assertTrue(snapshot.status.available)
        self.assertEqual(snapshot.trading_funds, 100.0)
        self.assertEqual(snapshot.assets, (StockAsset(2, "Salt", "SLT", 12.5, 4, 20, -2.75),))

    def test_invalid_snapshot_payload_is_safe(self):
        bridge = StubBridge([{"status": {"available": True, "unlocked": True}, "assets": "invalid"}])

        snapshot = bridge.get_stock_market_snapshot()

        self.assertFalse(snapshot.status.available)
        self.assertEqual(snapshot.assets, ())

    def test_invalid_order_is_rejected_before_javascript(self):
        bridge = StubBridge([])

        result = bridge.buy_stock(0, 0)

        self.assertFalse(result.success)
        self.assertEqual(result.executed_quantity, 0)
        self.assertEqual(bridge.scripts, [])

    def test_out_of_range_asset_is_rejected_before_javascript(self):
        bridge = StubBridge([])

        result = bridge.sell_stock(10_001, 1)

        self.assertFalse(result.success)
        self.assertIn("Identificador", result.message)
        self.assertEqual(bridge.scripts, [])

    def test_manual_sentinel_quantity_requires_the_maximum_action(self):
        bridge = StubBridge([])

        result = bridge.buy_stock(1, 10_000)

        self.assertFalse(result.success)
        self.assertIn("ordem máxima", result.message)
        self.assertEqual(bridge.scripts, [])

    def test_successful_order_reports_verified_quantity(self):
        bridge = StubBridge([{
            "ok": True, "message": "Compra executada", "before": 2,
            "after": 5, "executed": 3, "price": 7.0, "total": 21.0,
        }])

        result = bridge.buy_stock(1, 3)

        self.assertTrue(result.success)
        self.assertEqual(result.executed_quantity, 3)
        self.assertIn("M.buyGood", bridge.scripts[0])
        self.assertNotIn("querySelector", bridge.scripts[0])

    def test_maximum_order_uses_the_game_sentinel_and_accepts_partial_quantity(self):
        bridge = StubBridge([{
            "ok": True, "message": "Compra máxima executada", "before": 2,
            "after": 15, "executed": 13, "price": 7.0, "total": 70_000.0,
        }])

        result = bridge.buy_stock_max(1)

        self.assertTrue(result.success)
        self.assertTrue(result.is_maximum_order)
        self.assertEqual(result.executed_quantity, 13)
        self.assertIn("quantity = 10000", bridge.scripts[0])
        self.assertIn("isMaximum = true", bridge.scripts[0])

    def test_missing_cdp_response_becomes_failed_order(self):
        bridge = StubBridge([None])

        result = bridge.sell_stock(1, 2)

        self.assertFalse(result.success)
        self.assertIn("resposta inválida", result.message)


class StockMarketUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_snapshot_populates_table_and_enables_only_after_selection(self):
        window = MainWindow()
        snapshot = StockMarketSnapshot(
            status=StockMarketStatus(True, True, "Stock Market disponível"),
            assets=(StockAsset(7, "Chocolate", "CHC", 42.25, 8, 30, 1.5),),
        )

        window._display_stock_snapshot(snapshot)
        self.assertEqual(window.stock_table.rowCount(), 1)
        self.assertEqual(window.stock_table.item(0, 2).text(), "+1.50%")
        self.assertFalse(window.stock_buy_button.isEnabled())

        window.stock_table.selectRow(0)
        self.assertTrue(window.stock_buy_button.isEnabled())
        self.assertTrue(window.stock_use_max_checkbox.isEnabled())
        self.assertEqual(window.stock_table.item(0, 0).data(Qt.UserRole), 7)
        window.close()


class StockMarketAutomationTests(unittest.TestCase):
    def test_cycle_buys_low_unowned_assets_and_sells_high_owned_assets(self):
        status = StockMarketStatus(True, True, "disponível")
        before = StockMarketSnapshot(
            status=status,
            assets=(
                StockAsset(0, "Low", "LOW", 12.0, 0, 10),
                StockAsset(1, "Held", "HLD", 95.0, 4, 10),
                StockAsset(2, "Ignored", "IGN", 30.0, 0, 10),
            ),
        )
        after = StockMarketSnapshot(status=status, assets=before.assets)
        bridge = AutomationBridge([before, after])

        result = StockMarketAutomation(bridge).run_cycle(20.0, 80.0)

        self.assertIsInstance(result, StockMarketAutomationResult)
        self.assertEqual(bridge.calls, [("buy", 0), ("sell", 1)])
        self.assertEqual(len(result.orders), 2)

    def test_cycle_does_not_trade_when_market_is_unavailable(self):
        snapshot = StockMarketSnapshot(StockMarketStatus(False, False, "indisponível"))
        bridge = AutomationBridge([snapshot])

        result = StockMarketAutomation(bridge).run_cycle(20.0, 80.0)

        self.assertEqual(bridge.calls, [])
        self.assertEqual(result.orders, ())


if __name__ == "__main__":
    unittest.main()
