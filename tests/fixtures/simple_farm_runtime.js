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

// Dual Cast fixture uses actual mana/price formulas and checks restoration order.
if (options.dualRuntime) {
    const tower=Game.Objects['Wizard tower'];
    Object.assign(tower,{amount:options.towers??400,level:options.level??1,
        basePrice:options.basePrice??5,free:0});
    Game.BuildingsOwned=5000;
    Game.priceIncrease=1.001;
    Game.auraMult=()=>options.aura??0;
    Game.modifyBuildingPrice=(_tower,price)=>price*(options.priceMultiplier??1);
    tower.getPrice=function(){return Math.ceil(Game.modifyBuildingPrice(this,this.basePrice*Math.pow(Game.priceIncrease,this.amount)));};
    tower.sell=function(n){
        events.push(['sell',n]);
        const count=options.partialSale?Math.floor(n/2):n;
        for(let i=0;i<count;i++){Game.cookies+=Math.floor(this.getPrice()*.25);this.amount--;Game.BuildingsOwned--;}
    };
    tower.buy=function(n){
        events.push(['rebuy',n]);
        if(Game.buyMode!==1)throw Error('Wrong buy mode');
        if(options.failRebuy)throw Error('Simulated rebuy failure');
        for(let i=0;i<n;i++){const price=this.getPrice();if(Game.cookies<price)break;Game.cookies-=price;this.amount++;Game.BuildingsOwned++;}
    };
    M.computeMagicM=function(){
        const n=Math.max(tower.amount,1),lvl=Math.max(tower.level,1);
        this.magicM=Math.floor(4+Math.pow(n,.6)+Math.log((n+(lvl-1)*10)/15+1)*15);
        this.magic=Math.min(this.magic,this.magicM);
    };
    Object.assign(M.spellsById[1],{costMin:10,costPercent:.6});
    M.computeMagicM();M.magic=options.magic??M.magicM;
    M.getSpellCost=()=>Math.floor((10+.6*M.magicM)*(1-.1*Game.auraMult()));
    const effects=options.effects??['click frenzy','building special'];
    Math.seedrandom=seed=>{
        const index=Number(String(seed).split('/').pop())-10;
        const effect=effects[index]??'click frenzy';
        let rolls;
        if(effect==='blood frenzy') rolls=[.99,0,0,0,.9,.9,.99];
        else rolls=[options.successRoll??0,0,0,.9,effect==='building special'?0:.9,.9,.9,effect==='frenzy'?0:.99];
        if(Game.season==='valentines'||Game.season==='easter')rolls.splice(3,0,0);
        let i=0;Math.random=()=>rolls[i++%rolls.length];
    };
    M.getFailChance=()=>.15+.15*Game.shimmers.length;
    M.castSpell=function(){
        const index=this.spellsCastTotal-10;
        events.push(['cast',index,tower.amount,this.magic,this.getSpellCost()]);
        if(index===1 && options.rejectSecond)return false;
        if(this.magic<this.getSpellCost())return false;
        this.magic-=this.getSpellCost();this.spellsCastTotal++;
        const force=index===1 && options.wrongSecond?'clot':effects[index]??'click frenzy';
        const cookie={id:100+index,type:'golden',force,pop(){
            events.push(['pop',this.force,tower.amount]);
            Game.shimmers=Game.shimmers.filter(s=>s!==this);
            Game.buffs[this.force]={type:{name:this.force},time:30};
        }};
        Game.shimmers.push(cookie);return true;
    };
    if(options.formulaMismatch){M.magicM++;M.magic=M.magicM;}
    if(options.existingShimmer)Game.shimmers.push({id:90,type:'golden'});
}
Game.season=options.season??'';
