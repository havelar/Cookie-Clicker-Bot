// Oráculo com as funções da referência local; nenhum acesso ao jogo real.
const fs=require('fs'), input=JSON.parse(fs.readFileSync(0,'utf8'));
const main=fs.readFileSync('reference/cookie-clicker/src/main.js','utf8');
const grimoire=fs.readFileSync('reference/cookie-clicker/src/minigameGrimoire.js','utf8');
const seedLine=main.split('\n').find(line=>line.includes('c.seedrandom=function')).trim().replace(')(this,[],Math',')(globalThis,[],Math');
globalThis.navigator={plugins:[]};
eval(seedLine);
globalThis.loc=value=>value;
globalThis.EN=true;
globalThis.choose=values=>values[Math.floor(Math.random()*values.length)];
const M={spellsCastTotal:input.cast??120,magic:100,magicM:100};
globalThis.Game={ready:true,seed:input.seed??'teste-planner',season:input.season??'',
 OnAscend:!!input.ascending,Objects:{'Wizard tower':{minigameLoaded:!input.unavailable,minigame:M}},
 shimmerTypes:{golden:{n:input.visible??0}},BuildingsOwned:input.buildings??100,
 bounds:{left:0,right:1000,top:0,bottom:700},resPath:'',fps:30,
 hasBuff:name=>(input.buffs||[]).includes(name),auraMult:()=>input.aura??0,
 Has:()=>false,eff:()=>1,Popup:()=>{}};
eval(grimoire.slice(grimoire.indexOf('M.spells={'),grimoire.indexOf('M.spellsById=[]')));
const failStart=grimoire.indexOf('M.getFailChance=')+'M.getFailChance='.length;
M.getFailChance=eval('('+grimoire.slice(failStart,grimoire.indexOf('M.castSpell=',failStart)).trim().replace(/;$/,'')+')');
const initStart=main.indexOf('initFunc:function(me)');
const initEnd=main.indexOf('updateFunc:function(me)',initStart);
const init=eval('('+main.slice(initStart+'initFunc:'.length,initEnd).trim().replace(/,$/,'')+')');
let created;
Game.shimmer=function(type,forceObj){
 this.force='';this.forceObj=forceObj;this.l={style:{},setAttribute:()=>{}};
 Game.shimmerTypes.golden.n++;
 init.call({spawned:true,chain:0},this);
 created=this;
};
const before=JSON.stringify(Game);
let randomCalls=0;
const preserved=()=>{randomCalls++;return 0.42;};
Math.random=preserved;
const nativeSeedrandom=Math.seedrandom;
let seedCalls=0;
Math.seedrandom=()=>{seedCalls++;throw Error('O Planner não pode reseedar o jogo');};
const result=eval(input.script);
const unchanged=before===JSON.stringify(Game) && Math.random===preserved && randomCalls===0 && seedCalls===0;
Math.seedrandom=nativeSeedrandom;
let checked=0, mismatches=[];
if(result.ok){
 const spell=M.spells['hand of fate'];
 const contextSeason=Game.season;
 Game.season=input.mode==='seasonal'?'easter':input.mode==='normal'?'christmas':contextSeason;
 for(const row of result.rows){
  for(let existing=0;existing<4;existing++){
   Game.shimmerTypes.golden.n=existing;
   Math.seedrandom(Game.seed+'/'+row.cast);
   const backfire=!(Math.random()<1-M.getFailChance(spell));
   if(backfire)spell.fail();else spell.win();
   const actual=row.outcomes[existing];
   if(actual.effect!==created.force || actual.backfire!==backfire)
    mismatches.push({cast:row.cast,existing,actual,expected:{effect:created.force,backfire}});
   checked++;
  }
 }
}
console.log(JSON.stringify({result,unchanged,checked,mismatches}));
