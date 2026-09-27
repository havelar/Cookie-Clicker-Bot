"""Orquestrador por tick da coleção de sementes do Garden."""
from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable, Optional, Sequence, Tuple

from app.core.garden_catalog import GARDEN_CATALOG, TARGET_SEED_KEYS, GardenRecipe
from app.models.garden import (
    GardenAction,
    GardenActionResult,
    GardenCycleResult,
    GardenGoal,
    GardenPlan,
    GardenPlant,
    GardenSnapshot,
)
from app.utils.logger import logger


class Fazendeira:
    """Lê, prioriza, planeja e, quando autorizada, opera o Garden.

    A classe nunca sacrifica o jardim, compra upgrades ou altera saves. Quando
    autorizada, reconcilia o canteiro inteiro uma vez por tick: remove plantas
    divergentes, preserva as corretas e monta o layout da meta atual.
    """

    # Mapeamento explícito: a estratégia de qualquer meta pode ser localizada
    # sem procurar condicionais espalhadas pela aplicação.
    ESTRATEGIAS_POR_PLANTA = {
        "bakerWheat": "_estrategia_inicial",
        "thumbcorn": "_estrategia_mutacao_adjacente",
        "cronerice": "_estrategia_mutacao_adjacente",
        "gildmillet": "_estrategia_mutacao_adjacente",
        "clover": "_estrategia_mutacao_adjacente",
        "goldenClover": "_estrategia_anel",
        "shimmerlily": "_estrategia_mutacao_adjacente",
        "elderwort": "_estrategia_mutacao_adjacente",
        "bakeberry": "_estrategia_mutacao_adjacente",
        "chocoroot": "_estrategia_mutacao_adjacente",
        "whiteChocoroot": "_estrategia_mutacao_adjacente",
        "whiteMildew": "_estrategia_fungo_espalhamento",
        "brownMold": "_estrategia_derivado_erva",
        "meddleweed": "_estrategia_erva_espontanea",
        "whiskerbloom": "_estrategia_mutacao_adjacente",
        "chimerose": "_estrategia_mutacao_adjacente",
        "nursetulip": "_estrategia_mutacao_adjacente",
        "drowsyfern": "_estrategia_mutacao_adjacente",
        "wardlichen": "_estrategia_mutacao_adjacente",
        "keenmoss": "_estrategia_mutacao_adjacente",
        "queenbeet": "_estrategia_mutacao_adjacente",
        "queenbeetLump": "_estrategia_anel",
        "duketater": "_estrategia_mutacao_adjacente",
        "crumbspore": "_estrategia_derivado_erva",
        "doughshroom": "_estrategia_mutacao_adjacente",
        "glovemorel": "_estrategia_mutacao_adjacente",
        "cheapcap": "_estrategia_mutacao_adjacente",
        "foolBolete": "_estrategia_mutacao_adjacente",
        "wrinklegill": "_estrategia_mutacao_adjacente",
        "greenRot": "_estrategia_mutacao_adjacente",
        "shriekbulb": "_estrategia_anel",
        "tidygrass": "_estrategia_mutacao_adjacente",
        "everdaisy": "_estrategia_anel",
        "ichorpuff": "_estrategia_mutacao_adjacente",
    }

    def __init__(self, bridge, *, clock=None):
        if clock is None:
            import time
            clock = time.time
        self.bridge = bridge
        self._clock = clock
        self._last_real_tick_token: Optional[float] = None
        self._descendant_counts = self._calculate_descendant_counts()

    def capture_snapshot(self) -> GardenSnapshot:
        """Lê o Garden sem alterar o jogo."""
        return self.bridge.get_garden_snapshot()

    def select_next_goal(self, snapshot: GardenSnapshot) -> Optional[GardenGoal]:
        """Escolhe uma meta única a partir das sementes realmente desbloqueadas."""
        if not snapshot.status.available:
            return None
        unlocked = snapshot.unlocked_seed_keys
        missing = [key for key in TARGET_SEED_KEYS if key not in unlocked]
        if not missing:
            return None

        # Uma mutação já presente deve ser preservada e colhida antes de
        # iniciar outra receita. A maturidade desempata de forma determinística.
        present_missing = [
            plant for plant in snapshot.plants if plant.key in missing
        ]
        if present_missing:
            present_missing.sort(key=lambda plant: (not plant.mature, plant.y, plant.x, plant.key))
            target_key = present_missing[0].key
            reason = "A mutação-alvo já está no canteiro e deve ser preservada até a colheita madura."
        else:
            target_key = min(missing, key=lambda key: self._priority_key(key, unlocked))
            recipe = GARDEN_CATALOG[target_key]
            pending_count = sum(parent.key not in unlocked for parent in recipe.parents)
            reason = (
                "Receita pronta e com alto potencial de liberar novas dependências."
                if pending_count == 0
                else "Pré-requisito mais próximo que reduz o bloqueio das receitas seguintes."
            )

        recipe = GARDEN_CATALOG[target_key]
        pending = tuple(
            GARDEN_CATALOG[parent.key].name
            for parent in recipe.parents if parent.key not in unlocked
        )
        parent_names = tuple(
            f"{parent.count}× {GARDEN_CATALOG[parent.key].name}"
            if parent.count > 1 else GARDEN_CATALOG[parent.key].name
            for parent in recipe.parents
        )
        return GardenGoal(
            target_key=target_key,
            target_name=recipe.name,
            parent_keys=tuple(parent.key for parent in recipe.parents),
            parent_names=parent_names,
            reason=reason,
            pending_prerequisites=pending,
            success_condition=recipe.condition,
            strategy=recipe.strategy,
        )

    def build_plan(self, snapshot: GardenSnapshot) -> GardenPlan:
        """Gera o plano completo antes de qualquer chamada mutável."""
        if snapshot.status.available:
            runtime_keys = {seed.key for seed in snapshot.seeds}
            catalog_keys = set(TARGET_SEED_KEYS)
            if runtime_keys != catalog_keys:
                missing = sorted(catalog_keys - runtime_keys)
                extra = sorted(runtime_keys - catalog_keys)
                details = []
                if missing:
                    details.append("ausentes no runtime: " + ", ".join(missing))
                if extra:
                    details.append("novas no runtime: " + ", ".join(extra))
                return GardenPlan(
                    None,
                    explanation="Catálogo incompatível com esta versão do jogo; " + "; ".join(details) + ".",
                    waiting=True,
                )
        goal = self.select_next_goal(snapshot)
        if goal is None:
            explanation = (
                "Coleção completa: todas as sementes foram confirmadas no snapshot."
                if snapshot.status.available and not snapshot.missing_seed_keys
                else snapshot.status.message
            )
            return GardenPlan(None, explanation=explanation, waiting=True)

        recipe = GARDEN_CATALOG[goal.target_key]
        target_plants = tuple(plant for plant in snapshot.plants if plant.key == goal.target_key)
        mature_target = next((plant for plant in target_plants if plant.mature), None)
        if mature_target:
            actions = [GardenAction(
                "harvest", f"Colher {goal.target_name} madura e confirmar o desbloqueio da semente.",
                x=mature_target.x, y=mature_target.y, seed_key=goal.target_key,
            )]
            actions.extend(
                GardenAction(
                    "harvest", "Limpar o layout concluído antes da próxima meta.",
                    x=plant.x, y=plant.y, seed_key=plant.key, require_mature=False,
                )
                for plant in self._sorted_plants(snapshot)
                if (plant.x, plant.y) != (mature_target.x, mature_target.y)
            )
            actions = list(self._prepend_operational_actions(snapshot, actions))
            return GardenPlan(
                goal, tuple(actions),
                "A meta madura será colhida e o canteiro será limpo; o próximo tick escolherá a próxima meta.",
            )
        if target_plants:
            oldest = max(target_plants, key=lambda plant: plant.age)
            actions = list(self._growth_actions(snapshot))
            actions.extend(self._remove_plants_except(snapshot, allowed_keys={goal.target_key}))
            return GardenPlan(
                goal,
                tuple(actions),
                explanation=(
                    f"{goal.target_name} encontrada com idade {oldest.age:.1f}/{oldest.mature_age:.1f}; "
                    "preservar a meta, remover as demais plantas e aguardar maturidade."
                ),
                waiting=not actions,
            )
        if goal.pending_prerequisites:
            return GardenPlan(
                goal,
                explanation="A receita ainda depende de: " + ", ".join(goal.pending_prerequisites) + ".",
                waiting=True,
            )

        method_name = self.ESTRATEGIAS_POR_PLANTA[goal.target_key]
        actions, explanation = getattr(self, method_name)(snapshot, recipe)
        actions = self._prepend_operational_actions(snapshot, actions)
        return GardenPlan(goal, tuple(actions), explanation, waiting=not actions)

    def run_cycle(
        self,
        *,
        dry_run: bool = True,
        automation_enabled: bool = False,
    ) -> GardenCycleResult:
        """Simula ou executa um ciclo; sem autorização, jamais muta o jogo."""
        snapshot = self.capture_snapshot()
        plan = self.build_plan(snapshot)
        if dry_run or not automation_enabled or not snapshot.status.available:
            return GardenCycleResult(snapshot, plan, True, ())

        # ``M.nextStep`` muda somente quando o Garden processa um tick. Ele é
        # usado como token para impedir duas reconciliações reais no mesmo tick.
        tick_token = snapshot.next_tick_at
        if tick_token is not None and tick_token == self._last_real_tick_token:
            return GardenCycleResult(snapshot, plan, False, ())
        if tick_token is not None:
            self._last_real_tick_token = tick_token

        results = []
        for action in plan.actions:
            result = self._execute_action(action)
            results.append(result)
            if result.success:
                logger.info(f"Garden: {result.message}")
            else:
                logger.warning(f"Garden: {result.message}")
        return GardenCycleResult(snapshot, plan, False, tuple(results))

    def _execute_action(self, action: GardenAction) -> GardenActionResult:
        if action.kind == "plant":
            return self.bridge.plant_garden_seed(action.seed_key, action.x, action.y)
        if action.kind == "harvest":
            return self.bridge.harvest_garden_tile(
                action.x, action.y, expected_key=action.seed_key,
                require_mature=action.require_mature,
            )
        if action.kind == "change_soil":
            return self.bridge.change_garden_soil(action.soil_key)
        if action.kind == "set_freeze":
            return self.bridge.set_garden_frozen(bool(action.freeze))
        return GardenActionResult(False, action.kind, "Ação do Garden desconhecida.")

    def _estrategia_inicial(self, snapshot: GardenSnapshot, recipe: GardenRecipe):
        return (), "A semente inicial deveria estar desbloqueada; aguarde uma nova leitura do runtime."

    def _estrategia_mutacao_adjacente(self, snapshot: GardenSnapshot, recipe: GardenRecipe):
        return self._plan_generic_layout(snapshot, recipe)

    def _estrategia_anel(self, snapshot: GardenSnapshot, recipe: GardenRecipe):
        return self._plan_parent_layout(snapshot, recipe)

    def _estrategia_fungo_espalhamento(self, snapshot: GardenSnapshot, recipe: GardenRecipe):
        return self._plan_parent_layout(snapshot, recipe)

    def _estrategia_erva_espontanea(self, snapshot: GardenSnapshot, recipe: GardenRecipe):
        actions = self._remove_plants_except(snapshot, allowed_keys=set())
        return actions, (
            "Limpar o canteiro e mantê-lo vazio para permitir o surgimento espontâneo de Meddleweed."
            if actions else
            "Canteiro vazio; aguardando o surgimento espontâneo de Meddleweed."
        )

    def _estrategia_derivado_erva(self, snapshot: GardenSnapshot, recipe: GardenRecipe):
        weeds = sorted(
            (plant for plant in snapshot.plants if plant.key == "meddleweed"),
            key=lambda plant: (-plant.age, plant.y, plant.x),
        )
        if not weeds:
            desired_position = next(iter(sorted(snapshot.unlocked_tiles, key=lambda pos: (pos[1], pos[0]))), None)
            desired = {desired_position: "meddleweed"} if desired_position else {}
            actions = self._reconcile_layout(snapshot, desired)
            if desired_position and "meddleweed" in snapshot.unlocked_seed_keys:
                return actions, "Manter uma Meddleweed no ponto definido e remover qualquer planta fora do objetivo."
            return actions, "Aguardando uma Meddleweed disponível; o restante do canteiro ficará vazio."
        cleanup = list(self._remove_plants_except(snapshot, allowed_positions={(weeds[0].x, weeds[0].y)}))
        weed = weeds[0]
        if not weed.mature:
            return tuple(cleanup), f"Meddleweed com idade {weed.age:.1f}/{weed.mature_age:.1f}; preservar somente ela até amadurecer."
        action = GardenAction(
            "harvest", "Arrancar a Meddleweed madura para tentar gerar Brown mold ou Crumbspore.",
            x=weed.x, y=weed.y, seed_key="meddleweed", require_mature=True,
        )
        return (action, *cleanup), "A Meddleweed madura será arrancada; o resultado aleatório será validado no próximo tick."

    def _plan_generic_layout(self, snapshot: GardenSnapshot, recipe: GardenRecipe):
        """Aplica o layout repetível de duas plantas iguais ou diferentes."""
        layout = self._find_generic_layout(snapshot, recipe)
        if layout is None:
            # Receitas especiais usam o layout local em anel.
            return self._plan_parent_layout(snapshot, recipe)

        desired, mutation_tiles, orientation = layout
        actions = self._reconcile_layout(snapshot, desired)
        if actions:
            removals = sum(action.kind == "harvest" for action in actions)
            plantings = sum(action.kind == "plant" for action in actions)
            return actions, (
                f"Reconciliar o layout genérico em faixas {orientation}: remover {removals} "
                f"planta(s) divergente(s), plantar {plantings} pai(s) e preservar "
                f"{len(mutation_tiles)} espaços para a mutação."
            )

        ready_tiles = tuple(
            position for position in mutation_tiles
            if self._mutation_tile_is_ready(snapshot, position, recipe)
        )
        if not ready_tiles:
            return self._growth_actions(snapshot), (
                f"Layout genérico completo; aguardando a maturidade dos pais em faixas {orientation}."
            )
        woodchips = next(
            (soil for soil in snapshot.soils if soil.key == "woodchips" and soil.available), None
        )
        can_change = snapshot.next_soil_at is None or snapshot.next_soil_at <= self._clock()
        if woodchips and snapshot.soil_key != "woodchips" and can_change and not snapshot.frozen:
            return (
                GardenAction(
                    "change_soil", "Aumentar as tentativas do layout genérico com Wood chips.",
                    soil_key="woodchips",
                ),
            ), (
                f"{len(ready_tiles)} espaços do layout estão prontos; usar Wood chips e aguardar a mutação."
            )
        return (), (
            f"{len(ready_tiles)} espaços do layout genérico estão cercados pelos pais exigidos; "
            "preservar esses espaços vazios e aguardar a mutação."
        )

    def _find_generic_layout(self, snapshot: GardenSnapshot, recipe: GardenRecipe):
        """Escolhe a faixa que maximiza espaços válidos de mutação."""
        expanded_parents = tuple(
            parent.key for parent in recipe.parents for _ in range(parent.count)
        )
        if len(expanded_parents) != 2 or recipe.maximum_neighbors:
            return None
        unlocked = set(snapshot.unlocked_tiles)
        if not unlocked:
            return None
        reference_layout = self._maximum_reference_layout(unlocked, expanded_parents, recipe)
        if reference_layout is not None:
            return reference_layout
        minimum_x = min(x for x, _ in unlocked)
        minimum_y = min(y for _, y in unlocked)
        options = []
        pair_steps = (2, 3) if expanded_parents[0] == expanded_parents[1] else (3,)
        for orientation_rank, orientation in enumerate(("horizontais", "verticais")):
            for offset in range(3):
                for pair_step in pair_steps:
                    for pair_offset in range(pair_step):
                        desired = {}
                        maximum_x = max(x for x, _ in unlocked)
                        maximum_y = max(y for _, y in unlocked)
                        if orientation == "horizontais":
                            stripe_values = range(minimum_y + offset, maximum_y + 1, 3)
                            pair_starts = range(minimum_x + pair_offset, maximum_x, pair_step)
                            for y in stripe_values:
                                for x in pair_starts:
                                    pair = ((x, y), (x + 1, y))
                                    if all(position in unlocked for position in pair):
                                        # A primeira planta da receita ocupa G; a
                                        # segunda ocupa Y, como no layout de referência YG.
                                        desired[pair[0]] = expanded_parents[1]
                                        desired[pair[1]] = expanded_parents[0]
                        else:
                            stripe_values = range(minimum_x + offset, maximum_x + 1, 3)
                            pair_starts = range(minimum_y + pair_offset, maximum_y, pair_step)
                            for x in stripe_values:
                                for y in pair_starts:
                                    pair = ((x, y), (x, y + 1))
                                    if all(position in unlocked for position in pair):
                                        desired[pair[0]] = expanded_parents[1]
                                        desired[pair[1]] = expanded_parents[0]
                        desired_counts = Counter(desired.values())
                        if any(desired_counts[parent.key] < parent.count for parent in recipe.parents):
                            continue
                        mutation_tiles = tuple(
                            position for position in sorted(unlocked, key=lambda pos: (pos[1], pos[0]))
                            if position not in desired
                            and self._intended_tile_matches(position, desired, {}, recipe)
                        )
                        if not mutation_tiles:
                            continue
                        options.append((
                            -len(mutation_tiles), len(desired), orientation_rank,
                            offset, pair_step, pair_offset, desired, mutation_tiles, orientation,
                        ))
        if not options:
            return None
        *_, desired, mutation_tiles, orientation = min(options)
        return desired, mutation_tiles, orientation

    def _maximum_reference_layout(
        self,
        unlocked: set[Tuple[int, int]],
        parents: Tuple[str, str],
        recipe: GardenRecipe,
    ):
        """Usa o setup de referência com 10 pais no canteiro máximo 6×6."""
        minimum_x = min(x for x, _ in unlocked)
        minimum_y = min(y for _, y in unlocked)
        full_plot = {
            (minimum_x + x, minimum_y + y)
            for y in range(6) for x in range(6)
        }
        if unlocked != full_plot:
            return None

        first, second = parents
        if first == second:
            rows = (
                (1, ((0, first), (1, first), (3, first), (4, first), (5, first))),
                (4, ((0, first), (1, first), (3, first), (4, first), (5, first))),
            )
        else:
            # Layout oficializado pela referência visual do projeto:
            # GYG.YG
            # ......
            # GY.GYG
            rows = (
                (1, ((0, first), (1, second), (2, first), (4, second), (5, first))),
                (4, ((0, first), (1, second), (3, first), (4, second), (5, first))),
            )

        desired = {
            (minimum_x + x, minimum_y + y): key
            for y, entries in rows for x, key in entries
        }
        mutation_tiles = tuple(
            position for position in sorted(unlocked, key=lambda pos: (pos[1], pos[0]))
            if position not in desired
            and self._intended_tile_matches(position, desired, {}, recipe)
        )
        if not mutation_tiles:
            return None
        return desired, mutation_tiles, "horizontais (layout máximo de 10 plantas)"

    def _intended_tile_matches(self, position, desired, occupied, recipe: GardenRecipe) -> bool:
        counts = Counter()
        for neighbor in self._neighbors(position):
            if neighbor in desired:
                counts[desired[neighbor]] += 1
            elif neighbor in occupied:
                counts[occupied[neighbor].key] += 1
        return all(counts[parent.key] >= parent.count for parent in recipe.parents) and all(
            counts[key] <= maximum for key, maximum in recipe.maximum_neighbors
        )

    def _mutation_tile_is_ready(
        self, snapshot: GardenSnapshot, position: Tuple[int, int], recipe: GardenRecipe
    ) -> bool:
        plants = {
            (plant.x, plant.y): plant for plant in snapshot.plants
            if (plant.x, plant.y) in set(self._neighbors(position))
        }
        mature = Counter(plant.key for plant in plants.values() if plant.mature)
        present = Counter(plant.key for plant in plants.values())
        return all(
            (mature if parent.mature else present)[parent.key] >= parent.count
            for parent in recipe.parents
        ) and all(present[key] <= maximum for key, maximum in recipe.maximum_neighbors)

    def _plan_parent_layout(self, snapshot: GardenSnapshot, recipe: GardenRecipe):
        center, desired = self._find_layout(snapshot, recipe)
        if center is None:
            return (), "Não existe espaço desbloqueado suficiente para o layout exigido."
        actions = self._reconcile_layout(snapshot, desired)
        if not actions:
            parents = self._plants_around(snapshot, center)
            required = {parent.key: parent for parent in recipe.parents}
            mature = Counter(plant.key for plant in parents if plant.mature)
            present = Counter(plant.key for plant in parents)
            pending = [
                f"{GARDEN_CATALOG[key].name} ({(mature if requirement.mature else present)[key]}/{requirement.count} prontos)"
                for key, requirement in required.items()
                if (mature if requirement.mature else present)[key] < requirement.count
            ]
            if pending:
                return self._growth_actions(snapshot), "Layout preparado; aguardando maturidade: " + ", ".join(pending) + "."
            woodchips = next((soil for soil in snapshot.soils if soil.key == "woodchips" and soil.available), None)
            can_change = snapshot.next_soil_at is None or snapshot.next_soil_at <= self._clock()
            if woodchips and snapshot.soil_key != "woodchips" and can_change and not snapshot.frozen:
                return (
                    GardenAction("change_soil", "Aumentar as tentativas de mutação com lascas de madeira.", soil_key="woodchips"),
                ), "Pais maduros posicionados; mudar para lascas de madeira e preservar o centro vazio."
            return (), "Pais maduros posicionados; manter o centro vazio e aguardar a mutação."

        removals = sum(action.kind == "harvest" for action in actions)
        plantings = sum(action.kind == "plant" for action in actions)
        return actions, (
            f"Reconciliar o anel ao redor de ({center[0]}, {center[1]}): remover {removals} "
            f"planta(s) divergente(s), plantar {plantings} pai(s) e preservar o centro vazio."
        )

    def _find_layout(self, snapshot: GardenSnapshot, recipe: GardenRecipe):
        unlocked = set(snapshot.unlocked_tiles)
        required = tuple(
            parent.key for parent in recipe.parents for _ in range(parent.count)
        )
        candidates = []
        for center in sorted(unlocked, key=lambda pos: (pos[1], pos[0])):
            neighbors = sorted(
                (pos for pos in self._neighbors(center) if pos in unlocked),
                key=lambda pos: (pos[1], pos[0]),
            )
            if len(neighbors) >= len(required):
                candidates.append((-len(neighbors), center[1], center[0], center, neighbors))
        if not candidates:
            return None, {}
        _, _, _, center, neighbors = min(candidates)
        desired = {
            position: key for position, key in zip(neighbors[:len(required)], required)
        }
        return center, desired

    def _reconcile_layout(
        self, snapshot: GardenSnapshot, desired: Dict[Tuple[int, int], str]
    ) -> Tuple[GardenAction, ...]:
        """Transforma o canteiro no layout exato sem depender de ciclos extras."""
        occupied = {(plant.x, plant.y): plant for plant in snapshot.plants}
        actions = list(self._remove_plants_except(snapshot, allowed_layout=desired))
        for position, key in sorted(desired.items(), key=lambda item: (item[0][1], item[0][0])):
            current = occupied.get(position)
            if current is not None and current.key == key:
                continue
            actions.append(GardenAction(
                "plant", f"Plantar {GARDEN_CATALOG[key].name} na posição definida do layout.",
                x=position[0], y=position[1], seed_key=key,
            ))
        return tuple(actions)

    def _remove_plants_except(
        self,
        snapshot: GardenSnapshot,
        *,
        allowed_layout: Optional[Dict[Tuple[int, int], str]] = None,
        allowed_keys: Optional[set[str]] = None,
        allowed_positions: Optional[set[Tuple[int, int]]] = None,
    ) -> Tuple[GardenAction, ...]:
        allowed_layout = allowed_layout or {}
        allowed_keys = allowed_keys or set()
        allowed_positions = allowed_positions or set()
        actions = []
        for plant in self._sorted_plants(snapshot):
            position = (plant.x, plant.y)
            keep = (
                allowed_layout.get(position) == plant.key
                or plant.key in allowed_keys
                or position in allowed_positions
            )
            if keep:
                continue
            actions.append(GardenAction(
                "harvest", "Remover planta fora do layout ou do objetivo atual.",
                x=plant.x, y=plant.y, seed_key=plant.key, require_mature=False,
            ))
        return tuple(actions)

    @staticmethod
    def _sorted_plants(snapshot: GardenSnapshot) -> Tuple[GardenPlant, ...]:
        return tuple(sorted(snapshot.plants, key=lambda plant: (plant.y, plant.x)))

    def _prepend_operational_actions(
        self, snapshot: GardenSnapshot, actions: Sequence[GardenAction]
    ) -> Tuple[GardenAction, ...]:
        result = list(actions)
        if snapshot.frozen and not any(action.kind == "set_freeze" for action in result):
            result.insert(0, GardenAction("set_freeze", "Descongelar o Garden para permitir crescimento e mutações.", freeze=False))
        desired = self._desired_soil(snapshot, actions)
        if desired and desired != snapshot.soil_key and not snapshot.frozen:
            result.insert(0, GardenAction("change_soil", f"Usar {desired} na etapa atual.", soil_key=desired))
        return tuple(result)

    def _desired_soil(self, snapshot: GardenSnapshot, actions: Sequence[GardenAction]) -> Optional[str]:
        available = {soil.key for soil in snapshot.soils if soil.available}
        can_change = snapshot.next_soil_at is None or snapshot.next_soil_at <= self._clock()
        if not can_change:
            return None
        if any(action.kind == "plant" for action in actions) and "fertilizer" in available:
            return "fertilizer"
        return None

    def _growth_actions(self, snapshot: GardenSnapshot) -> Tuple[GardenAction, ...]:
        """Descongela e usa fertilizante, quando seguro, para amadurecer plantas."""
        actions = []
        if snapshot.frozen:
            actions.append(GardenAction(
                "set_freeze", "Descongelar o Garden para retomar o crescimento.", freeze=False,
            ))
            return tuple(actions)
        fertilizer = next(
            (soil for soil in snapshot.soils if soil.key == "fertilizer" and soil.available), None
        )
        can_change = snapshot.next_soil_at is None or snapshot.next_soil_at <= self._clock()
        if fertilizer and snapshot.soil_key != "fertilizer" and can_change:
            actions.append(GardenAction(
                "change_soil", "Acelerar o amadurecimento dos pais com fertilizante.",
                soil_key="fertilizer",
            ))
        return tuple(actions)

    def _priority_key(self, key: str, unlocked: frozenset[str]):
        recipe = GARDEN_CATALOG[key]
        pending = sum(parent.key not in unlocked for parent in recipe.parents)
        special_penalty = 1 if recipe.strategy in {"erva_espontanea", "derivado_erva"} else 0
        return (pending, special_penalty, -self._descendant_counts[key], TARGET_SEED_KEYS.index(key))

    def _calculate_descendant_counts(self) -> Dict[str, int]:
        children = {key: set() for key in TARGET_SEED_KEYS}
        for recipe in GARDEN_CATALOG.values():
            for parent in recipe.parents:
                children[parent.key].add(recipe.key)

        def descendants(key: str, seen: frozenset[str] = frozenset()) -> set[str]:
            if key in seen:
                return set()
            direct = children[key]
            result = set(direct)
            for child in direct:
                result.update(descendants(child, seen | {key}))
            return result

        return {key: len(descendants(key)) for key in TARGET_SEED_KEYS}

    @staticmethod
    def _neighbors(center: Tuple[int, int]) -> Iterable[Tuple[int, int]]:
        x, y = center
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx or dy:
                    yield x + dx, y + dy

    def _plants_around(
        self, snapshot: GardenSnapshot, center: Tuple[int, int]
    ) -> Tuple[GardenPlant, ...]:
        positions = set(self._neighbors(center))
        return tuple(plant for plant in snapshot.plants if (plant.x, plant.y) in positions)
