"""Regras compartilhadas pela previsão e execução econômica de FtHoF.

Fórmulas do Grimoire e preços: minigameGrimoire.js / main.js do jogo.
Nenhuma função de planejamento altera o save.
"""

SIMPLE_FARM_HELPERS = r"""
            const seasonal=Game.season==='valentines'||Game.season==='easter';
            function predict(cast,existing) {
                const oldRandom=Math.random;
                try {
                    Math.seedrandom(String(Game.seed)+'/'+cast);
                    const success=Math.random()<1-(failBase+0.15*existing);
                    Math.random(); Math.random(); if (seasonal) Math.random();
                    let choices;
                    if (success) {
                        choices=['frenzy','multiply cookies','click frenzy'];
                        if (Math.random()<0.1) choices.push('cookie storm','cookie storm','blab');
                        if (Number(Game.BuildingsOwned)>=10 && Math.random()<0.25) choices.push('building special');
                        if (Math.random()<0.15) choices=['cookie storm drop'];
                        if (Math.random()<0.0001) choices.push('free sugar lump');
                    } else {
                        choices=['clot','ruin cookies'];
                        if (Math.random()<0.1) choices.push('cursed finger','blood frenzy');
                        if (Math.random()<0.003) choices.push('free sugar lump');
                        if (Math.random()<0.1) choices=['blab'];
                    }
                    return choices[Math.floor(Math.random()*choices.length)];
                } finally { Math.random=oldRandom; }
            }

            function complementary(results) {
                if (results.length!==2 || results.filter(x=>x==='click frenzy').length!==1) return false;
                const other=results.find(x=>x!=='click frenzy');
                if (!['frenzy','building special','blood frenzy'].includes(other)) return false;
                // Buffs idênticos só estendem a duração. BS só revela o prédio ao abrir.
                return other==='building special' || !Object.values(Game.buffs||{}).some(
                    b=>b && b.type && b.type.name===other && Number(b.time)>0);
            }
            function dualPlan() {
                const amount=Number(tower.amount), level=Math.max(1,Number(tower.level));
                const before=Number(Game.cookies);
                const reserve=Math.max(cashFloor,before*reserveFraction,Math.max(0,Number(Game.cookiesPs)||0)*6000);
                const headroom=Math.max(0,before-reserve);
                const investmentBudget=Math.max(0,Math.min(before*fraction-spentInWindow,headroom));
                const unavailable=message=>({ok:false,message,reserve,budget:headroom,investmentBudget});
                if (!Number.isInteger(amount) || amount<2 || amount>100000 || !Number.isFinite(level) ||
                    typeof M.computeMagicM!=='function' || typeof tower.sell!=='function' ||
                    typeof tower.buy!=='function' || typeof Game.modifyBuildingPrice!=='function')
                    return unavailable('Torres insuficientes ou cálculo de recompra indisponível');
                const magicAt=n=>Math.floor(4+Math.pow(n,0.6)+Math.log((n+(level-1)*10)/15+1)*15);
                const aura=typeof Game.auraMult==='function'?Number(Game.auraMult('Supreme Intellect')):0;
                const costAt=n=>Math.floor((Number(spell.costMin)+magicAt(n)*Number(spell.costPercent))*(1-0.1*aura));
                if (magicAt(amount)!==Number(M.magicM) || costAt(amount)!==Number(M.getSpellCost(spell)))
                    return unavailable('Fórmula de mana divergente; usando uma magia');
                const remaining=Number(M.magicM)-costAt(amount);
                let target=amount-1;
                // Mantém o maior número possível de torres, vendendo só o necessário.
                while (target>=1 && Math.min(remaining,magicAt(target))<costAt(target)) target--;
                if (target<1 || Number(Game.BuildingsOwned)-(amount-target)<10)
                    return unavailable('Mana ou construções insuficientes para duas magias');
                let rebuy=0;
                try {
                    // buy() cobra cada unidade arredondada; getSumPrice arredonda só a soma.
                    for (let i=target;i<amount;i++) {
                        const base=Number(tower.basePrice)*Math.pow(Number(Game.priceIncrease),Math.max(0,i-Number(tower.free||0)));
                        rebuy+=Math.ceil(Number(Game.modifyBuildingPrice(tower,base)));
                    }
                } catch (_) { rebuy=Infinity; }
                // Não depende do produto da venda nem dos ganhos futuros do combo.
                if (!Number.isFinite(before) || !Number.isFinite(rebuy) || rebuy<=0 || rebuy>headroom)
                    return unavailable('Recompra não cabe no orçamento livre; reserva preservada');
                return {ok:true,originalTowers:amount,targetTowers:target,rebuy,reserve,
                    budget:headroom,investmentBudget};
            }
"""
