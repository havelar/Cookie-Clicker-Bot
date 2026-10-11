"""Carinho nativo e previsão dos drops sem alterar o RNG global."""

KRUMBLOR_PET_SCRIPT = r"""(() => {
const G=globalThis.Game;
const now=Date.now(), boundary=new Date(now);
boundary.setMinutes((Math.floor(boundary.getMinutes()/15)+1)*15,0,0);
const untilBoundary=Math.max(1,boundary.getTime()-now);
const base={retryAfterMs:60000,unlocked:false,pet:false};
if (!G || !G.ready || typeof G.Has!=='function' || typeof G.HasUnlocked!=='function')
    return {...base,reason:'unavailable',message:'Aguardando o jogo ficar pronto.'};
if (!G.Has('Pet the dragon'))
    return {...base,reason:'missing_upgrade',message:'Requer o upgrade celestial Pet the dragon.'};
if (G.dragonLevel<8)
    return {...base,reason:'dragon_level',message:'Requer Krumblor no nível 8 ou superior.'};
// Seedrandom nativo da referência Steam 2.053, isolado do Math.random do jogo.
const isolatedMath=Object.create(Math);
isolatedMath.random=()=>0.5;
(function(a,b,c,d,e,f){function k(a){var b,c=a.length,e=this,f=0,g=e.i=e.j=0,h=e.S=[];for(c||(a=[c++]);d>f;)h[f]=f++;for(f=0;d>f;f++)h[f]=h[g=j&g+a[f%c]+(b=h[f])],h[g]=b;(e.g=function(a){for(var b,c=0,f=e.i,g=e.j,h=e.S;a--;)b=h[f=j&f+1],c=c*d+h[j&(h[f]=h[g=j&g+b])+(h[g]=b)];return e.i=f,e.j=g,c})(d)}function l(a,b){var e,c=[],d=(typeof a)[0];if(b&&"o"==d)for(e in a)try{c.push(l(a[e],b-1))}catch(f){}return c.length?c:"s"==d?a:a+"\0"}function m(a,b){for(var d,c=a+"",e=0;c.length>e;)b[j&e]=j&(d^=19*b[j&e])+c.charCodeAt(e++);return o(b)}function n(c){try{return a.crypto.getRandomValues(c=new Uint8Array(d)),o(c)}catch(e){return[+new Date,a,a.navigator.plugins,a.screen,o(b)]}}function o(a){return String.fromCharCode.apply(0,a)}var g=c.pow(d,e),h=c.pow(2,f),i=2*h,j=d-1;c.seedrandom=function(a,f){var j=[],p=m(l(f?[a,o(b)]:0 in arguments?a:n(),3),j),q=new k(j);return m(o(q.S),b),c.random=function(){for(var a=q.g(e),b=g,c=0;h>a;)a=(a+c)*d,b*=d,c=q.g(1);for(;a>=i;)a/=2,b/=2,c>>>=1;return(a+c)/b},p},m(c.random(),b)})(globalThis,[],isolatedMath,256,6,52);
isolatedMath.seedrandom(String(G.seed)+'/dragonTime');
const drops=['Dragon scale','Dragon claw','Dragon fang','Dragon teddy bear'];
let counter=drops.length;
while (counter--) {
    const index=(isolatedMath.random()*counter)|0;
    [drops[counter],drops[index]]=[drops[index],drops[counter]];
}
const slot=Math.floor(new Date(now).getMinutes()/15), drop=drops[slot];
const collected=name=>G.Has(name)||G.HasUnlocked(name);
const owned=drops.filter(collected).length;
const nextWindow=String(boundary.getHours()).padStart(2,'0')+':'+String(boundary.getMinutes()).padStart(2,'0');
const status={...base,drop,collected:owned,slot,nextWindow,windowRemainingMs:untilBoundary,retryAfterMs:untilBoundary};
if (owned===4)
    return {...status,reason:'complete',message:'Os quatro upgrades do Krumblor já estão liberados ou comprados.'};
if (collected(drop))
    return {...status,reason:'waiting_window',message:'Upgrade desta faixa já liberado; aguardando a próxima faixa de 15 minutos.'};
if (G.OnAscend || G.AscendTimer || G.promptOn)
    return {...status,reason:'busy',retryAfterMs:5000,message:'Aguardando fechar a confirmação ou tela de ascensão.'};
if (typeof G.ClickSpecialPic!=='function' || typeof G.ToggleSpecialMenu!=='function'
    || typeof document==='undefined')
    return {...status,reason:'unavailable',retryAfterMs:60000,message:'Interface do Krumblor indisponível.'};
const previousTab=G.specialTab;
const popup=document.getElementById('specialPopup');
const previousOpen=!!previousTab && !!popup && popup.classList.contains('onScreen');
const changed=previousTab!=='dragon'||!previousOpen||!document.getElementById('specialPic');
try {
    if (changed) {
        G.specialTab='dragon';
        G.ToggleSpecialMenu(1);
    }
    if (!document.getElementById('specialPic'))
        return {...status,reason:'unavailable',retryAfterMs:60000,message:'Não foi possível abrir o painel do Krumblor.'};
    G.ClickSpecialPic(); // Somente carinho nativo: não compra ou treina.
    const unlocked=collected(drop);
    return {...status,pet:true,unlocked,collected:drops.filter(collected).length,
        reason:unlocked?'unlocked':'petting',retryAfterMs:unlocked?untilBoundary:Math.min(1000,untilBoundary),
        message:unlocked?'Upgrade liberado; aguardando a próxima faixa.':'Fazendo carinho para liberar o upgrade desta faixa.'};
} finally {
    if (changed) {
        if (previousOpen) {
            G.specialTab=previousTab;
            G.ToggleSpecialMenu(1);
        } else {
            G.ToggleSpecialMenu(0);
            G.specialTab=previousTab;
        }
    }
}
})()"""
