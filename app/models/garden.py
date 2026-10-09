"""Modelos imutáveis usados pela automação do Garden."""
from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class GardenStatus:
    """Disponibilidade do Garden no runtime atual."""

    available: bool
    unlocked: bool
    message: str


@dataclass(frozen=True)
class GardenSeed:
    """Metadados de uma semente informados pelo próprio minigame."""

    seed_id: int
    key: str
    name: str
    unlocked: bool
    plantable: bool
    mature_age: float
    weed: bool = False
    fungus: bool = False
    immortal: bool = False
    cost: Optional[float] = None


@dataclass(frozen=True)
class GardenSoil:
    """Solo disponível no runtime e seu requisito de Farms."""

    soil_id: int
    key: str
    name: str
    required_farms: int
    tick_minutes: float
    available: bool


@dataclass(frozen=True)
class GardenPlant:
    """Planta presente em um canteiro desbloqueado."""

    x: int
    y: int
    seed_id: int
    key: str
    name: str
    age: float
    mature_age: float
    mature: bool
    weed: bool = False
    fungus: bool = False
    immortal: bool = False
    average_growth: Optional[float] = None
    maximum_growth: Optional[float] = None


@dataclass(frozen=True)
class GardenSnapshot:
    """Leitura consistente e imutável do estado relevante do Garden."""

    status: GardenStatus
    farm_level: Optional[int] = None
    farm_amount: Optional[int] = None
    soil_key: Optional[str] = None
    soil_name: Optional[str] = None
    frozen: bool = False
    next_tick_at: Optional[float] = None
    tick_seconds: Optional[float] = None
    next_soil_at: Optional[float] = None
    game_seed: Optional[str] = None
    game_version: Optional[str] = None
    plot_width: int = 0
    plot_height: int = 0
    unlocked_tiles: Tuple[Tuple[int, int], ...] = field(default_factory=tuple)
    seeds: Tuple[GardenSeed, ...] = field(default_factory=tuple)
    plants: Tuple[GardenPlant, ...] = field(default_factory=tuple)
    soils: Tuple[GardenSoil, ...] = field(default_factory=tuple)
    green_aching_thumb_won: Optional[bool] = None
    green_aching_thumb_progress: Optional[int] = None
    green_aching_thumb_message: str = "Estado da conquista Green, aching thumb indisponível no runtime."

    cookies: Optional[float] = None
    sugar_lumps: Optional[float] = None
    can_refill_lump: Optional[bool] = None
    lump_refill_seconds: Optional[float] = None

    @property
    def unlocked_seed_keys(self) -> frozenset[str]:
        return frozenset(seed.key for seed in self.seeds if seed.unlocked)

    @property
    def missing_seed_keys(self) -> frozenset[str]:
        return frozenset(seed.key for seed in self.seeds if not seed.unlocked)


@dataclass(frozen=True)
class GardenAction:
    """Ação planejada antes de qualquer mutação do jogo."""

    kind: str
    reason: str
    x: Optional[int] = None
    y: Optional[int] = None
    seed_key: Optional[str] = None
    soil_key: Optional[str] = None
    freeze: Optional[bool] = None
    require_mature: bool = True

    @property
    def signature(self) -> str:
        return f"{self.kind}:{self.seed_key or ''}:{self.soil_key or ''}:{self.freeze}:{self.x}:{self.y}"


@dataclass(frozen=True)
class GardenActionResult:
    """Resultado verificável de uma operação enviada ao Garden."""

    success: bool
    action: str
    message: str
    x: Optional[int] = None
    y: Optional[int] = None
    seed_key: Optional[str] = None
    soil_key: Optional[str] = None
    before_key: Optional[str] = None
    after_key: Optional[str] = None
    waiting: bool = False
    reason: str = ""
    required_cookies: Optional[float] = None
    available_cookies: Optional[float] = None


@dataclass(frozen=True)
class GardenGoal:
    """Meta determinística escolhida para o snapshot atual."""

    target_key: str
    target_name: str
    parent_keys: Tuple[str, ...]
    parent_names: Tuple[str, ...]
    reason: str
    pending_prerequisites: Tuple[str, ...]
    success_condition: str
    strategy: str


@dataclass(frozen=True)
class GardenPlan:
    """Plano explicável e integralmente montado antes da execução."""

    goal: Optional[GardenGoal]
    actions: Tuple[GardenAction, ...] = field(default_factory=tuple)
    explanation: str = ""
    waiting: bool = False
    mode: Optional[str] = None
    completed: bool = False


@dataclass(frozen=True)
class GardenCycleResult:
    """Resultado de uma simulação ou ciclo real da Fazendeira."""

    snapshot: GardenSnapshot
    plan: GardenPlan
    dry_run: bool
    action_results: Tuple[GardenActionResult, ...] = field(default_factory=tuple)

