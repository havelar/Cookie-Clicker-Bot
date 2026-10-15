"""Distribui receitas pelo canteiro desbloqueado, preservando posições fixas."""
from functools import lru_cache
from itertools import combinations
from app.core.garden_catalog import GARDEN_CATALOG


class _LayoutSearch:
    def __init__(self, tiles, requirements, limits, fixed, preferred):
        self.tiles = tiles
        self.indices = {p:i for i,p in enumerate(tiles)}
        self.keys = tuple(key for key, _ in requirements)
        self.required = tuple(count for _, count in requirements)
        codes = {key:i+1 for i,key in enumerate(self.keys)}
        self.fixed = {self.indices[pos]:codes.get(key,-1) for pos,key in fixed}
        self.mutable = tuple(i for i in range(len(tiles)) if i not in self.fixed)
        self.preferred = {self.indices[pos]:codes[key] for pos,key in preferred if key in codes}
        self.neighbors = tuple(tuple(j for j,(px,py) in enumerate(tiles)
                              if max(abs(px-x),abs(py-y))==1) for x,y in tiles)
        self.masks = tuple(sum(1<<j for j in ns) for ns in self.neighbors)
        self.fixed_mask = sum(1<<i for i in self.fixed)
        self.limits = []
        for key, maximum in limits:
            if key in codes:
                self.limits.append((codes[key]-1, maximum, None))
            else:
                positions = {self.indices[pos] for pos,k in fixed if k==key}
                self.limits.append((None,maximum,tuple(sum(j in positions for j in ns) for ns in self.neighbors)))

    def load(self, layout):
        codes = {key:i+1 for i,key in enumerate(self.keys)}
        self.board = [0]*len(self.tiles)
        for pos,key in layout.items():
            if pos in self.indices and self.indices[pos] not in self.fixed and key in codes:
                self.board[self.indices[pos]] = codes[key]
        for i,code in self.fixed.items():self.board[i]=code
        self.counts = [[0]*len(self.tiles) for _ in self.keys]
        for i,code in enumerate(self.board):
            if code>0:
                for j in self.neighbors[i]:self.counts[code-1][j]+=1
        self.valid = [self.is_valid(i) for i in range(len(self.tiles))]

    def is_valid(self, i):
        return (self.board[i]==0 and all(self.counts[k][i]>=need for k,need in enumerate(self.required))
                and all((self.counts[k][i] if k is not None else counts[i])<=maximum
                        for k,maximum,counts in self.limits))

    def score(self):
        valid_mask = sum(1<<i for i,ready in enumerate(self.valid) if ready)
        support = 0
        for i,ready in enumerate(self.valid):
            if ready:support |= self.masks[i]
        parents = sum(1<<i for i,code in enumerate(self.board) if code>0)
        coverage = valid_mask | (support & parents) | self.fixed_mask
        changes = sum(self.board[i]!=code for i,code in self.preferred.items())
        return valid_mask.bit_count(), coverage.bit_count(), -parents.bit_count(), -changes

    def change(self, changes):
        previous = [(i,self.board[i]) for i,_ in changes]
        affected = set()
        for i,new in changes:
            old = self.board[i]
            self.board[i]=new
            affected.add(i)
            affected.update(self.neighbors[i])
            for j in self.neighbors[i]:
                if old>0:self.counts[old-1][j]-=1
                if new>0:self.counts[new-1][j]+=1
        for i in affected:self.valid[i]=self.is_valid(i)
        return previous

    def greedy(self, order):
        for center in order:
            if self.board[center]!=0 or self.valid[center]:continue
            empty = [i for i in self.neighbors[center] if self.board[i]==0 and not self.valid[i]]
            needs = [max(0,need-self.counts[k][center]) for k,need in enumerate(self.required)]
            if sum(needs)>len(empty):continue
            # Espécies alternadas evitam separar todos os pais de uma receita mista.
            assignments = [code for round_ in range(max(needs,default=0))
                           for code,need in enumerate(needs,1) if round_<need]
            best = None
            current = self.score()
            for reverse in (False,True):
                available = sorted(empty,key=lambda i:(-len(self.neighbors[i]),self.tiles[i]),reverse=reverse)
                changes = list(zip(available,assignments))
                old = self.change(changes)
                score = self.score()
                self.change(old)
                if score>current and (best is None or score>best[0]):best=(score,changes)
            if best:self.change(best[1])

    def expand_group(self, *, neutral=False):
        """Abre um novo centro com vários pais de uma vez, sem sacrificar centros ativos."""
        current = self.score()
        best = None
        alternatives = []
        for center in self.mutable:
            if self.valid[center]:continue
            previous_center = self.change([(center,0)])
            available = [i for i in self.neighbors[center] if self.board[i]==0 and not self.valid[i]]
            needs = [max(0,need-self.counts[k][center]) for k,need in enumerate(self.required)]
            if sum(needs)<=len(available):
                first_options = combinations(available,needs[0])
                for first in first_options:
                    remaining = [i for i in available if i not in first]
                    second_options = combinations(remaining,needs[1]) if len(needs)>1 else ((),)
                    for second in second_options:
                        changes = [(i,1) for i in first]+[(i,2) for i in second]
                        old = self.change(changes)
                        score = self.score()
                        self.change(old)
                        proposed = [(center,0),*changes]
                        if score>current and (best is None or score>best[0]):
                            best=(score,proposed)
                        elif neutral and score==current and any(self.board[i]!=code for i,code in proposed):
                            alternatives.append(proposed)
            self.change(previous_center)
        return alternatives[:32] if neutral else best

    def best_single(self, current):
        best = None
        for i in self.mutable:
            for code in range(len(self.keys)+1):
                if code==self.board[i]:continue
                changes = [(i,code)]
                old = self.change(changes)
                score = self.score()
                self.change(old)
                if score>current and (best is None or score>best[0]):best=(score,changes)
        return best

    def improve(self):
        while True:
            current = self.score()
            best = self.best_single(current)
            if best:
                self.change(best[1]);continue
            for i,j in combinations(self.mutable,2):
                if self.board[i]==self.board[j]:continue
                changes = [(i,self.board[j]),(j,self.board[i])]
                old = self.change(changes)
                score = self.score()
                self.change(old)
                if score>current and (best is None or score>best[0]):best=(score,changes)
            if not best:best=self.expand_group()
            if not best:
                for neutral in self.expand_group(neutral=True):
                    old = self.change(neutral)
                    improvement = self.best_single(current)
                    self.change(old)
                    if improvement and (best is None or improvement[0]>best[0]):
                        combined = dict(neutral)
                        combined.update(improvement[1])
                        best=(improvement[0],list(combined.items()))
            if not best:break
            self.change(best[1])

    def export(self):
        return tuple((self.tiles[i],self.keys[code-1]) for i,code in enumerate(self.board)
                     if code>0 and i not in self.fixed), tuple(self.tiles[i] for i,ready in enumerate(self.valid) if ready)


@lru_cache(maxsize=128)
def _solve(tiles, requirements, limits, fixed, preferred, baseline):
    search = _LayoutSearch(tiles,requirements,limits,fixed,preferred)
    search.load(dict(baseline))
    best_score = search.score()
    best = search.export()
    # Mantém um setup completo em curso, sem reiniciar a maturação por ganhos marginais.
    search.load(dict(preferred))
    preferred_score = search.score()
    if preferred_score[0] and preferred_score[1]==len(tiles) and preferred_score[0]>=best_score[0]:
        return search.export()
    if best_score[0] and best_score[1]==len(tiles):return best
    if preferred_score>best_score:best_score,best=preferred_score,search.export()
    seeds = [dict(baseline),dict(preferred)]
    x0,y0 = min(x for x,y in tiles),min(y for x,y in tiles)
    first = requirements[0][0]
    if len(requirements)==1:
        if requirements[0][1]==1:
            for dx in range(3):
                for dy in range(3):
                    seeds.append({p:first for p in tiles if (p[0]-x0)%3==dx and (p[1]-y0)%3==dy})
        else:
            for axis in (0,1):
                for offset in range(3):
                    seeds.append({p:first for p in tiles if (p[axis]-(x0 if axis==0 else y0))%3==offset})
    else:
        second = requirements[1][0]
        for axis in (0,1):
            for offset in range(2):
                seeds.append({p:(first if ((p[axis]-(x0 if axis==0 else y0))//2)%2==0 else second)
                              for p in tiles if (p[axis]-(x0 if axis==0 else y0))%2==offset})
                seeds.append({p:(first if (p[1-axis]-(y0 if axis==0 else x0))%2==0 else second)
                              for p in tiles if (p[axis]-(x0 if axis==0 else y0))%3==offset})
    # Completa grupos pelo canteiro inteiro, em ambas as direções.
    for reverse in (False,True):
        search.load(dict(preferred))
        order = sorted(search.mutable,key=lambda i:(-len(search.neighbors[i]),search.tiles[i]),reverse=reverse)
        search.greedy(order)
        seeds.append(dict(search.export()[0]))
    # Refina somente os candidatos mais promissores; leituras seguintes usam cache.
    ranked = []
    seen = set()
    for seed in seeds:
        signature = tuple(sorted(seed.items()))
        if signature in seen:continue
        seen.add(signature)
        search.load(seed)
        ranked.append((search.score(),signature))
    for _,seed in sorted(ranked,reverse=True)[:4]:
        search.load(dict(seed))
        search.improve()
        score = search.score()
        if score>best_score:best_score,best=score,search.export()
    return best if best_score[0] else ((),())


def full_plot_layout(snapshot, recipe, baseline=None, *, preserve_parent_keys=()):
    """Retorna pais e espaços de mutação em todo o Garden, sem mover protegidas."""
    tiles = tuple(sorted(snapshot.unlocked_tiles))
    if not tiles or not recipe.parents:return None
    parent_keys = {r.key for r in recipe.parents}
    preserved = set(preserve_parent_keys) & parent_keys
    fixed = tuple(sorted(((p.x,p.y),p.key) for p in snapshot.plants
                         if (p.key not in GARDEN_CATALOG or p.key not in snapshot.unlocked_seed_keys
                             or p.key in preserved) and (p.x,p.y) in tiles))
    preferred = tuple(sorted(((p.x,p.y),p.key) for p in snapshot.plants
                             if p.key in parent_keys and (p.x,p.y) in tiles and ((p.x,p.y),p.key) not in fixed))
    desired, centers = _solve(tiles,tuple((r.key,r.count) for r in recipe.parents),
                             recipe.maximum_neighbors,fixed,preferred,tuple(sorted((baseline or {}).items())))
    if not centers:return None
    desired = dict(desired)
    desired.update((pos,key) for pos,key in fixed
                   if key in preserved and key in snapshot.unlocked_seed_keys)
    return desired,centers
