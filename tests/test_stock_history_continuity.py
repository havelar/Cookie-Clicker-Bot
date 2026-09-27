"""Regression tests for continuous prices and persisted position state."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.core.market_history import MarketHistoryStore
from app.models.stock_market import (
    StockAsset,
    StockMarketSnapshot,
    StockMarketStatus,
    StockTradeResult,
)


class StockHistoryContinuityTests(unittest.TestCase):
    def setUp(self):
        logger_patch = patch("app.core.market_history.logger")
        logger_patch.start()
        self.addCleanup(logger_patch.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "stock_market_history.json"
        self.store = MarketHistoryStore(self.path)

    @staticmethod
    def asset(price=75.0, history=(), owned=0, purchase_price=None):
        return StockAsset(
            asset_id=0,
            name="Cereals",
            symbol="CRL",
            price=price,
            owned=owned,
            capacity=100,
            price_history=tuple(history),
            last_bought_price=purchase_price,
        )

    def record(self, tick, timestamp, prices=(), seed="save-a", asset=None):
        if asset is None:
            asset = self.asset(price=prices[0], history=prices)
        snapshot = StockMarketSnapshot(
            status=StockMarketStatus(True, True, "available"),
            tick=tick,
            seconds_per_tick=60.0,
            game_seed=seed,
            assets=(asset,),
        )
        with patch("app.core.market_history.time.time", return_value=timestamp):
            return self.store.record_snapshot(snapshot)

    def tracked_position(self):
        asset = self.asset(price=100.0, owned=3, purchase_price=7.0)
        self.record(5, 1_000.0, asset=asset)
        self.store.record_purchase(StockTradeResult(
            success=True,
            side="buy",
            asset_id=0,
            requested_quantity=10_000,
            executed_quantity=3,
            message="Bought maximum",
            stock_before=0,
            stock_after=3,
            unit_price=7.0,
            total_value=24.0,
            is_maximum_order=True,
        ))
        self.assertEqual(self.store.observe_position_peak(asset, 80.0), 100.0)
        self.assertEqual(self.store.purchase_cost(asset), 8.0)

    def write_legacy_history(self):
        self.path.write_text(json.dumps({
            "version": 3,
            "assets": {"0": {
                "symbol": "CRL",
                "points": [
                    [880.0, "save-a", 3, 30.0],
                    [940.0, "save-a", 4, 40.0],
                    [1_000.0, "save-a", 5, 50.0],
                ],
            }},
            "position_peaks": {
                "0": {"purchase_price": 7.0, "peak_price": 120.0},
            },
        }), encoding="utf-8")

    def test_same_seed_counter_reset_records_reused_ticks_after_restart(self):
        self.assertEqual(self.record(5, 1_000.0, (50.0, 40.0, 30.0)), 3)
        self.store = MarketHistoryStore(self.path)

        self.assertEqual(self.record(1, 1_120.0, (7.0, 6.0)), 2)
        self.assertEqual(self.record(3, 1_240.0, (9.0, 8.0, 7.0, 6.0)), 2)
        self.assertEqual(self.record(3, 1_245.0, (9.0, 8.0, 7.0, 6.0)), 0)

        restored = MarketHistoryStore(self.path)
        self.assertEqual(restored.point_count(), 7)
        self.assertEqual(restored.prices_for(0), (9.0, 8.0, 7.0, 6.0))

    def test_native_prices_override_stale_persisted_prices_without_padding(self):
        self.record(5, 1_000.0, (50.0, 40.0, 30.0))
        restored = MarketHistoryStore(self.path)

        self.assertEqual(restored.prices_for(0, (7.0, 6.0)), (7.0, 6.0))
        self.assertEqual(restored.prices_for(0, (7.0,)), (7.0,))

    def test_persisted_prices_stop_at_missing_ticks(self):
        self.record(5, 1_000.0, (50.0, 40.0, 30.0))
        self.record(10, 1_300.0, (100.0, 90.0))

        restored = MarketHistoryStore(self.path)
        self.assertEqual(restored.prices_for(0), (100.0, 90.0))

    def test_persisted_prices_stop_at_source_change_even_if_ticks_are_adjacent(self):
        self.record(5, 1_000.0, (50.0, 40.0, 30.0))
        self.record(6, 1_060.0, (60.0,), seed="save-b")

        restored = MarketHistoryStore(self.path)
        self.assertEqual(restored.prices_for(0), (60.0,))

    def test_restart_and_tick_reset_preserve_same_save_peak_and_executed_cost(self):
        self.tracked_position()
        self.store = MarketHistoryStore(self.path)
        asset = self.asset(price=75.0, owned=3, purchase_price=7.0)

        self.record(1, 1_120.0, asset=asset)

        restored = MarketHistoryStore(self.path)
        self.assertEqual(restored.observe_position_peak(asset, 80.0), 100.0)
        self.assertEqual(restored.purchase_cost(asset), 8.0)

    def test_different_save_discards_peak_and_cost_even_with_same_purchase_price(self):
        self.tracked_position()
        self.store = MarketHistoryStore(self.path)
        asset = self.asset(price=75.0, owned=3, purchase_price=7.0)

        self.record(6, 1_060.0, seed="save-b", asset=asset)

        restored = MarketHistoryStore(self.path)
        self.assertIsNone(restored.observe_position_peak(asset, 80.0))
        self.assertAlmostEqual(restored.purchase_cost(asset), 8.4)

    def test_legacy_migration_records_duplicate_tick_and_preserves_same_save_peak(self):
        self.write_legacy_history()
        asset = self.asset(price=75.0, owned=3, purchase_price=7.0)

        self.assertEqual(self.record(5, 1_120.0, asset=asset), 1)

        restored = MarketHistoryStore(self.path)
        self.assertEqual(restored.point_count(), 4)
        self.assertEqual(restored.prices_for(0), (75.0,))
        self.assertEqual(restored.observe_position_peak(asset, 80.0), 120.0)
        self.assertAlmostEqual(restored.purchase_cost(asset), 8.4)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["version"], 4)

    def test_legacy_migration_discards_peak_when_loading_a_different_save(self):
        self.write_legacy_history()
        asset = self.asset(price=75.0, owned=3, purchase_price=7.0)

        self.record(5, 1_120.0, seed="save-b", asset=asset)

        restored = MarketHistoryStore(self.path)
        self.assertIsNone(restored.observe_position_peak(asset, 80.0))


if __name__ == "__main__":
    unittest.main()
