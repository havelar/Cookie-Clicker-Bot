"""Testes da integração manual com o Stock Market."""
import os
from pathlib import Path
import tempfile
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from app.bridge.js_bridge import CookieClickerBridge
from app.core.stock_market import StockMarketAutomation, StockMarketPerformanceTracker
from app.core.market_history import MarketHistoryStore
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
            "tick": 42,
            "tickProgress": 15,
            "secondsPerTick": 60.0,
            "highestRawCps": 10.0,
            "tradingFunds": 100.0,
            "brokers": 3,
            "brokerOverhead": 1.17,
            "profit": 5.5,
            "assets": [{
                "id": 2, "name": "Salt", "symbol": "SLT", "price": 12.5,
                "priceChangePercent": -2.75, "lastBoughtPrice": 14.0,
                "priceHistory": [12.5, 12.9, 13.1], "owned": 4, "capacity": 20,
            }],
        }])

        snapshot = bridge.get_stock_market_snapshot()

        self.assertTrue(snapshot.status.available)
        self.assertEqual(snapshot.trading_funds, 100.0)
        self.assertEqual(snapshot.tick, 42)
        self.assertEqual(snapshot.assets, (StockAsset(2, "Salt", "SLT", 12.5, 4, 20, -2.75, 14.0, (12.5, 12.9, 13.1)),))

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
    def test_cycle_buys_low_falling_and_sells_high_rising_with_max_orders(self):
        status = StockMarketStatus(True, True, "disponível")
        before = StockMarketSnapshot(
            status=status,
            tick=100,
            broker_overhead=1.01,
            assets=(
                StockAsset(0, "Low", "LOW", 14.625, 0, 10,
                           price_history=(14.625, 12.5, 13.0, 14.0, 15.0, 16.0)),
                StockAsset(1, "Held", "HLD", 88.0, 4, 10, last_bought_price=80.0,
                           price_history=(88.0, 94.0, 93.0, 92.0, 90.0, 88.0)),
                StockAsset(2, "Ignored", "IGN", 30.0, 0, 10,
                           price_history=(30.0, 29.0, 28.0, 27.0, 26.0, 25.0)),
            ),
        )
        after = StockMarketSnapshot(status=status, tick=100, assets=before.assets)
        bridge = AutomationBridge([before, after])
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = MarketHistoryStore(Path(temporary_directory) / "history.json")
            result = StockMarketAutomation(bridge, history_store=store).run_cycle(20.0, 80.0, 5)

        self.assertIsInstance(result, StockMarketAutomationResult)
        self.assertEqual(bridge.calls, [("sell", 1), ("buy", 0)])
        self.assertEqual(len(result.orders), 2)
        self.assertEqual(result.signals[0].trend_direction, "falling")
        self.assertEqual(result.signals[0].current_move, "rising")
        self.assertAlmostEqual(result.signals[0].current_move_percent, 17.0)
        self.assertEqual(result.signals[1].trend_direction, "rising")
        self.assertEqual(result.signals[1].current_move, "falling")

    def test_cycle_does_not_trade_when_market_is_unavailable(self):
        snapshot = StockMarketSnapshot(StockMarketStatus(False, False, "indisponível"))
        bridge = AutomationBridge([snapshot])

        result = StockMarketAutomation(bridge).run_cycle(20.0, 80.0)

        self.assertEqual(bridge.calls, [])
        self.assertEqual(result.orders, ())

    def test_cycle_requires_the_configured_number_of_history_points(self):
        status = StockMarketStatus(True, True, "disponível")
        snapshot = StockMarketSnapshot(
            status=status, tick=100,
            assets=(StockAsset(0, "Low", "LOW", 12.5, 0, 10, price_history=(12.5, 12.0)),),
        )
        bridge = AutomationBridge([snapshot])
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = MarketHistoryStore(Path(temporary_directory) / "history.json")
            result = StockMarketAutomation(bridge, history_store=store).run_cycle(20.0, 80.0, 5)

        self.assertFalse(result.signals[0].is_entry_candidate)
        self.assertEqual(result.signals[0].trend_direction, "insufficient")
        self.assertEqual(result.signals[0].trend_ticks, 1)
        self.assertEqual(bridge.calls, [])

    def test_cycle_waits_while_low_keeps_falling_and_high_keeps_rising(self):
        status = StockMarketStatus(True, True, "disponível")
        snapshot = StockMarketSnapshot(
            status=status, tick=100, broker_overhead=1.0,
            assets=(
                StockAsset(0, "Low", "LOW", 11.0, 0, 10,
                           price_history=(11.0, 12.0, 14.0, 15.0, 16.0, 18.0, 20.0)),
                StockAsset(1, "Held", "HLD", 96.0, 3, 10, last_bought_price=70.0,
                           price_history=(96.0, 95.0, 93.0, 92.0, 90.0, 88.0, 86.0)),
            ),
        )
        bridge = AutomationBridge([snapshot])
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = StockMarketAutomation(
                bridge, MarketHistoryStore(Path(temporary_directory) / "history.json")
            ).run_cycle(20.0, 80.0, 5)

        self.assertFalse(result.signals[0].is_entry_candidate)
        self.assertEqual(result.signals[0].decision_reason, "aguardando alta de pelo menos 5.00% antes de comprar")
        self.assertFalse(result.signals[1].is_exit_candidate)
        self.assertEqual(result.signals[1].decision_reason, "aguardando queda de pelo menos 5.00% antes de vender")
        self.assertEqual(bridge.calls, [])

    def test_cycle_never_sells_below_purchase_cost_including_overhead(self):
        status = StockMarketStatus(True, True, "disponível")
        snapshot = StockMarketSnapshot(
            status=status, tick=100, broker_overhead=1.02,
            assets=(StockAsset(1, "Held", "HLD", 81.0, 3, 10, last_bought_price=80.0,
                               price_history=(81.0, 86.0, 83.0, 81.0, 80.5, 80.0)),),
        )
        bridge = AutomationBridge([snapshot])
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = StockMarketAutomation(
                bridge, MarketHistoryStore(Path(temporary_directory) / "history.json")
            ).run_cycle(20.0, 80.0, 5)

        held_signal = result.signals[0]
        self.assertFalse(held_signal.is_exit_candidate)
        self.assertAlmostEqual(held_signal.exit_target, 81.6)
        self.assertEqual(held_signal.decision_reason, "venda bloqueada abaixo do custo pago")
        self.assertEqual(bridge.calls, [])


class StockMarketPerformanceTests(unittest.TestCase):
    def test_profit_per_hour_uses_initial_and_current_market_value(self):
        status = StockMarketStatus(True, True, "disponível")
        initial = StockMarketSnapshot(
            status=status, profit=10.0,
            assets=(StockAsset(0, "Low", "LOW", 2.0, 5, 10),),
        )
        current = StockMarketSnapshot(
            status=status, profit=16.0,
            assets=(StockAsset(0, "Low", "LOW", 3.0, 5, 10),),
        )
        tracker = StockMarketPerformanceTracker()

        self.assertEqual(tracker.observe(initial, now=100.0), 0.0)
        self.assertEqual(tracker.observe(current, now=460.0), 110.0)


class MarketHistoryStoreTests(unittest.TestCase):
    def test_history_is_compact_persistent_and_deduplicated_per_session(self):
        snapshot = StockMarketSnapshot(
            status=StockMarketStatus(True, True, "disponível"),
            tick=10,
            seconds_per_tick=60.0,
            game_seed="save-1",
            assets=(StockAsset(3, "Sugar", "SUG", 20.0, 0, 10, price_history=(20.0, 18.0)),),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            history_path = Path(temporary_directory) / "market_history.json"
            store = MarketHistoryStore(history_path)

            self.assertEqual(store.record_snapshot(snapshot), 2)
            self.assertEqual(store.record_snapshot(snapshot), 0)
            self.assertTrue(history_path.exists())
            self.assertEqual(store.prices_for(3), (20.0, 18.0))

            restored = MarketHistoryStore(history_path)
            self.assertEqual(restored.prices_for(3), (20.0, 18.0))
            self.assertEqual(restored.record_snapshot(snapshot), 0)


if __name__ == "__main__":
    unittest.main()
