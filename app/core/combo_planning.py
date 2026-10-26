"""Estimativas comparáveis de preparo e ganho, sem prometer um resultado."""
import math


def estimate(candidate, snapshot, config):
    """Modelo prudente: usa o menor bônus de construção elegível e desconto de 50%."""
    skipped = max(0, candidate['startCast'] - int(snapshot.get('spellsCastTotal', 0)))
    cost = max(1, float(snapshot.get('skipSpellCost', 1)))
    magic = max(1, float(snapshot.get('magicM', 100)))
    # Estimativa de recargas: não é uma previsão exata do tempo de regeneração.
    bars = math.ceil(skipped * cost / magic)
    cooldown = max(0, float(snapshot.get('lumpRefillRemaining', 0)))
    # Regeneração do Grimoire: 0,002 * sqrt(mana/max(máximo,100)) por quadro.
    def regen(low, high):
        return 2 * math.sqrt(max(magic, 100)) / .06 * (math.sqrt(high) - math.sqrt(max(.0004, low)))
    natural_preparation = skipped * regen(max(0, magic-cost), magic)
    reserved = 1 + int(config.usar_sugar_frenzy and not snapshot.get('sugarFrenzyUsed') and config.maximo_lumps_total >= 2)
    refills = min(max(0, config.maximo_lumps_total-reserved), max(0, int(snapshot.get('lumps', 0))-reserved))
    with_refills = min(bars, refills) * 900 + max(0, bars-refills) * regen(0, magic)
    preparation = skipped * config.intervalo_verificacao + min(natural_preparation, with_refills) + cooldown
    if not skipped:
        preparation = max(cooldown, regen(min(magic, max(0, float(snapshot.get('magic', 0)))), magic))
    natural = candidate['naturalBuildingSpecials']
    wait = (natural + 1) * 180  # Comparação inicial, sem probabilidade empírica.
    if snapshot.get('buffs'):
        available = sum(b.get('type') == 'building buff' and b.get('buildingId') != 7
                        and float(b.get('timeSeconds', 0)) >= config.duracao_minima_buff
                        for b in snapshot['buffs'])
        wait = max(0, natural - available) * 180
        if not any(b.get('type') == 'dragon harvest' and float(b.get('timeSeconds', 0)) >= config.duracao_minima_buff for b in snapshot['buffs']):
            wait += 180
    gain = None
    mouse = float(snapshot.get('mouseCps') or 0)
    amounts = [int(b.get('amount', 0)) for b in snapshot.get('buildings', ())
               if int(b.get('id', -1)) != 7 and int(b.get('amount', 0)) > 0]
    if mouse > 0 and amounts:
        active = math.prod(max(1, float(b.get('multCpS', 1))) * max(1, float(b.get('multClick', 1)))
                           for b in snapshot.get('buffs', ()))
        base = mouse / active
        bonuses = candidate['spellBuildingSpecials'] + natural
        actual = [b for b in snapshot.get('buffs', ()) if b.get('type') == 'building buff'
                  and b.get('buildingId') != 7 and float(b.get('timeSeconds', 0)) >= config.duracao_minima_buff]
        missing = max(0, natural-len(actual))
        bs = max(1, min(amounts) * .1) ** (candidate['spellBuildingSpecials']+missing)
        bs *= math.prod(max(1, float(b.get('multCpS', 1))) for b in actual)
        # Não conta auras, vendas, empréstimos nem mudanças do Garden como ganho garantido.
        sugar = 3 if config.usar_sugar_frenzy and not snapshot.get('sugarFrenzyUsed') and config.maximo_lumps_total >= 2 else 1
        clicks = min(config.cliques_por_segundo, 100) * 5
        gain = base * 7 * 15 * 777 * 666 * bs * sugar * clicks * .5
    return dict(candidate, preparationSeconds=preparation, waitScoreSeconds=wait,
                estimatedGain=gain, score=preparation+wait)


def choose(candidates, snapshot, config):
    ranked = [estimate(c, snapshot, config) for c in candidates]
    within_deadline = [c for c in ranked if c['preparationSeconds'] <= config.tempo_maximo_espera]
    if within_deadline:
        ranked = within_deadline
    # Maximiza o ganho estimado por tempo de preparo/espera, sem meta de parada.
    return max(ranked, key=lambda c: ((c['estimatedGain'] or 0) / max(60, c['score']),
                                      -c['score'], -c['skipCount'])) if ranked else None
