"""Decisão atômica no runtime; o jogo processa a coleta no próximo frame."""
WRINKLER_SCRIPT = r"""(() => {
    const options = __OPTIONS__;
    if (typeof Game === 'undefined' || !Game.ready || Game.OnAscend || Game.AscendTimer > 0 ||
        !Array.isArray(Game.wrinklers) || typeof Game.getWrinklersMax !== 'function') return null;
    const capacity = Game.getWrinklersMax();
    if (!Number.isFinite(capacity) || capacity < 1) return null;
    const desired = Math.min(capacity, Math.max(1, Math.min(12, options.freeSlots)));
    const active = Game.wrinklers.map((w, index) => ({w, index})).filter(v => v.w && v.w.phase > 0);
    const shiny = active.filter(v => v.w.type === 1).length;
    const pending = active.filter(v => v.w.hp <= 0.5);
    let free = Math.max(0, capacity - active.length + pending.length);
    let multiplier = 1.1;
    if (Game.Has('Sacrilegious corruption')) multiplier *= 1.05;
    multiplier *= 1 + Game.auraMult('Dragon Guts') * 0.2;
    if (Game.Has('Wrinklerspawn')) multiplier *= 1.05;
    const scorn = Game.hasGod ? Game.hasGod('scorn') : 0;
    multiplier *= scorn === 1 ? 1.15 : scorn === 2 ? 1.1 : scorn === 3 ? 1.05 : 1;
    const payout = v => {
        const amount = Math.max(0, Number(v.w.sucked) || 0) * multiplier;
        return amount > 0.5 && Number.isFinite(amount) ? amount : 0;
    };
    let bank = Number(Game.cookies);
    if (!Number.isFinite(bank) || !Number.isFinite(multiplier)) return null;
    // Evita repetir uma coleta ainda não processada pelo frame nativo.
    bank += pending.filter(v => v.w.type === 0).reduce((sum, v) => sum + payout(v), 0);
    const normals = active.filter(v => v.w.type === 0 && v.w.hp > 0.5);
    normals.sort((a, b) => payout(a) - payout(b) || a.index - b.index);
    const popped = [];
    const pop = (v, reason) => {
        // Somente normais ativos. Nunca chama UpdateWrinklers nem altera tipo/RNG.
        if (v.w.type !== 0 || v.w.phase <= 0 || v.w.hp <= 0.5) return;
        const amount = payout(v);
        v.w.hp = 0;
        bank += amount; free++;
        popped.push({index: v.index, reason, estimatedCookies: amount});
    };
    while (free < desired && normals.length) pop(normals.shift(), 'vacancy');
    const requests = options.requests.filter(r => r.seed && r.seed === Game.seed &&
        Number.isFinite(r.target) && r.target > 0);
    const target = Math.min(Infinity, ...requests.filter(r => r.target > bank).map(r => r.target));
    // Só liquida por caixa quando consegue destravar a ação, mantendo um normal rendendo.
    normals.sort((a, b) => payout(b) - payout(a) || a.index - b.index);
    const spendable = normals.slice(0, Math.max(0, normals.length - 1));
    if (target > bank && bank + spendable.reduce((sum, v) => sum + payout(v), 0) >= target) {
        for (const v of spendable) {
            if (bank >= target) break;
            pop(v, 'cash');
        }
    }
    return {popped, capacity, freeSlots: free, desiredSlots: desired, shiny,
        blocked: free < desired, funded: requests.filter(r => bank >= r.target).map(r => r.source)};
})()"""
