// Isolated runtime: no browser or real save.
const options=OPTIONS, events=[];
globalThis.Game={cookies:options.cookies??100000, cookiesPs:options.cps??0, lumps:10,
    fps:1, seed:'seed', version:'2.053', season:'', BuildingsOwned:100, buyMode:-1,
    buffs:{}, shimmers:[], Objects:{}, ObjectsById:[], UpgradesInStore:[]};
for (const type of options.buffs||[]) Game.buffs[type]={type:{name:type},time:30};
const M={spellsCastTotal:10,magic:options.magic??100,magicM:100,spellsById:[null,{id:1}],
    getFailChance:()=>.15,getSpellCost:()=>30,
    castSpell(){events.push(['cast']);this.magic-=30;this.spellsCastTotal++;
        const s={id:1,type:'golden',force:'click frenzy',pop(){events.push(['pop']);Game.shimmers=[];}};
        Game.shimmers.push(s);return true;}};
Game.Objects['Wizard tower']={amount:1,level:11,minigameLoaded:true,minigame:M,
    sell(){throw Error('Unexpected sale');},buy(){throw Error('Unexpected tower purchase');}};
Game.Objects.Temple={minigameLoaded:true,minigame:{slot:[8,6,10]}};
Game.Objects.Bank={minigameLoaded:true,minigame:{officeLevel:1}};
if (options.noMinigames) Game.Objects={};
Math.seedrandom=()=>{let i=0;const rolls=[0,0,0,.9,.9,.9,.9,options.badForecast?0:.9];Math.random=()=>rolls[i++%rolls.length];};
for (const raw of options.upgrades||[]) {
    const u={name:'Production cookie',pool:'cookie',power:5,price:1000,...raw,bought:false,
        getPrice(){return this.price;},isVaulted(){return !!this.vaulted;},
        buy(){Game.cookies-=this.price;this.bought=true;events.push(['upgrade',this.name]);return 1;}};
    if (raw.clickFunction) u.clickFunction=()=>{throw Error('Unexpected special upgrade');};
    Game.UpgradesInStore.push(u);
}
for (const raw of options.buildings||[]) {
    const o={id:0,name:'Building',amount:10,price:1000,storedTotalCps:100,unlocked:1,...raw,
        getPrice(){return this.price;},buy(n){if(Game.buyMode!==1)throw Error('Wrong buy mode');
            Game.cookies-=this.price;this.amount+=n;events.push(['building',this.id]);this.price*=1.15;}};
    Game.ObjectsById.push(o);
}
