"""Sincronização da interface após ações, sem repetir operações no save."""

# As APIs de dados de alguns minigames não executam os passos de DOM dos
# handlers de clique. Não chamamos init/load/logic nem simulamos outro clique:
# isso poderia consumir recursos, avançar um tick ou duplicar uma ação.
GAME_VISUAL_SYNC = r"""
const syncGameVisuals = before => {
    const warnings=[];
    const G=typeof Game==='undefined'?null:Game;
    if (!G) return warnings;
    const element=id=>typeof document==='undefined'?null:document.getElementById(id);
    const run=(area,refresh)=>{
        try { refresh(); }
        catch (error) { warnings.push(area+': '+String(error && error.message || error)); }
    };
    const setClass=(node,name,on)=>{
        if (!node) return;
        node.classList.toggle(name,!!on);
        if (node.classList.contains(name)!==!!on) throw new Error('Destaque visual divergente');
    };
    const minigame=name=>{
        const object=G.Objects && G.Objects[name];
        return object && object.minigameLoaded ? object.minigame : null;
    };
    run('Garden',()=>{
        const M=minigame('Farm');
        if (!M) return;
        for (const soil of Object.values(M.soils||{}))
            setClass(element('gardenSoil-'+soil.id),'on',Number(M.soil)===Number(soil.id));
        const freeze=M.tools && M.tools.freeze;
        if (freeze) setClass(element('gardenTool-'+freeze.id),'on',M.freeze);
        setClass(element('gardenContent'),'gardenFrozen',M.freeze);
        if (element('gardenPlot') && M.toRebuild && typeof M.buildPlot==='function') M.buildPlot();
        if (M.toCompute && typeof M.computeEffs==='function') M.computeEffs();
    });
    run('Pantheon',()=>{
        const M=minigame('Temple');
        if (!M || M.dragging) return;
        // slotGod altera os slots, mas quem move os elementos é dropGod.
        for (const god of M.godsById||[]) {
            if (!god) continue;
            const node=element('templeGod'+god.id);
            const placeholder=element('templeGodPlaceholder'+god.id);
            if (!node || !placeholder) continue;
            const slot=Number(god.slot);
            const parent=slot>=0?element('templeSlot'+slot):placeholder.parentNode;
            if (!parent) continue;
            if (node.parentNode!==parent) {
                if (slot>=0) parent.appendChild(node);
                else parent.insertBefore(node,placeholder);
            }
            placeholder.style.display='none';
            if (node.parentNode!==parent) throw new Error('Espírito não aparece no slot aplicado');
        }
    });
    run('Dragon',()=>{
        if (before && (before[0]!==G.dragonAura || before[1]!==G.dragonAura2)
                && G.specialTab==='dragon' && element('specialPic')
                && typeof G.ToggleSpecialMenu==='function') G.ToggleSpecialMenu(1);
    });
    // Compras, vendas, sacrifícios e upgrades usam as APIs nativas; seus
    // indicadores de atualização precisam ser processados após restaurar buyMode.
    run('Loja',()=>{
        if (G.OnAscend || Number(G.AscendTimer)>0 || Number(G.ReincarnateTimer)>0) return;
        if (G.storeToRefresh && typeof G.RefreshStore==='function') G.RefreshStore();
        if (G.upgradesToRebuild && typeof G.RebuildUpgrades==='function') G.RebuildUpgrades();
    });
    // Banco e Grimoire já desenham escritório, estoques, empréstimos e mana
    // a partir dos dados em cada frame. Não avançamos a lógica para desenhá-los.
    return warnings;
};
"""
