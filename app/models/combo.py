"""Modelos do modo de combo planejado para o Cookie Clicker."""

from dataclasses import dataclass, field
from enum import Enum
import math
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

    busca_maxima_spells: int = 5_000
    maximo_lumps_total: int = 64
    building_specials_totais: int = 2
    intervalo_verificacao: float = 0.2
    duracao_minima_buff: float = 12.0
    tempo_maximo_espera: float = 10_800.0
    usar_sugar_frenzy: bool = True
    usar_loans: bool = True
    pausar_antes_ultimos_skips: bool = False
    reserva_caixa_percentual: float = 80.0
    permitir_converter_garden: bool = False
    otimizar_garden_final: bool = True
    cliques_por_segundo: float = 100.0

    def __post_init__(self) -> None:
        if not 1 <= self.cliques_por_segundo <= 1000:
            raise ValueError("A velocidade estimada deve ficar entre 1 e 1.000 cliques por segundo.")
        if not math.isfinite(self.reserva_caixa_percentual) or not 0 <= self.reserva_caixa_percentual <= 99:
            raise ValueError("A reserva de biscoitos deve ficar entre 0% e 99%.")
        if not 4 <= self.busca_maxima_spells <= 100_000:
            raise ValueError("Analise entre 4 e 100.000 magias futuras.")
        if not 0 <= self.maximo_lumps_total <= 10_000:
            raise ValueError("O limite de lumps é inválido")
        if not 1 <= self.building_specials_totais <= 6:
            raise ValueError("A quantidade de Building Specials é inválida")
        if not 0.1 <= self.intervalo_verificacao <= 60.0:
            raise ValueError("O intervalo de verificação é inválido")
        if not 5.0 <= self.duracao_minima_buff <= 120.0:
            raise ValueError("A duração mínima de buff é inválida")
        if not 60 <= self.tempo_maximo_espera <= 86_400:
            raise ValueError("O limite de espera deve ficar entre 1 minuto e 24 horas")


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
    ganho_estimado: Optional[float] = None
    preparo_estimado: float = 0.0

    @property
    def resumo(self) -> str:
        names = {"click frenzy": "Frenesi de cliques", "frenzy": "Frenesi ×7",
                 "building special": "Bônus de construção", "blood frenzy": "Frenesi ancestral",
                 "cookie storm drop": "Biscoito da tempestade", "multiply cookies": "Sorte"}
        efeitos = " + ".join(names.get(effect, effect) for effect in self.resultados)
        preparation = f"{self.spells_a_pular} magias de preparação" if self.spells_a_pular else "Sequência pronta"
        estimate = f" · Ganho estimado: {self.ganho_estimado:.2e} · Preparo: ~{self.preparo_estimado/60:.0f} min" if self.ganho_estimado is not None else ""
        return f"{efeitos} · {preparation}{estimate}"



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
    ciclos_concluidos: int = 0
    erro: str = ""

    @property
    def terminal(self) -> bool:
        return self.estado in {
            EstadoCombo.CONCLUIDO,
            EstadoCombo.INTERROMPIDO,
            EstadoCombo.ERRO_SEGURO,
        }
