"""Persistência compacta e tolerante a falhas do histórico do Stock Market."""
import json
import os
from pathlib import Path
import threading
import time
from typing import Dict, Iterable, Tuple
from uuid import uuid4

from app.models.stock_market import StockMarketSnapshot
from app.utils.logger import logger


class MarketHistoryStore:
    """Mantém uma janela persistente de preços sem gravar durante cada polling."""

    VERSION = 1
    MAX_POINTS_PER_ASSET = 10_080  # aproximadamente sete dias de ticks de um minuto

    def __init__(self, path: Path | str = Path("data") / "stock_market_history.json"):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._loaded = False
        self._session_id = uuid4().hex
        self._assets: Dict[str, Dict[str, object]] = {}
        self._known_points: set[tuple[str, str, int]] = set()

    def record_snapshot(self, snapshot: StockMarketSnapshot) -> int:
        """Armazena pontos inéditos do tick atual e do histórico nativo disponível."""
        if not snapshot.status.available or snapshot.tick is None:
            return 0
        with self._lock:
            self._load()
            now = time.time()
            seconds = snapshot.seconds_per_tick or 60.0
            source_id = snapshot.game_seed or self._session_id
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
        """Retorna preços mais recentes primeiro, usando o runtime como fallback."""
        with self._lock:
            self._load()
            entry = self._assets.get(str(asset_id), {})
            points = entry.get("points", []) if isinstance(entry, dict) else []
            prices = [point[3] for point in reversed(points) if self._valid_point(point)]
            return tuple(prices) if prices else tuple(fallback)

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
            if not isinstance(payload, dict) or payload.get("version") != self.VERSION:
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
            logger.info(f"Stock Market histórico: {self.point_count()} pontos restaurados")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            logger.warning(f"Stock Market histórico: arquivo ignorado ({error})")
            self._assets = {}

    def _save(self) -> None:
        payload = {
            "version": self.VERSION,
            "updated_at": round(time.time(), 3),
            "assets": self._assets,
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
