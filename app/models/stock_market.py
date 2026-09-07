"""Modelos tipados para leitura e operações manuais do Stock Market."""
from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class StockMarketStatus:
    """Disponibilidade do minigame no runtime atual."""

    available: bool
    unlocked: bool
    message: str


@dataclass(frozen=True)
class StockAsset:
    """Estado de um ativo em um instante do mercado."""

    asset_id: int
    name: str
    symbol: Optional[str]
    price: float
    owned: int
    capacity: Optional[int]
    price_change_percent: Optional[float] = None


@dataclass(frozen=True)
class StockMarketSnapshot:
    """Snapshot imutável que pode ser consumido por UI ou estratégias futuras."""

    status: StockMarketStatus
    cookies: Optional[float] = None
    highest_raw_cps: Optional[float] = None
    trading_funds: Optional[float] = None
    brokers: Optional[int] = None
    broker_overhead: Optional[float] = None
    profit: Optional[float] = None
    assets: Tuple[StockAsset, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class StockTradeResult:
    """Resultado verificável de uma ordem manual."""

    success: bool
    side: str
    asset_id: int
    requested_quantity: int
    executed_quantity: int
    message: str
    stock_before: Optional[int] = None
    stock_after: Optional[int] = None
    unit_price: Optional[float] = None
    total_value: Optional[float] = None
    is_maximum_order: bool = False


@dataclass(frozen=True)
class StockMarketAutomationResult:
    """Resultado de um ciclo temporal de leitura e ordens da estratégia simples."""

    snapshot: StockMarketSnapshot
    orders: Tuple[StockTradeResult, ...] = field(default_factory=tuple)
