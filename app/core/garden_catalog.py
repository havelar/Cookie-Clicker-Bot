"""Catálogo declarativo das mutações do Garden.

Fonte validada em 27/09/2026: código oficial de
https://orteil.dashnet.org/cookieclicker/minigameGarden.js, especialmente
``M.plants``, ``M.getMuts`` e ``M.soils``. As chaves são as chaves técnicas
do runtime; nomes e observações abaixo são destinados à interface em português.
"""
from dataclasses import dataclass, field
from typing import Mapping, Tuple


@dataclass(frozen=True)
class ParentRequirement:
    """Quantidade e maturidade exigidas de uma planta-pai."""

    key: str
    count: int = 1
    mature: bool = True


@dataclass(frozen=True)
class GardenRecipe:
    """Receita preferencial usada pela Fazendeira para uma semente."""

    key: str
    name: str
    parents: Tuple[ParentRequirement, ...] = field(default_factory=tuple)
    maximum_neighbors: Tuple[Tuple[str, int], ...] = field(default_factory=tuple)
    strategy: str = "mutacao_adjacente"
    condition: str = "Colher a planta-alvo quando estiver madura para desbloquear a semente."
    notes: str = ""
    source_probability: str = ""


def _p(key: str, count: int = 1, mature: bool = True) -> ParentRequirement:
    return ParentRequirement(key, count, mature)


# Uma receita preferencial por meta. O runtime possui alternativas para algumas
# plantas; elas ficam registradas em ``notes`` sem duplicar lógica no planejador.
GARDEN_CATALOG: Mapping[str, GardenRecipe] = {
    "bakerWheat": GardenRecipe("bakerWheat", "Baker's wheat", strategy="inicial", condition="Semente inicial do Garden."),
    "thumbcorn": GardenRecipe("thumbcorn", "Thumbcorn", (_p("bakerWheat", 2),), source_probability="5%"),
    "cronerice": GardenRecipe("cronerice", "Cronerice", (_p("bakerWheat"), _p("thumbcorn")), source_probability="1%"),
    "gildmillet": GardenRecipe("gildmillet", "Gildmillet", (_p("cronerice"), _p("thumbcorn")), source_probability="3%"),
    "clover": GardenRecipe("clover", "Ordinary clover", (_p("bakerWheat"), _p("gildmillet")), source_probability="3%"),
    "goldenClover": GardenRecipe("goldenClover", "Golden clover", (_p("clover", 4),), strategy="anel", source_probability="0,07%", notes="Também pode surgir de Baker's wheat + Gildmillet."),
    "shimmerlily": GardenRecipe("shimmerlily", "Shimmerlily", (_p("clover"), _p("gildmillet")), source_probability="2%"),
    "elderwort": GardenRecipe("elderwort", "Elderwort", (_p("shimmerlily"), _p("cronerice")), source_probability="1%", notes="Imortal depois de plantada."),
    "bakeberry": GardenRecipe("bakeberry", "Bakeberry", (_p("bakerWheat", 2),), source_probability="0,1%"),
    "chocoroot": GardenRecipe("chocoroot", "Chocoroot", (_p("bakerWheat"), _p("brownMold", 1, False)), source_probability="10%"),
    "whiteChocoroot": GardenRecipe("whiteChocoroot", "White chocoroot", (_p("chocoroot"), _p("whiteMildew", 1, False)), source_probability="10%"),
    "whiteMildew": GardenRecipe("whiteMildew", "White mildew", (_p("brownMold"),), (("brownMold", 1),), strategy="fungo_espalhamento", source_probability="50%", notes="Exige um Brown mold maduro e no máximo um Brown mold vizinho."),
    "brownMold": GardenRecipe("brownMold", "Brown mold", (_p("meddleweed", 1, False),), strategy="derivado_erva", source_probability="até 20%", notes="Pode aparecer ao arrancar uma Meddleweed; a chance cresce com a idade."),
    "meddleweed": GardenRecipe("meddleweed", "Meddleweed", strategy="erva_espontanea", condition="Aguardar surgimento espontâneo em canteiro vazio e colher quando madura.", source_probability="0,2% base por tick"),
    "whiskerbloom": GardenRecipe("whiskerbloom", "Whiskerbloom", (_p("shimmerlily"), _p("whiteChocoroot")), source_probability="1%"),
    "chimerose": GardenRecipe("chimerose", "Chimerose", (_p("shimmerlily"), _p("whiskerbloom")), source_probability="5%"),
    "nursetulip": GardenRecipe("nursetulip", "Nursetulip", (_p("whiskerbloom", 2),), source_probability="5%"),
    "drowsyfern": GardenRecipe("drowsyfern", "Drowsyfern", (_p("chocoroot"), _p("keenmoss")), source_probability="0,5%"),
    "wardlichen": GardenRecipe("wardlichen", "Wardlichen", (_p("cronerice"), _p("keenmoss")), source_probability="0,5%", notes="Cronerice + White mildew também funciona."),
    "keenmoss": GardenRecipe("keenmoss", "Keenmoss", (_p("greenRot"), _p("brownMold")), source_probability="10%"),
    "queenbeet": GardenRecipe("queenbeet", "Queenbeet", (_p("chocoroot"), _p("bakeberry")), source_probability="1%"),
    "queenbeetLump": GardenRecipe("queenbeetLump", "Juicy queenbeet", (_p("queenbeet", 8),), strategy="anel", source_probability="0,1%", notes="A semente não é plantável; requer oito Queenbeets maduras ao redor do centro."),
    "duketater": GardenRecipe("duketater", "Duketater", (_p("queenbeet", 2),), source_probability="0,1%"),
    "crumbspore": GardenRecipe("crumbspore", "Crumbspore", (_p("meddleweed", 1, False),), strategy="derivado_erva", source_probability="até 20%", notes="Pode aparecer ao arrancar uma Meddleweed; a chance cresce com a idade."),
    "doughshroom": GardenRecipe("doughshroom", "Doughshroom", (_p("crumbspore", 2),), source_probability="0,5%"),
    "glovemorel": GardenRecipe("glovemorel", "Glovemorel", (_p("crumbspore"), _p("thumbcorn")), source_probability="2%"),
    "cheapcap": GardenRecipe("cheapcap", "Cheapcap", (_p("crumbspore"), _p("shimmerlily")), source_probability="4%", notes="Pode morrer ao congelar; a Fazendeira não congela automaticamente."),
    "foolBolete": GardenRecipe("foolBolete", "Fool's bolete", (_p("doughshroom"), _p("greenRot")), source_probability="4%"),
    "wrinklegill": GardenRecipe("wrinklegill", "Wrinklegill", (_p("crumbspore"), _p("brownMold")), source_probability="6%"),
    "greenRot": GardenRecipe("greenRot", "Green rot", (_p("whiteMildew"), _p("clover")), source_probability="5%"),
    "shriekbulb": GardenRecipe("shriekbulb", "Shriekbulb", (_p("queenbeet", 5),), strategy="anel", source_probability="0,1%", notes="Há receitas alternativas com Elderwort, Duketater, Doughshroom ou Wrinklegill."),
    "tidygrass": GardenRecipe("tidygrass", "Tidygrass", (_p("bakerWheat"), _p("whiteChocoroot")), source_probability="0,2%"),
    "everdaisy": GardenRecipe("everdaisy", "Everdaisy", (_p("tidygrass", 3), _p("elderwort", 3)), strategy="anel", source_probability="0,2%", notes="Os seis pais devem estar maduros; a planta-alvo é imortal."),
    "ichorpuff": GardenRecipe("ichorpuff", "Ichorpuff", (_p("elderwort"), _p("crumbspore")), source_probability="0,2%"),
}

TARGET_SEED_KEYS: Tuple[str, ...] = tuple(GARDEN_CATALOG)


def validate_catalog() -> Tuple[str, ...]:
    """Retorna problemas estruturais sem depender do runtime do jogo."""
    problems = []
    for key, recipe in GARDEN_CATALOG.items():
        if key != recipe.key:
            problems.append(f"Chave divergente: {key} != {recipe.key}")
        for parent in recipe.parents:
            if parent.key not in GARDEN_CATALOG:
                problems.append(f"Pai desconhecido em {key}: {parent.key}")
            if parent.count < 1:
                problems.append(f"Quantidade inválida em {key}: {parent.key}")
        for neighbor_key, maximum in recipe.maximum_neighbors:
            if neighbor_key not in GARDEN_CATALOG or maximum < 0:
                problems.append(f"Limite de vizinhos inválido em {key}: {neighbor_key}")
    return tuple(problems)
