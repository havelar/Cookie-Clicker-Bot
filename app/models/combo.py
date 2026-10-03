"""Modelos do modo de combo planejado para o Cookie Clicker."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class EstadoCombo(str, Enum):
    """Estados observáveis da automação de combo."""

    OCIOSO = "ocioso"
    PREVIA = "prévia"
    PREPARANDO = "preparando"
    ALINHANDO = "alinhando spells"
    PAUSADO = "pausado — aguardando você"
    AGUARDANDO_GARDEN = "aguardando Garden"
    AGUARDANDO_BUFFS = "aguardando buffs naturais"
    EXECUTANDO = "executando Quadcast"
    CLICANDO = "janela de cliques"
    CONCLUIDO = "concluído"
    INTERROMPIDO = "interrompido"
    ERRO_SEGURO = "erro seguro"


@dataclass(frozen=True)
class ConfiguracaoCombo:
    """Limites explícitos da execução autônoma."""

    alvo_cookies: float = 1e72
    busca_maxima_spells: int = 5_000
    maximo_lumps_alinhamento: int = 64
    building_specials_totais: int = 3
    intervalo_verificacao: float = 1.0
    duracao_minima_buff: float = 15.0
    usar_sugar_frenzy: bool = True
    usar_loans: bool = True
    pausar_antes_ultimos_skips: bool = False

    def __post_init__(self) -> None:
        if self.alvo_cookies <= 0:
            raise ValueError("O alvo de cookies deve ser positivo")
        if not 4 <= self.busca_maxima_spells <= 100_000:
            raise ValueError("A busca deve ficar entre 4 e 100.000 spells")
        if not 0 <= self.maximo_lumps_alinhamento <= 10_000:
            raise ValueError("O limite de lumps é inválido")
        if not 1 <= self.building_specials_totais <= 6:
            raise ValueError("A quantidade de Building Specials é inválida")
        if not 0.1 <= self.intervalo_verificacao <= 60.0:
            raise ValueError("O intervalo de verificação é inválido")
        if not 5.0 <= self.duracao_minima_buff <= 120.0:
            raise ValueError("A duração mínima de buff é inválida")


@dataclass(frozen=True)
class PlanoCombo:
    """Melhor janela encontrada para o snapshot corrente."""

    seed: str
    versao: str
    cast_atual: int
    cast_inicial: int
    season: str
    resultados: Tuple[str, ...]
    spells_a_pular: int
    building_specials_spell: int
    building_specials_naturais: int
    score: float

    @property
    def resumo(self) -> str:
        efeitos = " → ".join(self.resultados)
        return (
            f"cast {self.cast_inicial} ({self.spells_a_pular} skips), "
            f"{self.season}: {efeitos}"
        )


@dataclass(frozen=True)
class RelatorioCombo:
    """Atualização imutável enviada pelo worker à interface."""

    estado: EstadoCombo
    mensagem: str
    proximo_passo: str = ""
    plano: Optional[PlanoCombo] = None
    cast_atual: Optional[int] = None
    mana: Optional[float] = None
    mana_maxima: Optional[float] = None
    lumps: Optional[int] = None
    lumps_gastos: int = 0
    cookies_assados: Optional[float] = None
    buffs_ativos: Tuple[str, ...] = field(default_factory=tuple)
    building_specials_ativos: int = 0
    garden_maduras: int = 0
    garden_total: int = 0
    erro: str = ""

    @property
    def terminal(self) -> bool:
        return self.estado in {
            EstadoCombo.CONCLUIDO,
            EstadoCombo.INTERROMPIDO,
            EstadoCombo.ERRO_SEGURO,
        }
