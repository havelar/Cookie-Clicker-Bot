"""Estratégia única baseada em preço absoluto e tendência do Stock Market."""
import math
import time
from typing import List, Optional, Sequence

from app.bridge.js_bridge import CookieClickerBridge
from app.core.market_history import MarketHistoryStore
from app.models.stock_market import (
    StockAsset,
    StockMarketAutomationResult,
    StockMarketSignal,
    StockTradeResult,
)
from app.utils.logger import logger


class StockMarketAutomation:
    """Compra barato durante baixa e vende caro durante alta confirmada."""

    TREND_MAJORITY_RATIO = 0.6

    def __init__(self, bridge: CookieClickerBridge,
                 history_store: Optional[MarketHistoryStore] = None):
        self.bridge = bridge
        self.history_store = history_store or MarketHistoryStore()
        self._last_analyzed_tick: int | None = None
        self._performance = StockMarketPerformanceTracker()
        self._logged_blocked_sales: set[int] = set()

    def profit_per_hour(self, snapshot) -> Optional[float]:
        """Retorna o resultado de mercado por hora desde o início da sessão."""
        return self._performance.observe(snapshot)

    def capture_snapshot(self):
        """Lê o runtime e persiste pontos novos, independentemente do Auto."""
        snapshot = self.bridge.get_stock_market_snapshot()
        if snapshot.status.available:
            self._record_history(snapshot)
        return snapshot

    def run_cycle(
        self,
        buy_price_limit: float,
        sell_price_limit: float,
        trend_ticks: int = 5,
        reversal_percent: float = 5.0,
        execute_orders: bool = True,
    ) -> StockMarketAutomationResult:
        """Analisa uma vez por tick e, quando autorizado, envia ordens MAX."""
        snapshot = self.capture_snapshot()
        if not snapshot.status.available:
            return StockMarketAutomationResult(snapshot=snapshot)

        tick = snapshot.tick
        if tick is not None and tick == self._last_analyzed_tick:
            return StockMarketAutomationResult(snapshot=snapshot)
        if tick is not None:
            if self._last_analyzed_tick is not None and tick < self._last_analyzed_tick:
                logger.info("Stock Market: contador de ticks reiniciado; análise recalibrada")
            self._last_analyzed_tick = tick

        window = max(2, int(trend_ticks))
        overhead = max(1.0, float(snapshot.broker_overhead or 1.0))
        signals = tuple(
            self._analyze_asset(
                asset,
                self.history_store.prices_for(asset.asset_id, asset.price_history),
                buy_price_limit,
                sell_price_limit,
                window,
                reversal_percent,
                overhead,
            )
            for asset in snapshot.assets
        )
        entries = [signal for signal in signals if signal.is_entry_candidate]
        exits = [signal for signal in signals if signal.is_exit_candidate]
        blocked = [
            signal for signal in signals
            if signal.decision_reason == "venda bloqueada abaixo do custo pago"
        ]

        orders: List[StockTradeResult] = []
        if execute_orders:
            for signal in exits:
                order = self.bridge.sell_stock_max(signal.asset_id)
                orders.append(order)
                self._log_trade("venda", signal, order)
            for signal in sorted(entries, key=lambda item: item.price):
                order = self.bridge.buy_stock_max(signal.asset_id)
                orders.append(order)
                self._log_trade("compra", signal, order)
            self._log_newly_blocked_sales(blocked)
            if orders:
                snapshot = self.bridge.get_stock_market_snapshot()
        else:
            self._logged_blocked_sales.clear()

        return StockMarketAutomationResult(
            snapshot=snapshot,
            orders=tuple(orders),
            signals=signals,
            tick_changed=True,
        )

    @classmethod
    def _analyze_asset(
        cls,
        asset: StockAsset,
        price_history: Sequence[float],
        buy_price_limit: float,
        sell_price_limit: float,
        trend_ticks: int,
        reversal_percent: float,
        broker_overhead: float,
    ) -> StockMarketSignal:
        # Os X pontos anteriores definem a tendência; o preço atual deve
        # inverter com força suficiente para evitar reagir a ruído pequeno.
        sample = tuple(float(price) for price in price_history[:trend_ticks + 1])
        previous_window = sample[1:]
        trend = cls._general_trend(previous_window)
        has_complete_window = len(sample) == trend_ticks + 1
        current_move = cls._confirmed_reversal(sample)
        current_move_percent = cls._current_move_percent(sample)
        required_move = abs(float(reversal_percent))
        purchase_price = (
            asset.last_bought_price
            if asset.last_bought_price is not None and asset.last_bought_price > 0
            else None
        )
        minimum_sale_price = (
            purchase_price * broker_overhead if purchase_price is not None else None
        )
        entry = (
            asset.owned == 0
            and asset.price < buy_price_limit
            and has_complete_window
            and trend == "falling"
            and current_move == "rising"
            and current_move_percent is not None
            and current_move_percent >= required_move
        )
        above_sale_limit = asset.owned > 0 and asset.price > sell_price_limit
        sell_is_safe = minimum_sale_price is not None and asset.price >= minimum_sale_price
        exit_candidate = (
            above_sale_limit
            and has_complete_window
            and trend == "rising"
            and current_move == "falling"
            and current_move_percent is not None
            and current_move_percent <= -required_move
            and sell_is_safe
        )

        if entry:
            reason = f"abaixo de ${buy_price_limit:.2f}; alta de {current_move_percent:+.2f}%"
        elif exit_candidate:
            reason = f"acima de ${sell_price_limit:.2f}; queda de {current_move_percent:+.2f}%"
        elif (
            above_sale_limit and has_complete_window and trend == "rising"
            and current_move == "falling"
            and current_move_percent is not None
            and current_move_percent <= -required_move
            and not sell_is_safe
        ):
            reason = "venda bloqueada abaixo do custo pago"
        elif asset.owned == 0 and asset.price < buy_price_limit and trend == "falling":
            reason = f"aguardando alta de pelo menos {required_move:.2f}% antes de comprar"
        elif above_sale_limit and trend == "rising":
            reason = f"aguardando queda de pelo menos {required_move:.2f}% antes de vender"
        else:
            reason = None

        return StockMarketSignal(
            asset_id=asset.asset_id,
            symbol=asset.name,
            price=asset.price,
            change_percent=asset.price_change_percent,
            is_entry_candidate=entry,
            exit_target=minimum_sale_price,
            is_exit_candidate=exit_candidate,
            trend_direction=trend,
            trend_ticks=len(previous_window),
            current_move=current_move,
            current_move_percent=current_move_percent,
            purchase_price=purchase_price,
            decision_reason=reason,
        )

    @classmethod
    def _general_trend(cls, newest_first: Sequence[float]) -> str:
        """Classifica tendência pelo sentido total e maioria dos movimentos."""
        if len(newest_first) < 2:
            return "insufficient"
        movements = len(newest_first) - 1
        required = max(1, math.ceil(movements * cls.TREND_MAJORITY_RATIO))
        falling_moves = sum(
            newer < older for newer, older in zip(newest_first, newest_first[1:])
        )
        rising_moves = sum(
            newer > older for newer, older in zip(newest_first, newest_first[1:])
        )
        if newest_first[0] < newest_first[-1] and falling_moves >= required:
            return "falling"
        if newest_first[0] > newest_first[-1] and rising_moves >= required:
            return "rising"
        return "sideways"

    @staticmethod
    def _confirmed_reversal(newest_first: Sequence[float]) -> str:
        """Retorna a direção da variação mais recente."""
        if len(newest_first) < 2:
            return "flat"
        if newest_first[0] > newest_first[1]:
            return "rising"
        if newest_first[0] < newest_first[1]:
            return "falling"
        return "flat"

    @staticmethod
    def _current_move_percent(newest_first: Sequence[float]) -> Optional[float]:
        if len(newest_first) < 2 or newest_first[1] <= 0:
            return None
        return ((newest_first[0] / newest_first[1]) - 1) * 100

    def _record_history(self, snapshot) -> None:
        added_points = self.history_store.record_snapshot(snapshot)
        if added_points:
            logger.debug(
                "Stock Market histórico: "
                f"{added_points} pontos salvos ({self.history_store.point_count()} no total)"
            )

    def _log_newly_blocked_sales(self, blocked: Sequence[StockMarketSignal]) -> None:
        blocked_ids = {signal.asset_id for signal in blocked}
        for signal in blocked:
            if signal.asset_id not in self._logged_blocked_sales:
                logger.info(
                    f"Mercado: venda de {signal.symbol} bloqueada — "
                    f"${signal.price:.2f} ainda não cobre o custo de ${signal.exit_target:.2f}."
                )
        self._logged_blocked_sales = blocked_ids

    @staticmethod
    def _log_trade(action: str, signal: StockMarketSignal, order: StockTradeResult) -> None:
        if order.success:
            if action == "compra":
                logger.info(
                    f"Mercado: comprou máximo de {signal.symbol} a ${signal.price:.2f}."
                )
            else:
                logger.info(
                    f"Mercado: vendeu máximo de {signal.symbol} a ${signal.price:.2f} "
                    f"(comprado a ${signal.purchase_price:.2f})."
                )
            return
        logger.warning(
            f"Mercado: não foi possível {action} {signal.symbol}: {order.message}."
        )


class StockMarketPerformanceTracker:
    """Mede o valor do mercado desde o primeiro snapshot desta sessão."""

    def __init__(self):
        self._initial_value: Optional[float] = None
        self._started_at: Optional[float] = None

    def observe(self, snapshot, now: Optional[float] = None) -> Optional[float]:
        """Calcula $/h de lucro realizado mais valor atual das posições."""
        value = self._market_value(snapshot)
        if value is None:
            return None
        timestamp = time.monotonic() if now is None else now
        if self._initial_value is None or self._started_at is None:
            self._initial_value = value
            self._started_at = timestamp
            return 0.0
        elapsed_seconds = max(0.0, timestamp - self._started_at)
        if elapsed_seconds == 0:
            return 0.0
        return (value - self._initial_value) * 3600 / elapsed_seconds

    @staticmethod
    def _market_value(snapshot) -> Optional[float]:
        if snapshot.profit is None or not math.isfinite(snapshot.profit):
            return None
        positions_value = sum(
            asset.price * asset.owned
            for asset in snapshot.assets
            if math.isfinite(asset.price) and asset.owned >= 0
        )
        return snapshot.profit + positions_value
