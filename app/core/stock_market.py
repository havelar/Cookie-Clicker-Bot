"""Estratégia única baseada em preço absoluto e tendência do Stock Market."""
import math
from dataclasses import replace
from typing import List, Optional, Sequence

from app.bridge.js_bridge import CookieClickerBridge
from app.core.market_history import MarketHistoryStore
from app.core.stock_policy import GASEOUS_ASSETS_TARGET, asset_limits
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
    TRAILING_STOP_PERCENT = 10.0

    def __init__(self, bridge: CookieClickerBridge,
                 history_store: Optional[MarketHistoryStore] = None):
        self.bridge = bridge
        self.history_store = history_store or MarketHistoryStore()
        self._last_analyzed_tick: int | None = None
        self._last_game_seed: Optional[str] = None
        self._performance = StockMarketPerformanceTracker()
        self._logged_blocked_sales: set[int] = set()

    def total_profit(self, snapshot) -> Optional[float]:
        """Retorna a diferença entre o valor atual e o inicial da sessão."""
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
        owned_only_view: bool = False,
        *,
        per_asset_limits: Optional[dict] = None,
        use_reference_prices: bool = True,
        buy_on_discount: bool = True,
    ) -> StockMarketAutomationResult:
        """Analisa uma vez por tick e, quando autorizado, envia ordens MAX."""
        snapshot = self.capture_snapshot()
        if not snapshot.status.available:
            return StockMarketAutomationResult(snapshot=snapshot)

        tick = snapshot.tick
        if snapshot.game_seed != self._last_game_seed:
            self._last_analyzed_tick = None
            self._last_game_seed = snapshot.game_seed
        if tick is not None and tick == self._last_analyzed_tick:
            return StockMarketAutomationResult(snapshot=snapshot)
        if tick is not None:
            if self._last_analyzed_tick is not None and tick < self._last_analyzed_tick:
                logger.info("Stock Market: contador de ticks reiniciado; análise recalibrada")
            self._last_analyzed_tick = tick

        window = max(2, int(trend_ticks))
        overhead = max(1.0, float(snapshot.broker_overhead or 1.0))
        limits = {
            asset.asset_id: asset_limits(asset, buy_price_limit, sell_price_limit,
                                         per_asset_limits, use_reference_prices)
            for asset in snapshot.assets
        }
        position_peaks = {
            asset.asset_id: self.history_store.observe_position_peak(asset, limits[asset.asset_id][1])
            for asset in snapshot.assets
        }
        signals = tuple(
            self._analyze_asset(
                asset,
                asset.price_history or (asset.price,),
                *limits[asset.asset_id],
                window,
                reversal_percent,
                overhead,
                position_peaks[asset.asset_id],
                self.history_store.purchase_cost(asset),
                buy_on_discount,
            )
            for asset in snapshot.assets
        )
        # O achievement considera o saldo do jogo, não o valor de posições abertas.
        # Se a liquidação lucrativa alcança a meta, não espera novos picos.
        safe_assets = {
            asset.asset_id: asset for asset, signal in zip(snapshot.assets, signals)
            if asset.owned > 0 and signal.exit_target is not None and asset.price > signal.exit_target
        }
        goal_reachable = (
            not snapshot.gaseous_assets_won and snapshot.profit is not None
            and snapshot.profit < GASEOUS_ASSETS_TARGET
            and snapshot.profit + sum(asset.price * asset.owned for asset in safe_assets.values())
            >= GASEOUS_ASSETS_TARGET
        )
        if goal_reachable:
            signals = tuple(
                replace(signal, is_exit_candidate=True, decision_reason="realizar lucro para Gaseous assets")
                if signal.asset_id in safe_assets else signal for signal in signals
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
                order = self.bridge.sell_stock_max(
                    signal.asset_id, minimum_price=signal.exit_target,
                    expected_purchase_price=signal.purchase_price,
                )
                orders.append(order)
                self._log_trade("venda", signal, order)
                if order.success and order.stock_after == 0:
                    self.history_store.clear_position_peak(signal.asset_id)
                    self.history_store.clear_position_cost(signal.asset_id)
            if orders and goal_reachable:
                snapshot = self.bridge.get_stock_market_snapshot()
            goal_complete = snapshot.gaseous_assets_won or (
                snapshot.profit is not None and snapshot.profit >= GASEOUS_ASSETS_TARGET
            )
            if not goal_complete and not goal_reachable:
                for signal in sorted(entries, key=lambda item: item.price):
                    order = self.bridge.buy_stock_max(
                        signal.asset_id, price_limit=limits[signal.asset_id][0], require_empty=True,
                    )
                    orders.append(order)
                    self.history_store.record_purchase(order)
                    self._log_trade("compra", signal, order)
            self._log_newly_blocked_sales(blocked)
            if orders and not goal_reachable:
                snapshot = self.bridge.get_stock_market_snapshot()
        else:
            self._logged_blocked_sales.clear()

        if owned_only_view:
            self.bridge.set_stock_market_owned_only_view(True)

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
        position_peak: Optional[float],
        purchase_cost: Optional[float],
        buy_on_discount: bool = True,
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
        minimum_sale_price = purchase_cost
        reversal_entry = (
            has_complete_window and trend == "falling" and current_move == "rising"
            and current_move_percent is not None and current_move_percent >= required_move
        )
        entry = (
            asset.owned == 0
            and asset.price < buy_price_limit
            and asset.capacity is not None and asset.capacity > 0
            and sell_price_limit * (1 - cls.TRAILING_STOP_PERCENT / 100) > asset.price * broker_overhead
            and (buy_on_discount or reversal_entry)
        )
        above_sale_limit = asset.owned > 0 and asset.price > sell_price_limit
        sell_is_safe = minimum_sale_price is not None and asset.price > minimum_sale_price
        drawdown_percent = (
            ((asset.price / position_peak) - 1) * 100
            if position_peak is not None and position_peak > 0 else None
        )
        trailing_stop_triggered = (
            asset.owned > 0
            and drawdown_percent is not None
            and drawdown_percent <= (-cls.TRAILING_STOP_PERCENT + 1e-9)
        )
        regular_exit_triggered = (
            above_sale_limit
            and has_complete_window
            and trend == "rising"
            and current_move == "falling"
            and current_move_percent is not None
            and current_move_percent <= -required_move
        )
        exit_candidate = (
            (regular_exit_triggered or trailing_stop_triggered)
            and sell_is_safe
        )

        if entry:
            reason = f"preço abaixo do limite de ${buy_price_limit:.2f}"
        elif trailing_stop_triggered and sell_is_safe:
            reason = f"queda de {drawdown_percent:+.2f}% desde o pico de ${position_peak:.2f}"
        elif exit_candidate:
            reason = f"acima de ${sell_price_limit:.2f}; queda de {current_move_percent:+.2f}%"
        elif (regular_exit_triggered or trailing_stop_triggered) and not sell_is_safe:
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
            peak_price=position_peak,
            peak_drawdown_percent=drawdown_percent,
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
                cost_detail = (f"${signal.price:.2f} ainda não supera o custo de ${signal.exit_target:.2f}"
                               if signal.exit_target is not None else "custo da posição não confirmado")
                logger.info(
                    f"Mercado: venda de {signal.symbol} bloqueada — {cost_detail}."
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
                trailing_detail = f"; {signal.decision_reason}" if signal.decision_reason else ""
                logger.info(
                    f"Mercado: vendeu máximo de {signal.symbol} a ${signal.price:.2f} "
                    f"(comprado a ${signal.purchase_price:.2f}{trailing_detail})."
                )
            return
        logger.warning(
            f"Mercado: não foi possível {action} {signal.symbol}: {order.message}."
        )


class StockMarketPerformanceTracker:
    """Mede o lucro total do mercado desde o primeiro snapshot da sessão."""

    def __init__(self):
        self._initial_value: Optional[float] = None

    def observe(self, snapshot) -> Optional[float]:
        """Calcula valor final menos valor inicial, incluindo posições abertas."""
        value = self._market_value(snapshot)
        if value is None:
            return None
        if self._initial_value is None:
            self._initial_value = value
            return 0.0
        return value - self._initial_value

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
