"""Planeja plantios pela janela de vida compartilhada dos pais, em ticks."""
import math
from collections import Counter, defaultdict
from dataclasses import dataclass

from app.models.garden import GardenAction


@dataclass(frozen=True)
class ParentWindow:
    key: str
    ready: int
    expires: float
    born: int = 0


def _neighbors(position):
    x, y = position
    return {(x+dx, y+dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy}


def _windows(recipe, center, forecasts, horizon):
    """Intervalos onde cada contagem e restrição da receita é satisfeita."""
    parents = [forecasts[p] for p in _neighbors(center) if p in forecasts]
    events = sorted({0, horizon} | {t for p in parents for t in (p.born, p.ready, p.expires) if 0 <= t <= horizon})
    result = []
    for start, end in zip(events, events[1:]):
        ready = Counter(p.key for p in parents if p.ready <= start < p.expires)
        present = Counter(p.key for p in parents if p.born <= start < p.expires)
        if (all(ready[r.key] >= r.count for r in recipe.parents)
                and all(present[key] <= count for key, count in recipe.maximum_neighbors)):
            if result and result[-1][1] == start:
                result[-1] = (result[-1][0], end)
            else:
                result.append((start, end))
    return result


def schedule_parent_plantings(snapshot, recipe, desired, centers, actions):
    """Mantém pais existentes; adia novos pais rápidos para ampliar as mutações."""
    if recipe.key == 'queenbeetLump' or not recipe.parents:
        return tuple(actions), ''
    planting = {(a.x, a.y): a for a in actions
                if a.kind == 'plant' and desired.get((a.x, a.y)) == a.seed_key}
    if not planting:
        return tuple(actions), ''
    removed = {(a.x, a.y) for a in actions if a.kind == 'harvest'}
    occupied = {(p.x, p.y): p for p in snapshot.plants if (p.x, p.y) not in removed}
    requirements = {r.key: r for r in recipe.parents}
    seeds = {s.key: s for s in snapshot.seeds}
    boosts = {(x, y): boost for x, y, boost in snapshot.growth_multipliers}
    forecasts, new_windows = {}, {}
    for position, plant in occupied.items():
        rate = plant.average_growth
        if rate is None or not math.isfinite(rate) or rate <= 0:
            if plant.key in requirements:
                return tuple(actions), ''
            # Uma planta desconhecida continua bloqueando o espaço, sem ser removida.
            forecasts[position] = ParentWindow(plant.key, 0, math.inf)
            continue
        ready = (math.ceil(max(0, plant.mature_age-plant.age)/rate)
                 if plant.key in requirements and requirements[plant.key].mature else 0)
        expires = math.inf if plant.immortal else math.ceil(max(0, 100-plant.age)/rate)
        forecasts[position] = ParentWindow(plant.key, ready, expires)
    for position, action in planting.items():
        if position in occupied:
            continue
        seed = seeds.get(action.seed_key)
        rate = seed.average_growth * boosts.get(position, 1.0) if seed and seed.average_growth is not None else None
        if rate is None or not math.isfinite(rate) or rate <= 0:
            return tuple(actions), ''
        ready = math.ceil(seed.mature_age/rate) if requirements[seed.key].mature else 0
        expires = math.inf if seed.immortal else math.ceil(100/rate)
        new_windows[position] = ParentWindow(seed.key, ready, expires)
        forecasts[position] = new_windows[position]
    if not new_windows:
        return tuple(actions), ''
    # A vida dos pais finitos limita a espera; imortais podem amadurecer antes.
    horizon = max(p.ready for p in forecasts.values()) + max(
        (p.expires for p in forecasts.values() if math.isfinite(p.expires)), default=1) + 1
    centers = tuple(c for c in centers if c not in occupied)
    affected = {p: tuple(c for c in centers if p in _neighbors(c)) for p in new_windows}
    delays = {}
    # Receitas que exigem vários pais da mesma espécie ajustam o grupo junto.
    # Assim Everdaisy não fica esperando três decisões isoladas incompatíveis.
    grouped = defaultdict(list)
    for position, base in new_windows.items():
        group = base.key if requirements[base.key].count > 1 else position
        grouped[group].append(position)
    groups = sorted(grouped.values(), key=lambda group: (-max(new_windows[p].ready for p in group), min(group)))
    for group in groups:
        local_centers = {c for position in group for c in affected[position]}
        others = {p: forecasts[p] for c in local_centers for p in _neighbors(c)
                  if p not in group and p in forecasts}
        events = {t for p in others.values() for t in (p.born, p.ready, p.expires) if math.isfinite(t)}
        candidates = {0}
        for event in events:
            for position in group:
                base = new_windows[position]
                for offset in (base.ready, base.expires):
                    if math.isfinite(offset):
                        shift = int(event-offset)
                        candidates.update(t for t in (shift-1, shift, shift+1) if 0 <= t <= horizon-base.ready)
        def evaluate(delay):
            for position in group:
                base = new_windows[position]
                forecasts[position] = ParentWindow(base.key, base.ready+delay, base.expires+delay, delay)
            intervals = [w for c in local_centers for w in _windows(recipe, c, forecasts, horizon)]
            score = sum(end-start for start, end in intervals)
            other_ready = [p.ready for p in others.values() if p.key in requirements]
            alignment = sum(min((abs(new_windows[pos].ready+delay-t) for t in other_ready), default=0)
                            for pos in group if math.isfinite(new_windows[pos].expires))
            return score, -alignment if score else 0, -delay
        delay = max(candidates, key=evaluate)
        for position in group:
            base = new_windows[position]
            delays[position] = delay
            forecasts[position] = ParentWindow(base.key, base.ready+delay, base.expires+delay, delay)
    deferred = {p: delay for p, delay in delays.items() if delay > 0}
    kept = tuple(a for a in actions if a.kind != 'plant' or (a.x, a.y) not in deferred)
    # Não limpar um canteiro antecipadamente quando seu novo pai ainda precisa esperar.
    kept = tuple(a for a in kept if not (a.kind == 'harvest' and (a.x, a.y) in deferred))
    if not deferred:
        return kept, ''
    tick_seconds = snapshot.tick_seconds or next(
        (s.tick_minutes*60 for s in snapshot.soils if s.key == snapshot.soil_key), 180)
    by_key = defaultdict(list)
    for position, delay in deferred.items():
        by_key[new_windows[position].key].append(delay)
    waits = []
    for key, ticks in sorted(by_key.items()):
        low, high = min(ticks)*tick_seconds/60, max(ticks)*tick_seconds/60
        when = f'~{low:.0f} min' if low == high else f'~{low:.0f}–{high:.0f} min'
        waits.append(f'{seeds[key].name} em {when}')
    return kept, 'Sincronizar os pais: aguardar para plantar ' + '; '.join(waits) + ' com o solo atual. Estimativa recalculada a cada leitura.'
