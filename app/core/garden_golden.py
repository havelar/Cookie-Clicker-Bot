"""Canteiro permanente para aumentar a frequência de Golden Cookies."""
from functools import lru_cache
from math import prod

GOLDEN = 'goldenClover'
NURSE = 'nursetulip'


def stage(age, mature):
    if age >= mature:return 1.0
    if age >= mature * .666:return .5
    if age >= mature * .333:return .25
    return .1


def frequency_bonus(plants, soil_multiplier=1.25):
    """Reproduz computeBoostPlot/computeEffs, sem amplificação recursiva das tulipas."""
    nurses = [(pos,power) for pos,(key,power) in plants.items() if key == NURSE]
    return sum(.03 * soil_multiplier * power * prod(
        1 + .2 * soil_multiplier * nurse_power
        for (nx,ny),nurse_power in nurses if max(abs(nx-x),abs(ny-y)) == 1
    ) for (x,y),(key,power) in plants.items() if key == GOLDEN)


@lru_cache(maxsize=128)
def golden_layout(tiles, blocked=()):
    """Compara faixas nas duas orientações; enumera layouts em canteiros pequenos."""
    available = tuple(sorted(set(tiles)-set(blocked)))
    if not available:return ()
    candidates = [{p:GOLDEN for p in available}]
    for axis in (0,1):
        for offset in (0,1):
            candidates.append({p:NURSE if (p[axis]+offset)%2 else GOLDEN for p in available})
    if len(available) <= 12:
        candidates.extend({p:NURSE if mask & (1<<i) else GOLDEN for i,p in enumerate(available)}
                          for mask in range(1<<len(available)))
    def score(layout):
        return round(frequency_bonus({p:(key,1) for p,key in layout.items()}),12)
    # A ordem fixa também mantém o desenho estável após mortes e replantios.
    best = max(candidates,key=score)
    if len(available)>12 and (len(available)!=36 or blocked):
        # Ajusta as bordas de canteiros menores e casas protegidas.
        for seed in candidates:
            layout = dict(seed)
            while True:
                current = score(layout)
                options = []
                for pos in available:
                    trial = dict(layout)
                    trial[pos] = GOLDEN if trial[pos]==NURSE else NURSE
                    options.append(trial)
                improved = max(options,key=score)
                if score(improved)<=current:break
                layout = improved
            if score(layout)>score(best):best=layout
    return tuple(sorted(best.items()))


def golden_soil(snapshot, desired):
    """Mantém Clay enquanto o efeito compensa, tolerando reposições pontuais."""
    plants = {(p.x,p.y):(p.key,stage(p.age,p.mature_age)) for p in snapshot.plants
              if desired.get((p.x,p.y))==p.key}
    peak = frequency_bonus({pos:(key,1) for pos,key in desired.items()})
    current = frequency_bonus(plants)
    # Histerese: crescer até 60% do potencial e recuperar abaixo de 40%.
    # Uma planta jovem isolada não reinicia o crescimento do canteiro inteiro.
    threshold = .4 if snapshot.soil_key=='clay' else .6
    soil = 'clay' if peak and current >= peak*threshold else 'fertilizer'
    return soil,current,peak
