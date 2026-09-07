"""Estratégia temporal configurável para o Stock Market."""
from typing import List

from app.bridge.js_bridge import CookieClickerBridge
from app.models.stock_market import StockMarketAutomationResult, StockTradeResult
from app.utils.logger import logger


class StockMarketAutomation:
    """Executa regras simples sem acoplar a política à interface Qt."""

    def __init__(self, bridge: CookieClickerBridge):
        self.bridge = bridge

    def run_cycle(self, buy_price_limit: float, sell_price_limit: float) -> StockMarketAutomationResult:
        """Lê o mercado e aplica as ordens máximas autorizadas pela regra atual."""
        snapshot = self.bridge.get_stock_market_snapshot()
        if not snapshot.status.available:
            return StockMarketAutomationResult(snapshot=snapshot)

        orders: List[StockTradeResult] = []
        for asset in sorted(snapshot.assets, key=lambda item: item.price):
            if asset.owned == 0 and asset.price < buy_price_limit:
                orders.append(self.bridge.buy_stock_max(asset.asset_id))
            elif asset.owned > 0 and asset.price > sell_price_limit:
                orders.append(self.bridge.sell_stock_max(asset.asset_id))

        if orders:
            successful = sum(order.success for order in orders)
            logger.info(
                "Stock Market: ciclo automático concluído "
                f"({successful}/{len(orders)} ordens aceitas)"
            )
            snapshot = self.bridge.get_stock_market_snapshot()
        return StockMarketAutomationResult(snapshot=snapshot, orders=tuple(orders))
