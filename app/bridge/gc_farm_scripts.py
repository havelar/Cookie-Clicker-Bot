"""Leituras e ações do modo de coleta para a conquista de Golden Cookies."""

SNAPSHOT = r"""(() => {
const G=globalThis.Game;
if (!G || !G.ready || G.OnAscend || G.AscendTimer || G.ReincarnateTimer)
    return {available:false,message:'Jogo indisponível ou em transição.'};
if (!Number.isSafeInteger(G.goldenClicks) || G.goldenClicks<0 || !Number.isFinite(G.cookies) || G.cookies<0)
    return {available:false,message:'Contadores ou saldo inválidos.'};
return {available:true,seed:String(G.seed||''),count:G.goldenClicks,cookies:G.cookies,
    completed:!!G.HasAchiev('Seven horseshoes'),chain:!!G.shimmerTypes.golden.chain};
})()"""

COLLECT = r"""(() => {
const G=globalThis.Game, expectedSeed=__SEED__, manualLastClick=__MANUAL_LAST__;
if (!G || !G.ready || G.OnAscend || G.AscendTimer || G.ReincarnateTimer) return 0;
if (expectedSeed!==null && String(G.seed||'')!==expectedSeed) return 0;
if (typeof G.hasGod==='function' && G.hasGod('asceticism')) return 0;
let clicked=0;
// Biscoitos invocados e gotas de tempestade não avançam esta conquista.
for (const s of Array.from(G.shimmers||[])) {
    // Revalida antes de cada clique, inclusive com vários biscoitos em tela.
    if (manualLastClick && G.goldenClicks===27776) break;
    if (s.type==='golden' && s.spawnLead && !s.force && typeof s.pop==='function') {
        const before=G.goldenClicks;
        s.pop();
        clicked+=Math.max(0,G.goldenClicks-before);
    }
}
return clicked;
})()"""

PREPARE = r"""(() => {
const G=globalThis.Game, reserve=__RESERVE__, expectedSeed=__SEED__;
const fail=message=>({ok:false,message});
if (!G || !G.ready || G.OnAscend || G.AscendTimer || G.ReincarnateTimer)
    return fail('Jogo indisponível ou em transição.');
if (expectedSeed!==null && String(G.seed||'')!==expectedSeed) return fail('O save mudou; preparo cancelado.');
if (!Number.isFinite(G.cookies) || G.cookies<0) return fail('Saldo inválido; nenhuma alteração enviada.');
if (G.goldenClicks>=27777 || G.HasAchiev('Seven horseshoes')) return {ok:true,completed:true};
if (G.shimmerTypes.golden.chain>0) return {ok:true,chain:true,message:'Coletando a corrente; preparo adiado até ela terminar.'};
const floor=Number(G.cookies)*reserve/100;
function refresh() {
    G.recalculateGains=1; G.storeToRefresh=1; G.upgradesToRebuild=1;
}
function buy(name,confirmed,message) {
    const u=G.Upgrades && G.Upgrades[name];
    if (!u || !u.unlocked || u.bought || typeof u.buy!=='function')
        return fail('Indisponível: '+message);
    const price=Number(u.getPrice());
    if (!Number.isFinite(price) || price<0) return fail('Preço inválido: '+message);
    if (price>G.cookies-floor) return {ok:false,waiting:true,message:'Aguardando saldo livre: '+message};
    u.buy(); refresh();
    return {ok:!!confirmed(),changed:true,message};
}
const pending=[];
if (G.Has('Golden switch [off]')) {
    const result=buy('Golden switch [on]',()=>!G.Has('Golden switch [off]'),'Desligar o interruptor dourado.');
    if (result.ok || result.changed) return result;
    pending.push(result.message);
}
if (G.elderWrath>0) {
    // O pacto permanente recolheria todos os Wrinklers, inclusive os Shiny.
    const result=buy('Elder Pledge',()=>G.pledgeT>0,'Apaziguar as vovós sem recolher os Wrinklers.');
    if (result.ok || result.changed) return result;
    pending.push(result.message);
}
const P=G.Objects.Temple && G.Objects.Temple.minigame;
if (P && Array.isArray(P.slot) && P.gods) {
    const desired=P.gods.seasons;
    const harmful=new Set([P.gods.industry.id,P.gods.mother.id,P.gods.scorn.id,P.gods.asceticism.id]);
    const bad=P.slot.findIndex(id=>harmful.has(id));
    const slot=P.slot[0]!==desired.id?0:bad;
    if (slot>=0) {
        if (P.swaps<1) pending.push('Aguardando uma troca do Panteão.');
        else {
            if (slot===0) { P.slotGod(desired,0); P.useSwap(1); }
            else { const god=P.godsById[P.slot[slot]]; P.slotGod(god,-1); P.useSwap(1); }
            P.toRedraw=true; refresh();
            return {ok:slot===0?P.slot[0]===desired.id:P.slot[slot]===-1,changed:true,
                message:slot===0?'Selebrak colocado no diamante.':'Espírito que atrapalhava a coleta removido.'};
        }
    }
}
if (G.season!=='fools') {
    const result=buy("Fool's biscuit",()=>G.season==='fools','Ativar o Dia dos Negócios.');
    if (result.ok || result.changed) return result;
    pending.push(result.message);
}
const desired=(G.dragonAura===18 || G.dragonAura2===9) && G.dragonLevel>=27?[18,9]:[9,18];
for (let slot=0;slot<2;slot++) {
    if (slot===1 && G.dragonLevel<27) continue;
    const field=slot===0?'dragonAura':'dragonAura2', aura=desired[slot];
    if (G[field]===aura) continue;
    if (G.dragonLevel<aura+4) {pending.push('Treine o dragão para liberar as auras de frequência.');continue;}
    // Reprodução da confirmação nativa: uma construção por troca de aura.
    const building=Object.values(G.Objects).filter(o=>o.amount>0).pop();
    if (!building) {pending.push('Uma construção é necessária para trocar a aura.');continue;}
    const before=building.amount;
    building.sacrifice(1);
    if (building.amount!==before-1) return fail('Sacrifício da aura não confirmado.');
    G[field]=aura; refresh();
    return {ok:G[field]===aura,changed:true,message:'Aura de frequência ajustada e confirmada.'};
}
for (const name of ['Lucky day','Serendipity','Golden goose egg','Green yeast digestives','Startrade']) {
    const u=G.Upgrades[name];
    if (u && u.unlocked && !u.bought && u.pool!=='prestige' && u.pool!=='debug'
            && !(typeof u.isVaulted==='function' && u.isVaulted())) {
        const result=buy(name,()=>G.Has(name),'Comprar melhoria de frequência: '+(u.dname||name)+'.');
        if (result.ok || result.changed) return result;
        pending.push(result.message);
    }
}
if (!P || !Array.isArray(P.slot)) pending.push('Panteão indisponível; mantendo os demais bônus.');
return {ok:!pending.length,waiting:!!pending.length,message:pending.length?pending.join(' '):'Configuração de coleta mantida.'};
})()"""
