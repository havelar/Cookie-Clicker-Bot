"""Renovação de temporadas por meio da compra nativa do jogo."""

AUTO_SEASON_SCRIPT = r"""(() => {
const G=globalThis.Game, season=__SEASON__;
const result=(reason,message,retryAfterMs=60000)=>({reason,message,retryAfterMs});
if (!G || !G.ready || typeof G.Has!=='function')
    return result('unavailable','Aguardando o jogo ficar pronto.');
if (G.OnAscend || G.AscendTimer || G.promptOn)
    return result('busy','Aguardando fechar a confirmação ou ascensão.',5000);
if (G.season===season) {
    const remaining=Number(G.seasonT), fps=Number(G.fps);
    const retry=remaining>0 && fps>0 ? Math.min(60000,Math.max(1000,remaining/fps*1000+100)) : 60000;
    return result('active','A temporada escolhida está ativa.',retry);
}
if (!G.Has('Season switcher'))
    return result('locked','Requer o upgrade celestial Season switcher.');
const entry=G.seasons && G.seasons[season];
const upgrade=entry && G.Upgrades && G.Upgrades[entry.trigger];
if (!upgrade || !upgrade.unlocked || upgrade.bought || typeof upgrade.buy!=='function' || typeof upgrade.getPrice!=='function')
    return result('unavailable','O biscoito da temporada ainda não está disponível.');
const price=Number(upgrade.getPrice()), cookies=Number(G.cookies);
if (!Number.isFinite(price) || price<0 || !Number.isFinite(cookies))
    return result('unavailable','Não foi possível confirmar o preço da temporada.');
if (cookies<price)
    return result('funds','Aguardando saldo para ativar a temporada.',10000);
upgrade.buy();
if (G.season!==season)
    return result('failed','O jogo não confirmou a ativação da temporada.',10000);
// A compra nativa atualiza os efeitos; solicita também a atualização da loja.
G.storeToRefresh=1;
G.upgradesToRebuild=1;
G.recalculateGains=1;
return result('activated','Temporada ativada e confirmada.');
})()"""
