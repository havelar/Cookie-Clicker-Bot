"""Persistência compacta e tolerante a falhas do histórico do Stock Market."""
import json
import math
import os
from pathlib import Path
import threading
import time
from typing import Dict, Iterable, Optional, Tuple
from uuid import uuid4

from app.models.stock_market import StockMarketSnapshot
from app.utils.logger import logger


class MarketHistoryStore:
    """Mantém uma janela persistente de preços sem gravar durante cada polling."""

    VERSION = 4
    MAX_POINTS_PER_ASSET = 10_080  # aproximadamente sete dias de ticks de um minuto

    def __init__(self, path: Path | str = Path("data") / "stock_market_history.json"):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._loaded = False
        self._session_id = uuid4().hex
        self._assets: Dict[str, Dict[str, object]] = {}
        self._known_points: set[tuple[str, str, int]] = set()
        self._position_peaks: Dict[str, Dict[str, float]] = {}
        self._position_costs: Dict[str, dict] = {}
        self._history_context: dict = {}

    def record_purchase(self, order) -> None:
        """Guarda o custo executado, incluindo a taxa cobrada naquela compra."""
        if not (order.success and order.side == "buy" and order.stock_before == 0
                and order.executed_quantity > 0 and order.total_value is not None
                and math.isfinite(order.total_value) and order.total_value > 0
                and order.unit_price is not None and order.unit_price > 0):
            return
        with self._lock:
            self._load()
            self._position_costs[str(order.asset_id)] = {
                "purchase_price": order.unit_price,
                "unit_cost": order.total_value / order.executed_quantity,
                "quantity": order.executed_quantity,
            }
            self._save()

    def purchase_cost(self, asset) -> Optional[float]:
        """Custo real das compras acompanhadas; teto conservador para lotes antigos."""
        with self._lock:
            self._load()
            position = self._position_costs.get(str(asset.asset_id))
            if asset.owned <= 0:
                if self._position_costs.pop(str(asset.asset_id), None) is not None:
                    self._save()
                return None
            if asset.last_bought_price is None or asset.last_bought_price <= 0:
                return None
            if position:
                # Uma compra adicional desconhecida invalida o custo do lote.
                if (position["purchase_price"] != asset.last_bought_price
                        or asset.owned > position["quantity"]):
                    return None
                return position["unit_cost"]
            # O jogo salva o último preço, mas não a taxa histórica. Para
            # posições anteriores ao rastreio, usa-se a taxa máxima de 20%.
            return asset.last_bought_price * 1.2

    def clear_position_cost(self, asset_id: int) -> None:
        with self._lock:
            self._load()
            if self._position_costs.pop(str(asset_id), None) is not None:
                self._save()

    def observe_position_peak(self, asset, activation_price: float) -> Optional[float]:
        """Registra o pico somente após a posição entrar no modo de venda."""
        with self._lock:
            self._load()
            asset_id = str(asset.asset_id)
            purchase_price = asset.last_bought_price
            if asset.owned <= 0 or purchase_price is None or purchase_price <= 0:
                self.clear_position_peak(asset.asset_id)
                return None

            current_price = float(asset.price)
            position = self._position_peaks.get(asset_id)
            if (
                position is None
                or position.get("purchase_price") != float(purchase_price)
                or position.get("peak_price", 0) < activation_price
            ):
                if current_price < activation_price:
                    if self._position_peaks.pop(asset_id, None) is not None:
                        self._save()
                    return None
                self._position_peaks[asset_id] = {
                    "purchase_price": float(purchase_price),
                    "peak_price": current_price,
                }
                self._save()
                return current_price

            peak_price = max(float(position["peak_price"]), current_price)
            if peak_price != position["peak_price"]:
                position["peak_price"] = peak_price
                self._save()
            return peak_price

    def clear_position_peak(self, asset_id: int) -> None:
        """Remove o pico após a venda para a próxima posição começar limpa."""
        with self._lock:
            self._load()
            if self._position_peaks.pop(str(asset_id), None) is not None:
                self._save()

    def record_snapshot(self, snapshot: StockMarketSnapshot) -> int:
        """Armazena pontos inéditos do tick atual e do histórico nativo disponível."""
        if not snapshot.status.available or snapshot.tick is None:
            return 0
        with self._lock:
            self._load()
            now = time.time()
            seconds = snapshot.seconds_per_tick or 60.0
            seed = snapshot.game_seed or self._session_id
            context = self._history_context
            if context.get("seed") != seed or snapshot.tick < context.get("tick", -1):
                # O jogo reinicia o contador ao recarregar; a seed pode ser igual.
                if context.get("seed") is not None and context.get("seed") != seed:
                    self._position_peaks.clear()
                    self._position_costs.clear()
                context = {"seed": seed, "source": seed + ":" + uuid4().hex}
            context["tick"] = snapshot.tick
            self._history_context = context
            source_id = context["source"]
            added = 0
            for asset in snapshot.assets:
                prices = asset.price_history or (asset.price,)
                entry = self._assets.setdefault(
                    str(asset.asset_id), {"symbol": asset.symbol or asset.name, "points": []}
                )
                entry["symbol"] = asset.symbol or asset.name
                points = entry["points"]
                if not isinstance(points, list):
                    points = []
                    entry["points"] = points
                for offset, price in enumerate(prices):
                    game_tick = snapshot.tick - offset
                    if game_tick < 0:
                        continue
                    key = (str(asset.asset_id), source_id, game_tick)
                    if key in self._known_points:
                        continue
                    points.append([round(now - offset * seconds, 3), source_id, game_tick, price])
                    self._known_points.add(key)
                    added += 1
                points.sort(key=lambda point: point[0])
                if len(points) > self.MAX_POINTS_PER_ASSET:
                    del points[:-self.MAX_POINTS_PER_ASSET]
            if added:
                self._save()
            return added

    def prices_for(self, asset_id: int, fallback: Iterable[float] = ()) -> Tuple[float, ...]:
        """Prioriza ticks nativos; não completa janelas com períodos desconexos."""
        native_prices = tuple(fallback)
        if native_prices:
            return native_prices
        with self._lock:
            self._load()
            entry = self._assets.get(str(asset_id), {})
            points = entry.get("points", []) if isinstance(entry, dict) else []
            prices = []
            source, expected_tick = None, None
            for point in reversed(points):
                if not self._valid_point(point):
                    break
                if source is not None and (point[1] != source or point[2] != expected_tick):
                    break
                prices.append(point[3])
                source, expected_tick = point[1], point[2] - 1
            return tuple(prices)

    def point_count(self) -> int:
        with self._lock:
            self._load()
            return sum(
                len(entry.get("points", [])) for entry in self._assets.values()
                if isinstance(entry, dict)
            )

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as history_file:
                payload = json.load(history_file)
            version = payload.get("version") if isinstance(payload, dict) else None
            if version not in (1, 2, 3, self.VERSION):
                raise ValueError("versão ou estrutura inválida")
            assets = payload.get("assets")
            if not isinstance(assets, dict):
                raise ValueError("ativos inválidos")
            for asset_id, entry in assets.items():
                if not isinstance(asset_id, str) or not isinstance(entry, dict):
                    continue
                points = [point for point in entry.get("points", []) if self._valid_point(point)]
                points.sort(key=lambda point: point[0])
                self._assets[asset_id] = {
                    "symbol": str(entry.get("symbol") or asset_id),
                    "points": points[-self.MAX_POINTS_PER_ASSET:],
                }
                self._known_points.update(
                    (asset_id, point[1], point[2]) for point in self._assets[asset_id]["points"]
                )
            raw_peaks = payload.get("position_peaks", {})
            # Picos v2 foram criados antes da regra de ativação em $80; não
            # são reaproveitados para evitar uma venda baseada no cap antigo.
            if version in (3, self.VERSION) and isinstance(raw_peaks, dict):
                for asset_id, position in raw_peaks.items():
                    if not isinstance(asset_id, str) or not isinstance(position, dict):
                        continue
                    purchase_price, peak_price = position.get("purchase_price"), position.get("peak_price")
                    if (
                        isinstance(purchase_price, (int, float)) and purchase_price > 0
                        and isinstance(peak_price, (int, float)) and peak_price > 0
                    ):
                        self._position_peaks[asset_id] = {
                            "purchase_price": float(purchase_price),
                            "peak_price": float(peak_price),
                        }
            raw_costs = payload.get("position_costs", {})
            for asset_id, cost in (raw_costs.items() if isinstance(raw_costs, dict) else ()):
                if isinstance(cost, dict) and all(
                    isinstance(cost.get(key), (int, float)) and math.isfinite(cost[key]) and cost[key] > 0
                    for key in ("purchase_price", "unit_cost", "quantity")
                ):
                    self._position_costs[asset_id] = cost
            context = payload.get("history_context", {})
            if (isinstance(context, dict) and isinstance(context.get("seed"), str)
                    and isinstance(context.get("source"), str) and isinstance(context.get("tick"), int)):
                self._history_context = context
            elif version < self.VERSION:
                legacy_points = [point for entry in self._assets.values() for point in entry["points"]]
                if legacy_points:
                    last_point = max(legacy_points, key=lambda point: point[0])
                    # Conserva a origem dos picos, mas inaugura um segmento sem
                    # as colisões de ticks dos arquivos anteriores à versão 4.
                    self._history_context = {
                        "seed": last_point[1], "source": last_point[1] + ":" + uuid4().hex,
                        "tick": last_point[2],
                    }
            logger.info(f"Stock Market histórico: {self.point_count()} pontos restaurados")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            logger.warning(f"Stock Market histórico: arquivo ignorado ({error})")
            self._assets = {}
            self._known_points.clear()
            self._position_peaks.clear()
            self._position_costs.clear()
            self._history_context = {}

    def _save(self) -> None:
        payload = {
            "version": self.VERSION,
            "updated_at": round(time.time(), 3),
            "assets": self._assets,
            "position_peaks": self._position_peaks,
            "position_costs": self._position_costs,
            "history_context": self._history_context,
        }
        temporary_path = self.path.with_suffix(".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary_path.open("w", encoding="utf-8") as history_file:
                json.dump(payload, history_file, ensure_ascii=False, separators=(",", ":"))
            os.replace(temporary_path, self.path)
        except OSError as error:
            logger.error(f"Stock Market histórico: falha ao salvar ({error})")
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _valid_point(point: object) -> bool:
        return (
            isinstance(point, list)
            and len(point) == 4
            and isinstance(point[0], (int, float))
            and isinstance(point[1], str)
            and isinstance(point[2], int)
            and isinstance(point[3], (int, float))
        )
