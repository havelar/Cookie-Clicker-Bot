// Disposable model of native Garden planting/harvesting, no real save.
const options=OPTIONS, events=[];
globalThis.Game={cookies:options.cookies??1000,OnAscend:false,Objects:{}};
const seeds=[{id:0,key:'bakerWheat',unlocked:true,plantable:true,cost:100,mature:50},
             {id:1,key:'thumbcorn',unlocked:!options.locked,plantable:true,cost:200,mature:50}];
const M={freeze:false,plantsById:seeds,plants:Object.fromEntries(seeds.map(s=>[s.key,s])),
    plot:Array.from({length:6},()=>Array.from({length:6},()=>[0,0])),
    isTileUnlocked:(x,y)=>x>=0&&x<6&&y>=0&&y<6,
    getCost:s=>options.invalidCost?NaN:(options.free?0:s.cost*(options.multiplier??1)),
    canPlant:s=>Game.cookies>=M.getCost(s),
    harvest(x,y){if(!this.plot[y][x][0])return false;events.push(['harvest',x,y]);this.plot[y][x]=options.spawn?[2,0]:[0,0];return true;},
    useTool(id,x,y){
        // Native useTool harvests instead of planting if the tile is occupied.
        if(this.plot[y][x][0])return this.harvest(x,y);
        const s=seeds[id];if(!this.canPlant(s))return false;
        Game.cookies-=this.getCost(s);this.plot[y][x]=[id+1,0];events.push(['plant',s.key,x,y]);return true;
    }};
if(options.occupied!==false)M.plot[0][0]=[options.changed?2:1,10];
Game.Objects.Farm={minigameLoaded:true,minigame:M};
