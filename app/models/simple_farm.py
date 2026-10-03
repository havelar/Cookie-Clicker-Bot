"""Modelos imutáveis do modo de farm simples por Golden Cookies."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class EstadoSimpleFarm(str, Enum):
    OCIOSO = "ocioso"
    PREVIA = "prévia"
    COLETANDO = "coletando Golden Cookies"
    ALINHANDO = "alinhando FtHoF"
    AGUARDANDO_BUFF = "aguardando buff natural"
    EXECUTANDO = "executando Dualcast"
    INTERROMPIDO = "interrompido"
    ERRO_SEGURO = "erro seguro"


@dataclass(frozen=True)
class ConfiguracaoSimpleFarm:
    """Ajustes que não relaxam as garantias de custo do modo."""

    busca_maxima_spells: int = 250
    intervalo_verificacao: float = 0.2
    duracao_minima_buff: float = 8.0
    reserva_caixa: float = 0.30
    investimento_por_ciclo: float = 0.10

    def __post_init__(self) -> None:
        if not 2 <= self.busca_maxima_spells <= 10_000:
            raise ValueError("A busca deve ficar entre 2 e 10.000 spells")
        if not 0.1 <= self.intervalo_verificacao <= 10.0:
            raise ValueError("O intervalo deve ficar entre 0,1 e 10 segundos")
        if not 3.0 <= self.duracao_minima_buff <= 60.0:
            raise ValueError("A duração mínima deve ficar entre 3 e 60 segundos")
        if not 0.10 <= self.reserva_caixa <= 0.90:
            raise ValueError("A reserva de caixa deve ficar entre 10% e 90%")
        if not 0.01 <= self.investimento_por_ciclo <= 0.50:
            raise ValueError("O investimento por ciclo deve ficar entre 1% e 50%")


@dataclass(frozen=True)
class PlanoSimpleFarm:
    seed: str
    versao: str
    cast_atual: int
    cast_inicial: int
    resultados: Tuple[str, str]
    spells_a_pular: int
    qualidade: str
    torres_iniciais: int
    torres_finais: int

    @property
    def resumo(self) -> str:
        efeitos = " → ".join(self.resultados)
        return (
            f"cast {self.cast_inicial} ({self.spells_a_pular} skips): {efeitos} "
            f"| torres {self.torres_iniciais}→{self.torres_finais} | {self.qualidade}"
        )


@dataclass(frozen=True)
class RelatorioSimpleFarm:
    estado: EstadoSimpleFarm
    mensagem: str
    proximo_passo: str = ""
    plano: Optional[PlanoSimpleFarm] = None
    cast_atual: Optional[int] = None
    mana: Optional[float] = None
    mana_maxima: Optional[float] = None
    cookies_assados: Optional[float] = None
    cookies_no_banco: Optional[float] = None
    buffs_ativos: Tuple[str, ...] = field(default_factory=tuple)
    golden_cookies_coletados: int = 0
    dualcasts_executados: int = 0
    upgrades_comprados: int = 0
    construcoes_compradas: int = 0
    caixa_reservado: Optional[float] = None
    pantheon_slots: Tuple[int, ...] = field(default_factory=tuple)
    erro: str = ""

    @property
    def terminal(self) -> bool:
        return self.estado in {EstadoSimpleFarm.INTERROMPIDO, EstadoSimpleFarm.ERRO_SEGURO}
