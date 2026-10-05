// UI and save are deliberately independent: changing data must update the DOM.
const options=OPTIONS, events=[], nodes={};
function node(id) {
    const classes=new Set();
    return nodes[id]={id,parentNode:null,children:[],style:{},
        classList:{toggle(name,on){if(options.brokenUI)throw Error('DOM unavailable');on?classes.add(name):classes.delete(name);},contains:name=>classes.has(name)},
        appendChild(child){if(child.parentNode)child.parentNode.children=child.parentNode.children.filter(c=>c!==child);this.children.push(child);child.parentNode=this;},
        insertBefore(child){this.appendChild(child);}};
}
globalThis.document={getElementById:id=>options.noDOM?null:nodes[id]||null};
globalThis.Game={Objects:{},Has:()=>false,dragonAura:0,dragonAura2:1,
    dragonLevel:27,dragonAuras:[],specialTab:'dragon',
    ToggleSpecialMenu(){events.push('dragonMenu');},
    RefreshStore(){events.push('store');this.storeToRefresh=0;},
    RebuildUpgrades(){events.push('upgrades');this.upgradesToRebuild=0;}};
const soils={dirt:{id:0,req:0},fertilizer:{id:1,req:50}};
const garden={soils,soil:0,freeze:options.frozen?1:0,nextSoil:options.cooldown?Date.now()+600000:0,
    tools:{freeze:{id:1}},computeStepT(){events.push('step');},
    computeEffs(){events.push('effects');this.toCompute=false;},
    buildPlot(){events.push('plot');this.toRebuild=false;}};
Game.Objects.Farm={minigameLoaded:true,amount:100,minigame:garden,
    sacrifice(n){this.amount-=n;events.push('sacrifice');}};
node('gardenSoil-0').classList.toggle('on',true);node('gardenSoil-1');
node('gardenTool-1');node('gardenContent');node('gardenPlot');
if(options.frozen){nodes['gardenTool-1'].classList.toggle('on',true);nodes.gardenContent.classList.toggle('gardenFrozen',true);}
const temple={slot:[0,1,2],godsById:[{id:0,slot:0},{id:1,slot:1},{id:2,slot:2}],swaps:3,
    slotGod(god,slot){const old=god.slot,other=this.godsById[this.slot[slot]];other.slot=old;this.slot[old]=other.id;this.slot[slot]=god.id;god.slot=slot;events.push('slot');},
    useSwap(n){this.swaps-=n;events.push('swap');}};
Game.Objects.Temple={minigameLoaded:true,minigame:temple};
const roster=node('roster');
for(let i=0;i<3;i++){const slot=node('templeSlot'+i),god=node('templeGod'+i),placeholder=node('templeGodPlaceholder'+i);roster.appendChild(placeholder);slot.appendChild(god);}
if(!options.closedDragon)node('specialPic');
