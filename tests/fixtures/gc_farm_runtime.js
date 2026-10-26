// Runtime isolado para conferir compras, trocas e cliques válidos do GC Farm.
const O=OPTIONS, events=[], flags=new Set(O.switchOn?['Golden switch [off]']:[]);
const G=globalThis.Game={ready:true,seed:'teste',goldenClicks:O.count??100,cookies:O.cookies??1000,
    OnAscend:!!O.ascend,AscendTimer:0,ReincarnateTimer:0,elderWrath:O.wrath??0,pledgeT:0,
    season:O.season??'fools',dragonLevel:O.dragonLevel??27,dragonAura:O.primary??9,dragonAura2:O.secondary??18,
    Has:name=>flags.has(name),HasAchiev:()=>!!O.completed,
    shimmerTypes:{golden:{chain:O.chain??0}},shimmers:[],Upgrades:{},Objects:{},
    ToggleSpecialMenu:()=>events.push('desenho')};
const P={slot:O.slots??[4,10,-1],swaps:O.swaps??3,gods:{},godsById:[]};
for (const [key,id] of Object.entries({asceticism:0,seasons:4,industry:7,mother:8,scorn:9,order:10})) {
    const god={id,slot:P.slot.indexOf(id)};P.gods[key]=god;P.godsById[id]=god;
}
// Mesma operação de troca de slots usada pelo minigame do jogo.
P.slotGod=(god,slot)=>{
    if (slot===god.slot) return false;
    if (slot!==-1 && P.slot[slot]!==-1) {
        P.godsById[P.slot[slot]].slot=god.slot;
        P.slot[god.slot]=P.slot[slot];
    } else if (god.slot!==-1) P.slot[god.slot]=-1;
    if (slot!==-1) P.slot[slot]=god.id;
    god.slot=slot;events.push('espírito');
};
P.useSwap=()=>{P.swaps--;events.push('troca');};
G.Objects.Temple={minigame:P,amount:100,sacrifice(n){this.amount-=n;events.push('sacrifício');}};
for (const name of ['Golden switch [on]','Elder Pledge',"Fool's biscuit",'Lucky day','Serendipity',
                    'Golden goose egg','Green yeast digestives','Startrade']) {
    const frequency=['Lucky day','Serendipity','Golden goose egg','Green yeast digestives','Startrade'].includes(name);
    const bought=frequency && O.missingUpgrade!==name;
    if (bought) flags.add(name);
    G.Upgrades[name]={unlocked:O.locked!==name,bought,dname:name,pool:O.prestige===name?'prestige':'',
        isVaulted:()=>O.vaulted===name,getPrice:()=>O.price??10,buy(){
            events.push('compra:'+name);
            if (O.refuse) return 0;
            G.cookies-=this.getPrice();this.bought=1;flags.add(name);
            if (name==='Golden switch [on]') flags.delete('Golden switch [off]');
            if (name==='Elder Pledge') {G.elderWrath=0;G.pledgeT=100;}
            if (name==="Fool's biscuit") G.season='fools';
            return 1;
        }};
}
for (const [i,type] of ['natural','storm','invocado','vermelho'].entries()) {
    G.shimmers.push({id:i,type:'golden',spawnLead:type==='natural'||type==='vermelho',
        force:type==='invocado'?'frenzy':type==='storm'?'cookie storm drop':'',
        pop(){events.push('clique:'+type);if(this.spawnLead) G.goldenClicks++;}});
}
