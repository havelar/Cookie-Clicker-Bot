"""Leituras e ações nativas de Sugar Lumps, sem alterar RNG ou timestamps."""
SUGAR_LUMP_HELPERS = r"""
const lumpNames=['Normal','Bifurcado','Dourado','Carnudo','Caramelizado'];
const lumpStatus=()=>{
    const G=globalThis.Game;
    if (!G || typeof G.canLumps!=='function' || !G.canLumps()
            || G.OnAscend || G.AscendTimer || G.ReincarnateTimer) return null;
    const started=Number(G.lumpT),matureMs=Number(G.lumpMatureAge),ripeMs=Number(G.lumpRipeAge),overripeMs=Number(G.lumpOverripeAge);
    const type=Number(G.lumpCurrentType),now=Date.now(),age=now-started;
    if (![started,matureMs,ripeMs,overripeMs,age,Number(G.lumps)].every(Number.isFinite)
            || started<=0 || matureMs<=0 || ripeMs<matureMs || overripeMs<=ripeMs
            || !Number.isInteger(type) || type<0 || type>4) return null;
    return {type,typeName:lumpNames[type],started,now,age,matureMs,ripeMs,overripeMs,
        mature:age>=matureMs,ready:age>=ripeMs,overripe:age>=overripeMs,
        remainingMatureMs:Math.max(0,matureMs-age),remainingRipeMs:Math.max(0,ripeMs-age),
        remainingAutoMs:Math.max(0,overripeMs-age),lumps:Number(G.lumps)};
};
"""
