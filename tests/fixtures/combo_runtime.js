// Modelo isolado da engine: sem navegador, save, rede ou operações no jogo real.
const events=[];
const options=OPTIONS;
const results=['blood frenzy','click frenzy','frenzy','building special'];
const rolls=[
    [.99,0,0,0,.01,.9,.9,.99],
    [0,0,0,0,.9,.9,.9,.9,.99],
    [0,0,0,0,.9,.9,.9,.9,0],
    [0,0,0,0,.9,.1,.9,.9,.99],
];
Math.seedrandom=seed=>{let i=0;const values=rolls[Number(seed.split('/')[1])-10];Math.random=()=>values[i++];};
const buff=(type,time,id)=>({type:{name:type},time,arg2:id});
const Game={fps:1,seed:'seed',season:'valentines',lumps:10,priceIncrease:1.15,
    cookies:1e100,BuildingsOwned:10000,dragonAura:4,dragonAura2:13,buyMode:1,
    prefs:{askLumps:1},shimmers:[],buffs:{harvest:buff('dragon harvest',30),natural:buff('building buff',options.naturalTime||30,6)},
    Upgrades:{},UpgradesInStore:[],canRefillLump:()=>true,getLumpRefillMax:()=>900,
    hasBuff:name=>Game.buffs[name]||false,modifyBuildingPrice:(tower,p)=>p};
if (!options.noFrenzy) Game.buffs.frenzy=buff('frenzy',30);
if (options.negative) Game.buffs.negative=buff(options.negative,30);
const addDevastation=()=>{if(!Game.buffs.devastation) Game.buffs.devastation=buff('devastation',options.devastationTime||10);};
Game.ObjectsById=Array.from({length:20},(_,id)=>({id,amount:id===7?601:800,level:10,basePrice:1,free:0,
    sell(n){this.amount-=n;events.push(['sell',id,n]);addDevastation();},
    buy(n){this.amount+=n;events.push(['buy',id,n]);},sacrifice(n){this.amount-=n;}}));
Game.Objects=Object.fromEntries(Game.ObjectsById.map((o,i)=>[i,o]));
const M={spellsCastTotal:10,magic:108,magicM:108,spellsById:[null,{}],getFailChance:()=>.15,
    getSpellCost:()=>1,computeMagicM(){this.magicM=Game.ObjectsById[7].amount===1?30:108;},
    castSpell(){
        let index=this.spellsCastTotal++-10;
        events.push(['cast',index]);
        this.magic--;
        const s={id:index,type:'golden',force:results[index],life:100,
            pop(){
                events.push(['pop',this.force]);
                const type=this.force==='building special'?'building buff':this.force;
                const key=type==='building buff'?(options.duplicate?'natural':'spellBS'):type;
                Game.buffs[key]=buff(type,type==='blood frenzy'?14:type==='click frenzy'?30:72,
                    type==='building buff'?(options.duplicate?6:9):undefined);
                Game.shimmers=Game.shimmers.filter(x=>x!==this);
            }};
        Game.shimmers.push(s);return true;
    }};
Game.Objects['Wizard tower']=Object.assign(Game.ObjectsById[7],{minigameLoaded:true,minigame:M});
Game.Objects.Temple=Object.assign(Game.ObjectsById[6],{minigameLoaded:true,minigame:{slot:[2,8,6]}});
Game.Objects.Bank=Object.assign(Game.ObjectsById[5],{minigameLoaded:true,minigame:{officeLevel:5,takeLoan(id){events.push(['loan',id]);Game.buffs['Loan '+id]=buff('loan '+id,40);return true;}}});
// Reproduz a versão 2.053: buy(1) ignora o click handler; a compra normal
// retorna 0 mesmo quando o callback compra o upgrade e ativa o buff.
Game.Upgrades['Sugar frenzy']={bought:false,buy(bypass){
    if(bypass){this.bought=true;return 1;}
    events.push(['sugar']);
    if(Game.prefs.askLumps) throw Error('Unexpected confirmation dialog');
    Game.lumps--;this.buy(1);
    if(!options.sugarMissingBuff) Game.buffs['Sugar frenzy']=buff('sugar frenzy',3600);
    return 0;
}};
if(options.loanInterest) Game.buffs['Loan 2 (interest)']=buff('loan 2 interest',1000);
