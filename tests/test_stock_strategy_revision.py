"""Regressões da estratégia de desconto, custos reais e meta do achievement."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from app.core.market_history import MarketHistoryStore
from app.core.stock_market import StockMarketAutomation
from app.core.stock_policy import GASEOUS_ASSETS_TARGET, asset_limits
from app.models.stock_market import StockAsset, StockMarketSnapshot, StockMarketStatus, StockTradeResult


AVAILABLE = StockMarketStatus(True, True, "Disponível")


def snapshot(*assets, tick=100, overhead=1.0, profit=0.0, won=False, seed="test-save"):
    return StockMarketSnapshot(
        AVAILABLE, broker_overhead=overhead, profit=profit, tick=tick,
        game_seed=seed, assets=assets, gaseous_assets_won=won,
    )


class RevisionBridge:
    def __init__(self, snapshots, orders=()):
        self.snapshots = list(snapshots)
        self.orders = list(orders)
        self.calls = []
        self.current = None

    def get_stock_market_snapshot(self):
        self.current = self.snapshots.pop(0)
        return self.current

    def _order(self, side, asset_id, guards):
        self.calls.append((side, asset_id, guards))
        if self.orders:
            return self.orders.pop(0)
        asset = next(asset for asset in self.current.assets if asset.asset_id == asset_id)
        quantity = asset.capacity - asset.owned if side == "buy" else asset.owned
        overhead = self.current.broker_overhead if side == "buy" else 1.0
        return StockTradeResult(
            True, side, asset_id, 10_000, quantity, "Executada",
            stock_before=asset.owned, stock_after=asset.capacity if side == "buy" else 0,
            unit_price=asset.price, total_value=asset.price * overhead * quantity,
            is_maximum_order=True,
        )

    def buy_stock_max(self, asset_id, **guards):
        return self._order("buy", asset_id, guards)

    def sell_stock_max(self, asset_id, **guards):
        return self._order("sell", asset_id, guards)


class StockStrategyRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "history.json"

    def automation(self, bridge):
        return StockMarketAutomation(bridge, MarketHistoryStore(self.path))

    def test_discount_buys_max_without_waiting_for_history_or_reversal(self):
        empty = StockAsset(0, "Cereals", "CRL", 10, 0, 100)
        falling = StockAsset(1, "Chocolate", "CHC", 15, 0, 100, price_history=(15, 16, 17))
        before = snapshot(empty, falling)
        bridge = RevisionBridge([before, before])

        result = self.automation(bridge).run_cycle(20, 80)

        self.assertEqual(bridge.calls, [
            ("buy", 0, {"price_limit": 20, "require_empty": True}),
            ("buy", 1, {"price_limit": 20, "require_empty": True}),
        ])
        self.assertTrue(all(order.is_maximum_order for order in result.orders))

    def test_custom_limits_override_reference_and_global_limits(self):
        asset = StockAsset(7, "Chocolate", "CHC", 40, 0, 100, resting_value=100)
        self.assertEqual(asset_limits(asset, 20, 80), (50, 100))
        self.assertEqual(asset_limits(asset, 20, 80, use_reference_prices=False), (20, 80))
        overrides = {"7": {"buy": 45, "sell": 70}}
        self.assertEqual(asset_limits(asset, 20, 80, overrides), (45, 70))
        self.assertEqual(asset_limits(asset, 20, 80, overrides, False), (45, 70))
        before = snapshot(asset)
        bridge = RevisionBridge([before, before])

        self.automation(bridge).run_cycle(20, 80, per_asset_limits=overrides)

        self.assertEqual(bridge.calls, [("buy", 7, {"price_limit": 45, "require_empty": True})])

    def test_reference_limits_allow_discount_on_a_higher_value_asset(self):
        asset = StockAsset(7, "Chocolate", "CHC", 40, 0, 100, resting_value=100)
        before = snapshot(asset)
        bridge = RevisionBridge([before, before])

        self.automation(bridge).run_cycle(20, 80)

        self.assertEqual(bridge.calls, [("buy", 7, {"price_limit": 50, "require_empty": True})])

    def test_paid_overhead_survives_restart_and_blocks_break_even_sales(self):
        empty = StockAsset(0, "Cereals", "CRL", 20, 0, 10)
        held = replace(empty, owned=10, last_bought_price=20)
        purchase_bridge = RevisionBridge([snapshot(empty, overhead=1.2), snapshot(held, overhead=1.2)])
        self.automation(purchase_bridge).run_cycle(30, 30)
        restored = MarketHistoryStore(self.path)
        self.assertEqual(restored.purchase_cost(held), 24)
        peak = replace(held, price=30)
        below_cost = replace(held, price=21)
        at_cost = replace(held, price=24)
        profitable = replace(held, price=24.1)
        bridge = RevisionBridge([
            snapshot(peak, tick=101), snapshot(below_cost, tick=102), snapshot(at_cost, tick=103),
            snapshot(profitable, tick=104), snapshot(replace(profitable, owned=0), tick=104),
        ])
        automation = StockMarketAutomation(bridge, restored)
        automation.run_cycle(30, 30, execute_orders=False)
        first = automation.run_cycle(30, 30)
        equal = automation.run_cycle(30, 30)
        self.assertFalse(first.signals[0].is_exit_candidate)
        self.assertFalse(equal.signals[0].is_exit_candidate)
        self.assertEqual(first.signals[0].exit_target, 24)
        self.assertEqual(bridge.calls, [])

        sold = automation.run_cycle(30, 30)

        self.assertTrue(sold.signals[0].is_exit_candidate)
        self.assertEqual(bridge.calls, [
            ("sell", 0, {"minimum_price": 24, "expected_purchase_price": 20}),
        ])

    def test_goal_liquidates_profitable_stock_without_trend_and_does_not_rebuy(self):
        held = StockAsset(0, "Cereals", "CRL", 15, 10, 10, last_bought_price=5)
        cheap = StockAsset(1, "Chocolate", "CHC", 10, 0, 10)
        before = snapshot(held, cheap, profit=GASEOUS_ASSETS_TARGET - 150)
        after = snapshot(replace(held, owned=0), cheap, profit=GASEOUS_ASSETS_TARGET, won=True)
        bridge = RevisionBridge([before, after])

        result = self.automation(bridge).run_cycle(20, 80)

        self.assertEqual([call[0:2] for call in bridge.calls], [("sell", 0)])
        self.assertIn("Gaseous assets", result.signals[0].decision_reason)
        self.assertEqual(result.snapshot.profit, 31_536_000)

    def test_completed_goal_does_not_open_new_positions(self):
        cheap = StockAsset(0, "Cereals", "CRL", 10, 0, 10)
        for profit, won in ((GASEOUS_ASSETS_TARGET, False), (10, True)):
            with self.subTest(profit=profit, won=won):
                bridge = RevisionBridge([snapshot(cheap, profit=profit, won=won)])
                self.automation(bridge).run_cycle(20, 80)
                self.assertEqual(bridge.calls, [])

    def test_auto_off_only_analyzes_even_when_goal_can_be_reached(self):
        held = StockAsset(0, "Cereals", "CRL", 15, 10, 10, last_bought_price=5)
        cheap = StockAsset(1, "Chocolate", "CHC", 10, 0, 10)
        bridge = RevisionBridge([snapshot(held, cheap, profit=GASEOUS_ASSETS_TARGET - 150)])

        result = self.automation(bridge).run_cycle(20, 80, execute_orders=False)

        self.assertTrue(result.signals[0].is_exit_candidate)
        self.assertTrue(result.signals[1].is_entry_candidate)
        self.assertEqual(bridge.calls, [])

    def test_unavailable_market_does_not_trade(self):
        bridge = RevisionBridge([StockMarketSnapshot(StockMarketStatus(False, False, "Indisponível"))])

        result = self.automation(bridge).run_cycle(20, 80)

        self.assertEqual(result.orders, ())
        self.assertEqual(bridge.calls, [])

    def test_peak_arms_at_custom_sell_limit_and_only_clears_after_complete_sale(self):
        held = StockAsset(0, "Cereals", "CRL", 90, 10, 10, last_bought_price=10)
        peak = replace(held, price=100)
        partial = replace(held, owned=4)
        partial_order = StockTradeResult(
            True, "sell", 0, 10_000, 6, "Parcial", stock_before=10,
            stock_after=4, unit_price=90, total_value=540, is_maximum_order=True,
        )
        bridge = RevisionBridge([
            snapshot(held), snapshot(peak, tick=101), snapshot(held, tick=102),
            snapshot(partial, tick=102), snapshot(partial, tick=103),
            snapshot(replace(partial, owned=0), tick=103),
        ], orders=[partial_order])
        automation = self.automation(bridge)
        options = {"per_asset_limits": {"0": {"buy": 20, "sell": 100}}}
        first = automation.run_cycle(20, 80, **options)
        self.assertIsNone(first.signals[0].peak_price)
        second = automation.run_cycle(20, 80, **options)
        self.assertEqual(second.signals[0].peak_price, 100)
        automation.run_cycle(20, 80, **options)
        restored = MarketHistoryStore(self.path)
        self.assertEqual(restored.observe_position_peak(partial, 100), 100)

        automation.run_cycle(20, 80, **options)

        self.assertEqual([call[0:2] for call in bridge.calls], [("sell", 0), ("sell", 0)])
        self.assertIsNone(MarketHistoryStore(self.path).observe_position_peak(held, 100))


if __name__ == "__main__":
    unittest.main()
