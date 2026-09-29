"""Modelos imutáveis usados pela automação de ascensão."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class EstadoAutoAscensao(str, Enum):
    """Estados explícitos do ciclo de Auto Ascensão."""

    PREVIA = "Prévia"
    COMPRA_CELESTIAL = "Compra de Heavenly Upgrades"
    REENCARNACAO = "Reencarnação"
    PREPARACAO = "Preparação"
    PRODUCAO_COMPRAS = "Produção e compras"
    AGUARDANDO_PRESTIGIO = "Aguardando prestígio"
    ASCENSAO = "Ascensão"
    CONCLUIDO = "Concluído"
    INTERROMPIDO = "Interrompido"
    ERRO_SEGURO = "Erro seguro"


@dataclass(frozen=True)
class HeavenlyUpgrade:
    """Heavenly Upgrade observado na árvore de ascensão."""

    id: int
    nome: str
    preco: float
    elegivel: bool
    motivo: str = ""


@dataclass(frozen=True)
class UpgradeNormal:
    """Upgrade normal seguro e visível na loja."""

    id: int
    nome: str
    preco: float
    elegivel: bool
    motivo: str = ""


@dataclass(frozen=True)
class Construcao:
    """Construção desbloqueada e suas condições atuais de compra."""

    id: int
    nome: str
    quantidade: int
    preco_unitario: float
    maximo_compravel: int
    desbloqueada: bool = True


@dataclass(frozen=True)
class SnapshotAscensao:
    """Leitura única e defensiva do estado relevante do jogo."""

    disponivel: bool
    tela: str
    mensagem: str
    versao: Optional[str] = None
    cookies: float = 0.0
    cookies_por_segundo: float = 0.0
    prestigio_atual: float = 0.0
    ganho_prestigio: float = 0.0
    heavenly_chips: float = 0.0
    ascend_timer: float = 0.0
    reincarnate_timer: float = 0.0
    compra_todos_disponivel: bool = False
    heavenly_upgrades: Tuple[HeavenlyUpgrade, ...] = ()
    upgrades_normais: Tuple[UpgradeNormal, ...] = ()
    construcoes: Tuple[Construcao, ...] = ()


@dataclass(frozen=True)
class ResultadoAcaoAscensao:
    """Resultado verificável de uma única operação mutável."""

    sucesso: bool
    acao: str
    mensagem: str
    id_alvo: Optional[int] = None
    quantidade_executada: int = 0
    antes: Optional[float] = None
    depois: Optional[float] = None
    motivo: str = ""


@dataclass(frozen=True)
class PlanoConstrucao:
    """Compra determinística escolhida pela política central."""

    id: int
    nome: str
    quantidade: int
    motivo: str


@dataclass(frozen=True)
class RelatorioAutoAscensao:
    """Relatório em memória apresentado pela interface."""

    estado: EstadoAutoAscensao
    ciclo_atual: int
    ciclos_alvo: int
    ultima_acao: str
    proximo_passo: str
    motivo_parada: str = ""
    simulacao: bool = False
    snapshot: Optional[SnapshotAscensao] = None
    historico: Tuple[str, ...] = field(default_factory=tuple)
