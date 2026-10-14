"""Resumos do Garden para a interface; não altera o plano nem executa ações."""
import math
from collections import Counter
from app.core.garden_catalog import GARDEN_CATALOG

SOIL_NAMES = {'dirt': 'Dirt', 'fertilizer': 'Fertilizer', 'clay': 'Clay',
              'pebbles': 'Pebbles', 'woodchips': 'Wood Chips'}


def short_message(message, limit=150):
    text = ' '.join(str(message).split())
    return text if len(text) <= limit else text[:limit-1].rstrip() + '…'


def grouped_actions(actions):
    groups = Counter((a.kind, a.seed_key, a.soil_key, a.require_mature, a.freeze) for a in actions)
    lines = []
    for (kind, key, soil, mature, freeze), count in groups.items():
        name = GARDEN_CATALOG[key].name if key in GARDEN_CATALOG else key or 'planta'
        if kind == 'plant': lines.append(f'Plantar {count}× {name}')
        elif kind == 'harvest': lines.append(f'{"Colher" if mature else "Remover"} {count}× {name}')
        elif kind == 'change_soil': lines.append(f'Trocar solo para {SOIL_NAMES.get(soil, soil)}')
        elif kind == 'set_freeze': lines.append('Congelar o Garden' if freeze else 'Descongelar o Garden')
        elif kind == 'boost_mutation': lines.append(f'Usar {count} Sugar {"Lump" if count == 1 else "Lumps"} para uma tentativa extra')
        else: lines.append(f'{count}× {kind}')
    return '\n'.join('• ' + line for line in lines)


def result_summary(results):
    confirmed = [r for r in results if r.success]
    groups = Counter((r.action, r.seed_key) for r in confirmed)
    phrases, shown = [], 0
    for (kind, key), count in list(groups.items())[:3]:
        name = GARDEN_CATALOG[key].name if key in GARDEN_CATALOG else 'plantas'
        if kind == 'plant': phrases.append(f'Plantou {count}× {name}')
        elif kind == 'harvest': phrases.append(f'Colheu {count}× {name}')
        elif kind == 'change_soil': phrases.append('Solo atualizado')
        elif kind == 'set_freeze': phrases.append('Congelamento atualizado')
        elif kind == 'boost_mutation': phrases.append('Tentativa extra de mutação realizada')
        else: phrases.append(f'{count} {"ação confirmada" if count == 1 else "ações confirmadas"}')
        shown += count
    if shown < len(confirmed): phrases.append(f'mais {len(confirmed)-shown} ações confirmadas')
    return ' · '.join(phrases) or 'Ciclo concluído.'


def pending_actions(plan, results):
    return tuple(a for a in plan.actions if not any(
        r.success and r.action == a.kind and r.x == a.x and r.y == a.y
        and (r.seed_key is None or r.seed_key == a.seed_key) for r in results))


def _mutation_ready(snapshot, recipe):
    occupied = {(p.x, p.y): p for p in snapshot.plants}
    for x, y in snapshot.unlocked_tiles:
        if (x, y) in occupied:
            continue
        neighbors = [p for (px, py), p in occupied.items() if max(abs(px-x), abs(py-y)) == 1]
        ready = Counter(p.key for p in neighbors if p.mature)
        present = Counter(p.key for p in neighbors)
        if (all((ready if r.mature else present)[r.key] >= r.count for r in recipe.parents)
                and all(present[key] <= maximum for key, maximum in recipe.maximum_neighbors)):
            return True
    return False


def current_state(snapshot, plan):
    if not snapshot.status.available:
        return 'Garden indisponível', short_message(snapshot.status.message)
    if plan.goal is None:
        if snapshot.missing_seed_keys:
            return 'Automação aguardando', short_message(plan.explanation)
        return 'Coleção completa', 'Todas as sementes foram desbloqueadas.'
    goal = plan.goal
    targets = [p for p in snapshot.plants if p.key == goal.target_key]
    if targets:
        plant = max(targets, key=lambda p: p.age)
        if plant.mature:
            return 'Semente pronta para colher', f'{goal.target_name} está madura.'
        detail = f'{goal.target_name}: maturidade {plant.age:.0f} / {plant.mature_age:.0f}.'
        if plant.average_growth and plant.average_growth > 0 and snapshot.tick_seconds:
            minutes = math.ceil((plant.mature_age-plant.age)/plant.average_growth)*snapshot.tick_seconds/60
            detail += f' Faltam cerca de {minutes:.0f} min.'
        return 'Esperando a nova planta amadurecer', detail
    if goal.pending_prerequisites:
        return 'Esperando sementes necessárias', ', '.join(goal.pending_prerequisites)
    if snapshot.frozen:
        return 'Garden congelado', 'O crescimento será retomado ao descongelar.'
    timing_marker = 'Sincronizar os pais: '
    timing = plan.explanation.split(timing_marker, 1)[1].split('. Estimativa', 1)[0] if timing_marker in plan.explanation else ''
    recipe = GARDEN_CATALOG.get(goal.target_key)
    if recipe and recipe.parents and _mutation_ready(snapshot, recipe):
        return 'Esperando a mutação aparecer', 'Já há espaços com os pais exigidos prontos.'
    if timing:
        return 'Alinhando a maturação dos pais', timing[0].upper() + timing[1:]
    if any(a.kind in {'plant', 'harvest'} for a in plan.actions):
        return 'Preparando o canteiro', f'Organizar os pais para obter {goal.target_name}.'
    parents = []
    for key in goal.parent_keys:
        plants = [p for p in snapshot.plants if p.key == key]
        name = GARDEN_CATALOG[key].name if key in GARDEN_CATALOG else key
        parents.append(f'{name}: {sum(p.mature for p in plants)} maduras / {len(plants)} plantadas')
    return 'Esperando os pais amadurecerem', '\n'.join(parents) or short_message(plan.explanation)
