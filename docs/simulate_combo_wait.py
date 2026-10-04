"""Simulação local de oportunidades naturais (não acessa nem altera o jogo).

Modelo do runtime 2.053 observado em 03/10/2026: sem wrath/Dragonflight,
Reaper of Fields, Valentine, 20 prédios elegíveis e cookies duplos de 1%.
Ignora a aceleração de chains, representa storms como eventos sem buff útil.
Garden e frequência constantes: cenários, não previsão do próximo cookie.
"""
import bisect
import json
import random


def spawn_cdf(minimum, maximum, fps=30):
    survival = 1.0
    cdf = []
    for frame in range(1, round(maximum * fps) + 1):
        hazard = min(1.0, max(0.0, (frame / fps - minimum) / (maximum - minimum)) ** 5)
        survival *= 1 - hazard
        cdf.append(1 - survival)
    return cdf


def outcome(rng, last):
    choices = ["frenzy", "lucky"]
    if rng.random() < .03:
        choices += ["chain", "storm"]
    if rng.random() < .1:
        choices += ["click"]
    if rng.random() < .25:
        choices += ["building"]
    if rng.random() < .0005:
        choices += ["lump"]
    if rng.random() < .15 or rng.random() < .05:
        choices += ["harvest"]
    if last in choices and rng.random() < .8:
        choices.remove(last)
    if rng.random() < .0001:
        choices += ["blab"]
    return rng.choice(choices)


def simulate(natural_bs, minimum_buff, spell_frenzy, trials=10000, frequency_scale=1.0):
    rng = random.Random(20261003)
    cdf = spawn_cdf(46.4666666667 / frequency_scale, 139.3333333333 / frequency_scale)
    successful = []
    counts = {1: 0, 2: 0, 3: 0}
    for _ in range(trials):
        now, last, frenzy, harvest = 0.0, "", 0.0, 0.0
        buildings = {}
        while now < 10800:
            now += (bisect.bisect_left(cdf, rng.random()) + 1) / 30 + .2
            for _ in range(1 + (rng.random() < .01)):
                last = outcome(rng, last)
                if last == "frenzy":
                    frenzy = max(now, frenzy) + 184
                elif last == "harvest":
                    harvest = max(now, harvest) + 143
                elif last == "building":
                    building = rng.randrange(20)
                    buildings[building] = max(now, buildings.get(building, 0)) + 72
            if (harvest - now >= minimum_buff
                    and (spell_frenzy or frenzy - now >= minimum_buff)
                    and sum(expiry - now >= minimum_buff for b, expiry in buildings.items() if b != 7) >= natural_bs):
                if now <= 10800:
                    successful.append(now)
                    for hours in counts:
                        counts[hours] += now <= hours * 3600
                break
    successful.sort()
    median = successful[trials // 2] / 60 if len(successful) > trials // 2 else None
    mean_interval = sum(1 - value for value in cdf) / 30 + 1 / 30 + .2
    return {"trials": trials, "mean_cookie_seconds": round(mean_interval, 1),
            "median_minutes_censored_at_180": round(median, 1) if median else None,
            "opportunity_probability_by_hours": {h: round(c / trials, 4) for h, c in counts.items()}}


if __name__ == "__main__":
    print(json.dumps({
        "old_2_natural": simulate(2, 15, False),
        "new_1_natural": simulate(1, 12, True),
        "new_hypothetical_double_frequency": simulate(1, 12, True, frequency_scale=2),
    }, indent=2))
