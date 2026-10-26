"""Previsão isolada de FtHoF, conforme a referência local do Grimoire."""

FTHOF_PLANNER_SCRIPT = r"""(() => {
const G=globalThis.Game, count=__COUNT__, mode=__MODE__;
const fail=message=>({ok:false,message});
const tower=G && G.Objects && G.Objects['Wizard tower'];
const M=tower && tower.minigameLoaded && tower.minigame;
const spell=M && M.spells && M.spells['hand of fate'];
if (!G || !G.ready || !M || !spell || typeof M.getFailChance!=='function' || typeof G.hasBuff!=='function')
    return fail('Abra o Grimório para consultar as próximas magias.');
if (G.OnAscend || G.AscendTimer) return fail('Aguardando concluir a ascensão.');
const current=Number(M.spellsCastTotal), visible=Number(G.shimmerTypes && G.shimmerTypes.golden && G.shimmerTypes.golden.n);
if (!Number.isSafeInteger(current) || current<0 || !Number.isInteger(visible) || visible<0)
    return fail('Não foi possível confirmar o contador de magias ou de biscoitos dourados.');
const failBase=Number(M.getFailChance(spell))-0.15*visible;
if (!Number.isFinite(failBase) || failBase<0 || failBase>1)
    return fail('Não foi possível confirmar a chance de falha da magia.');
const seed=String(G.seed||'');
if (!seed) return fail('Não foi possível confirmar a identificação do save.');
const season=String(G.season||'');
const seasonal=mode==='current' ? season==='valentines'||season==='easter' : mode==='seasonal';
const dragonflight=!!G.hasBuff('Dragonflight');
// Seedrandom da referência Steam 2.053 em um Math próprio. Não modifica
// Math.random, o estado do gerador do jogo, mana, contadores ou cookies.
const isolatedMath=Object.create(Math);
isolatedMath.random=()=>0.5;
(function(a,b,c,d,e,f){function k(a){var b,c=a.length,e=this,f=0,g=e.i=e.j=0,h=e.S=[];for(c||(a=[c++]);d>f;)h[f]=f++;for(f=0;d>f;f++)h[f]=h[g=j&g+a[f%c]+(b=h[f])],h[g]=b;(e.g=function(a){for(var b,c=0,f=e.i,g=e.j,h=e.S;a--;)b=h[f=j&f+1],c=c*d+h[j&(h[f]=h[g=j&g+b])+(h[g]=b)];return e.i=f,e.j=g,c})(d)}function l(a,b){var e,c=[],d=(typeof a)[0];if(b&&"o"==d)for(e in a)try{c.push(l(a[e],b-1))}catch(f){}return c.length?c:"s"==d?a:a+"\0"}function m(a,b){for(var d,c=a+"",e=0;c.length>e;)b[j&e]=j&(d^=19*b[j&e])+c.charCodeAt(e++);return o(b)}function n(c){try{return a.crypto.getRandomValues(c=new Uint8Array(d)),o(c)}catch(e){return[+new Date,a,a.navigator.plugins,a.screen,o(b)]}}function o(a){return String.fromCharCode.apply(0,a)}var g=c.pow(d,e),h=c.pow(2,f),i=2*h,j=d-1;c.seedrandom=function(a,f){var j=[],p=m(l(f?[a,o(b)]:0 in arguments?a:n(),3),j),q=new k(j);return m(o(q.S),b),c.random=function(){for(var a=q.g(e),b=g,c=0;h>a;)a=(a+c)*d,b*=d,c=q.g(1);for(;a>=i;)a/=2,b/=2,c>>>=1;return(a+c)/b},p},m(c.random(),b)})(globalThis,[],isolatedMath,256,6,52);
function predict(cast,existing) {
    isolatedMath.seedrandom(seed+'/'+cast);
    const random=isolatedMath.random;
    const chance=failBase+0.15*existing;
    const backfire=!(random()<1-chance);
    // A aparência sazonal consome uma rolagem; a posição consome duas.
    if (seasonal) random();
    random(); random();
    let choices;
    if (!backfire) {
        choices=['frenzy','multiply cookies'];
        if (!dragonflight) choices.push('click frenzy');
        if (random()<0.1) choices.push('cookie storm','cookie storm','blab');
        if (Number(G.BuildingsOwned)>=10 && random()<0.25) choices.push('building special');
        if (random()<0.15) choices=['cookie storm drop'];
        if (random()<0.0001) choices.push('free sugar lump');
    } else {
        choices=['clot','ruin cookies'];
        if (random()<0.1) choices.push('cursed finger','blood frenzy');
        if (random()<0.003) choices.push('free sugar lump');
        if (random()<0.1) choices=['blab'];
    }
    return {effect:choices[Math.floor(random()*choices.length)],backfire,
            failChance:Math.max(0,Math.min(1,chance))};
}
const rows=Array.from({length:count},(_,offset)=>({offset,cast:current+offset,
    outcomes:[0,1,2,3].map(existing=>predict(current+offset,existing))}));
return {ok:true,seed,currentCast:current,season,seasonal,visible,dragonflight,failBase,rows};
})()"""
