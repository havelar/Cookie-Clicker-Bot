"""Limites por ativo, baseados no preço de referência do jogo."""
import math
from typing import Mapping

def valid_limits(value) -> bool:
    if not isinstance(value, dict):
        return False
    buy, sell = value.get("buy"), value.get("sell")
    return all(
        isinstance(number, (int, float)) and not isinstance(number, bool)
        and math.isfinite(number) and number > 0 for number in (buy, sell)
    ) and buy < sell


def asset_limits(asset, buy_limit: float, sell_limit: float,
                 overrides: Mapping | None = None,
                 use_reference_prices: bool = True) -> tuple[float, float]:
    custom = (overrides or {}).get(str(asset.asset_id))
    if valid_limits(custom):
        return float(custom["buy"]), float(custom["sell"])
    reference = asset.resting_value
    if use_reference_prices and reference is not None and math.isfinite(reference) and reference > 0:
        return reference * 0.5, reference
    return buy_limit, sell_limit
