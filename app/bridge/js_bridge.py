"""
Bridge para comunicação com o runtime JavaScript do Cookie Clicker.
"""
import json
import time
import threading
from typing import Optional, Any, Dict, List

try:
    import pychrome
except ImportError:
    raise ImportError("pychrome não encontrado. Instale com 'pip install pychrome'")

from app.config.settings import app_config
from app.models.garden import (
    GardenAction,
    GardenActionResult,
    GardenPlant,
    GardenSeed,
    GardenSnapshot,
    GardenSoil,
    GardenStatus,
)
from app.models.stock_market import (
    StockAsset,
    StockMarketSnapshot,
    StockMarketStatus,
    StockTradeResult,
)
from app.models.auto_ascensao import (
    Construcao,
    HeavenlyUpgrade,
    ResultadoAcaoAscensao,
    SnapshotAscensao,
    UpgradeNormal,
)
from app.utils.logger import logger

MAX_STOCK_ASSET_ID = 10_000
MAX_STOCK_TRADE_QUANTITY = 1_000_000_000
GAME_MAXIMUM_ORDER_SENTINEL = 10_000
DEFAULT_GRIMOIRE_SPELLS = (
    (0, "Conjure Baked Goods"),
    (1, "Force the Hand of Fate"),
    (2, "Stretch Time"),
    (3, "Spontaneous Edifice"),
    (4, "Haggler's Charm"),
    (5, "Summon Crafty Pixies"),
    (6, "Gambler's Fever Dream"),
    (7, "Resurrect Abomination"),
    (8, "Diminish Ineptitude"),
)


class CookieClickerBridge:
    """
    Bridge para comunicação com o runtime JavaScript do Cookie Clicker via Chrome DevTools Protocol.
    Conecta ao CEF do jogo Steam usando remote debugging.
    """

    def __init__(self,
                 host: Optional[str] = None,
                 port: Optional[int] = None,
                 timeout: Optional[int] = None):
        """
        Inicializa a bridge.

        Args:
            host: Host do remote debugging (usa config se None)
            port: Porta do remote debugging (usa config se None)
            timeout: Timeout para conexões em segundos (usa config se None)
        """
        self.host = host or app_config.remote_debugging_host
        self.port = port or app_config.remote_debugging_port
        self.timeout = timeout or app_config.connection_timeout
        self.browser: Optional[pychrome.Browser] = None
        self.tab: Optional[pychrome.Tab] = None
        self.connected = False
        # pychrome não garante acesso concorrente seguro ao mesmo websocket.
        self._runtime_lock = threading.RLock()

    def connect(self) -> bool:
        """
        Conecta ao remote debugging do CEF.

        Returns:
            True se conectado com sucesso, False caso contrário
        """
        with self._runtime_lock:
            try:
                self.browser = pychrome.Browser(url=f"http://{self.host}:{self.port}")
                tabs = self.browser.list_tab()
                if not tabs:
                    logger.error("Nenhuma aba encontrada no remote debugging")
                    return False

                # Assume a primeira aba é o jogo
                self.tab = tabs[0]
                # Evita despejar cada pacote CDP no console quando a variável
                # de ambiente DEBUG estiver definida no processo.
                self.tab.debug = False
                self.tab.start()
                self.connected = True
                logger.info("Conectado ao CEF do Cookie Clicker via CDP")
                return True
            except Exception as e:
                logger.error(f"Erro ao conectar ao remote debugging: {e}")
                self.connected = False
                return False

    def disconnect(self):
        """Desconecta do remote debugging."""
        with self._runtime_lock:
            if self.tab:
                try:
                    self.tab.stop()
                except Exception as e:
                    logger.warning(f"Erro ao parar aba: {e}")
            self.browser = None
            self.tab = None
            self.connected = False
            logger.info("Desconectado do remote debugging")

    def execute_js(self, code: str) -> Optional[Any]:
        """
        Executa código JavaScript no contexto do jogo e retorna o resultado.

        Args:
            code: Código JavaScript a executar

        Returns:
            Resultado da execução ou None se erro
        """
        with self._runtime_lock:
            if not self.connected or not self.tab:
                logger.warning("Bridge não conectado. Tentando reconectar...")
                if not self.connect():
                    return None

            try:
                result = self.tab.Runtime.evaluate(expression=code, returnByValue=True)
                if 'result' in result and 'value' in result['result']:
                    return result['result']['value']
                elif result.get('result', {}).get('type') == 'undefined':
                    # Algumas APIs do jogo executam a ação, mas não retornam valor.
                    # Isso não é uma falha de CDP e não deve poluir o log.
                    return None
                elif 'exceptionDetails' in result:
                    logger.error(f"Erro JS: {result['exceptionDetails']}")
                    return None
                else:
                    logger.error(f"Resposta inesperada do CDP: {result!r}")
                    return None
            except Exception as e:
                logger.error(f"Erro ao executar JS: {e}")
                self.connected = False  # Marcar como desconectado para tentar reconectar
                return None

    # === Helpers específicos do Cookie Clicker ===

    def get_ascension_snapshot(self) -> SnapshotAscensao:
        """Obtém em uma avaliação o estado necessário para a Auto Ascensão."""
        payload = self.execute_js("""(() => {
            const unavailable = message => ({available:false, screen:'indisponivel', message});
            if (!globalThis.Game) return unavailable('Runtime do jogo indisponível');

            const finite = (value, fallback=0) => {
                const number = Number(value);
                return Number.isFinite(number) ? number : fallback;
            };
            const onAscend = !!Game.OnAscend;
            const ascendTimer = finite(Game.AscendTimer);
            const reincarnateTimer = finite(Game.ReincarnateTimer);
            const screen = onAscend ? 'ascensao'
                : (ascendTimer > 0 || reincarnateTimer > 0 ? 'transicao' : 'jogo');
            const cookies = Math.max(0, finite(Game.cookies));
            const prestige = Math.max(0, finite(Game.prestige));
            let totalPrestige = prestige;
            if (typeof Game.HowMuchPrestige === 'function') {
                try {
                    totalPrestige = finite(Game.HowMuchPrestige(
                        finite(Game.cookiesReset) + finite(Game.cookiesEarned)
                    ), prestige);
                } catch (_) { totalPrestige = prestige; }
            }

            const heavenly = Object.values(Game.UpgradesById || {})
                .filter(upgrade => upgrade && upgrade.pool === 'prestige' && !upgrade.bought)
                .map(upgrade => {
                    let price = Infinity;
                    try { price = finite(upgrade.getPrice(), Infinity); } catch (_) {}
                    const parents = Array.isArray(upgrade.parents) ? upgrade.parents : [];
                    const parentsBought = parents.every(parent => parent && parent.bought);
                    const simple = !upgrade.clickFunction && !upgrade.choicesFunction;
                    const affordable = price <= finite(Game.heavenlyChips);
                    const eligible = onAscend && parentsBought && simple && affordable;
                    let reason = '';
                    if (!onAscend) reason = 'fora da tela de ascensão';
                    else if (!parentsBought) reason = 'pré-requisito celestial ausente';
                    else if (!simple) reason = 'upgrade exige interação especial';
                    else if (!affordable) reason = 'Heavenly Chips insuficientes';
                    return {id:Number(upgrade.id), name:String(upgrade.name || upgrade.id),
                        price:Number.isFinite(price) ? price : 0, eligible, reason};
                });

            const store = Array.from(Game.UpgradesInStore || []);
            const buyAllAvailable = typeof Game.storeBuyAll === 'function'
                && typeof Game.Has === 'function' && !!Game.Has('Inspired checklist');
            const normal = store.filter(upgrade => upgrade && !upgrade.bought).map(upgrade => {
                let price = Infinity, canBuy = false, vaulted = true;
                try { price = finite(upgrade.getPrice(), Infinity); } catch (_) {}
                try { canBuy = typeof upgrade.canBuy === 'function' && !!upgrade.canBuy(); } catch (_) {}
                try { vaulted = typeof upgrade.isVaulted === 'function' ? !!upgrade.isVaulted() : true; }
                catch (_) { vaulted = true; }
                const acceptedByBuyAll = !vaulted && upgrade.pool !== 'toggle' && upgrade.pool !== 'tech';
                const eligible = buyAllAvailable && !onAscend && screen === 'jogo' && acceptedByBuyAll
                    && canBuy && price <= cookies;
                let reason = '';
                if (onAscend || screen !== 'jogo') reason = 'fora do jogo normal';
                else if (!buyAllAvailable) reason = 'botão Comprar todos indisponível';
                else if (!acceptedByBuyAll) reason = 'upgrade ignorado pelo botão Comprar todos';
                else if (!canBuy || price > cookies) reason = 'cookies insuficientes';
                return {id:Number(upgrade.id), name:String(upgrade.name || upgrade.id),
                    price:Number.isFinite(price) ? price : 0, eligible, reason};
            });

            const buildings = Object.values(Game.ObjectsById || {}).filter(Boolean).map(object => {
                const unlocked = object.unlocked !== 0;
                let unitPrice = Infinity, maximum = 0;
                try { unitPrice = finite(object.getPrice(), Infinity); } catch (_) {}
                if (unlocked && Number(Game.buyMode) !== -1 && unitPrice <= cookies) {
                    if (typeof object.getSumPrice === 'function') {
                        const affordable = quantity => {
                            try { return finite(object.getSumPrice(quantity), Infinity) <= cookies; }
                            catch (_) { return false; }
                        };
                        let low = 1, high = 1;
                        while (high < 1000 && affordable(high)) {
                            low = high;
                            high = Math.min(1000, high * 2);
                            if (high === low) break;
                        }
                        if (high === 1000 && affordable(high)) maximum = 1000;
                        else {
                            let left = low, right = high - 1;
                            while (left <= right) {
                                const middle = Math.floor((left + right) / 2);
                                if (affordable(middle)) { maximum = middle; left = middle + 1; }
                                else right = middle - 1;
                            }
                        }
                    } else maximum = 1;
                }
                return {id:Number(object.id), name:String(object.name || object.id),
                    amount:Math.max(0, Math.trunc(finite(object.amount))),
                    unitPrice:Number.isFinite(unitPrice) ? unitPrice : 0,
                    maximum:Math.max(0, Math.trunc(maximum)), unlocked};
            });

            return {
                available:true, screen, message:screen === 'ascensao'
                    ? 'Tela de ascensão disponível'
                    : (screen === 'transicao' ? 'Transição do jogo em andamento' : 'Jogo normal disponível'),
                version:Game.version === undefined ? null : String(Game.version),
                cookies, cookiesPerSecond:Math.max(0, finite(Game.cookiesPs)),
                prestige, prestigeGain:Math.max(0, totalPrestige - prestige),
                heavenlyChips:Math.max(0, finite(Game.heavenlyChips)),
                ascendTimer, reincarnateTimer, buyAllAvailable, heavenly, normal, buildings
            };
        })()""")
        return self._parse_ascension_snapshot(payload)

    def buy_heavenly_upgrade(self, upgrade_id: int) -> ResultadoAcaoAscensao:
        """Compra um Heavenly Upgrade simples, elegível e confirma a mudança."""
        if isinstance(upgrade_id, bool) or not isinstance(upgrade_id, int) or upgrade_id < 0:
            return self._invalid_ascension_action("comprar_heavenly", "Identificador inválido")
        payload = self.execute_js("""(() => {
            const id=%d, fail=(reason,message,extra={}) =>
                Object.assign({ok:false,reason,message,id},extra);
            if (!globalThis.Game || !Game.OnAscend)
                return fail('wrong_screen','A compra celestial exige a tela de ascensão');
            const upgrade=Game.UpgradesById && Game.UpgradesById[id];
            if (!upgrade || upgrade.pool!=='prestige')
                return fail('missing_upgrade','Heavenly Upgrade não encontrado');
            if (upgrade.bought) return fail('already_bought','Heavenly Upgrade já comprado');
            if (upgrade.clickFunction || upgrade.choicesFunction)
                return fail('special_interaction','Upgrade exige interação especial');
            const parents=Array.isArray(upgrade.parents)?upgrade.parents:[];
            if (!parents.every(parent=>parent && parent.bought))
                return fail('missing_parent','Pré-requisito celestial ainda não comprado');
            const price=Number(upgrade.getPrice());
            const before=Number(Game.heavenlyChips);
            if (!Number.isFinite(price) || !Number.isFinite(before) || before<price)
                return fail('insufficient_chips','Heavenly Chips insuficientes',{before});
            let accepted=0;
            try { accepted=upgrade.buy(); }
            catch(error) { return fail('operation_error',`Falha ao comprar: ${error && error.message ? error.message : error}`,{before}); }
            const after=Number(Game.heavenlyChips);
            const ok=accepted===1 && !!upgrade.bought && Number.isFinite(after) && after<=before;
            return {ok,reason:ok?'verified':'ambiguous_result',
                message:ok?'Heavenly Upgrade comprado e verificado':'O jogo não confirmou a compra celestial',
                id,quantity:ok?1:0,before,after};
        })()""" % upgrade_id)
        result = self._parse_ascension_action(payload, "comprar_heavenly", upgrade_id)
        self._log_ascension_action(result)
        return result

    def reincarnate(self) -> ResultadoAcaoAscensao:
        """Reencarna somente a partir da tela de ascensão e verifica a saída dela."""
        payload = self.execute_js("""(() => {
            const fail=(reason,message)=>({ok:false,reason,message});
            if (!globalThis.Game || typeof Game.Reincarnate!=='function')
                return fail('unavailable','API de reencarnação indisponível');
            if (!Game.OnAscend) return fail('wrong_screen','O jogo não está na tela de ascensão');
            if (Number(Game.AscendTimer)>0 || Number(Game.ReincarnateTimer)>0)
                return fail('transition','Já existe uma transição em andamento');
            const before=Number(Game.resets||0);
            try { Game.Reincarnate(1); }
            catch(error) { return fail('operation_error',`Falha ao reencarnar: ${error && error.message ? error.message : error}`); }
            const after=Number(Game.resets||0);
            const ok=!Game.OnAscend || Number(Game.ReincarnateTimer)>0;
            return {ok,reason:ok?'verified':'ambiguous_result',
                message:ok?'Reencarnação iniciada e verificada':'O jogo não confirmou a reencarnação',
                before,after};
        })()""")
        result = self._parse_ascension_action(payload, "reencarnar")
        self._log_ascension_action(result)
        return result

    def buy_all_normal_upgrades(self) -> ResultadoAcaoAscensao:
        """Aciona uma vez o botão nativo de comprar todos e verifica as compras."""
        payload = self.execute_js("""(() => {
            const fail=(reason,message,extra={}) =>
                Object.assign({ok:false,reason,message,quantity:0},extra);
            if (!globalThis.Game || Game.OnAscend || Number(Game.AscendTimer)>0
                    || Number(Game.ReincarnateTimer)>0)
                return fail('wrong_screen','A compra exige o jogo normal e sem transição');
            if (typeof Game.storeBuyAll!=='function' || typeof Game.Has!=='function'
                    || !Game.Has('Inspired checklist'))
                return fail('unavailable','O botão Comprar todos os upgrades está indisponível');
            const allowed=upgrade => {
                if (!upgrade || upgrade.bought || typeof upgrade.isVaulted!=='function') return false;
                let vaulted=true;
                try { vaulted=!!upgrade.isVaulted(); } catch(_) { return false; }
                return !vaulted && upgrade.pool!=='toggle' && upgrade.pool!=='tech';
            };
            const beforeStore=Array.from(Game.UpgradesInStore||[]).filter(allowed);
            const beforeOwned=Number(Game.UpgradesOwned||0);
            const cookiesBefore=Number(Game.cookies||0);
            if (!beforeStore.some(upgrade => {
                try { return typeof upgrade.canBuy==='function' && upgrade.canBuy(); }
                catch(_) { return false; }
            })) return fail('nothing_affordable','Nenhum upgrade do botão está acessível agora',
                {before:beforeOwned,after:beforeOwned});
            try { Game.storeBuyAll(); }
            catch(error) {
                return fail('operation_error',`Falha ao comprar todos: ${error && error.message ? error.message : error}`,
                    {before:beforeOwned,after:Number(Game.UpgradesOwned||0)});
            }
            const boughtIds=beforeStore.filter(upgrade=>!!upgrade.bought).map(upgrade=>Number(upgrade.id));
            const afterOwned=Number(Game.UpgradesOwned||0);
            const cookiesAfter=Number(Game.cookies||0);
            const ok=boughtIds.length>0 && Number.isFinite(cookiesAfter) && cookiesAfter<=cookiesBefore;
            return {ok,reason:ok?'verified':'ambiguous_result',
                message:ok
                    ? `${boughtIds.length} upgrade(s) comprado(s) e verificado(s) pelo botão nativo`
                    : 'O jogo não confirmou nenhuma compra pelo botão Comprar todos',
                quantity:boughtIds.length,before:beforeOwned,after:afterOwned,boughtIds};
        })()""")
        result = self._parse_ascension_action(payload, "comprar_todos_upgrades")
        self._log_ascension_action(result)
        return result

    def buy_buildings_batch(
        self, building_ids: List[int], quantity_limit: int = 100,
    ) -> ResultadoAcaoAscensao:
        """Compra até um lote de cada construção, priorizando os maiores IDs."""
        if (
            not isinstance(building_ids, list) or not building_ids
            or any(isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 10_000
                   for item in building_ids)
            or isinstance(quantity_limit, bool) or not isinstance(quantity_limit, int)
            or not 1 <= quantity_limit <= 1000
        ):
            return self._invalid_ascension_action(
                "comprar_lote_construcoes", "Parâmetros do lote de construções inválidos"
            )
        ordered_ids = sorted(set(building_ids), reverse=True)
        payload = self.execute_js("""(() => {
            const ids=%s, limit=%d, fail=(reason,message,extra={}) =>
                Object.assign({ok:false,reason,message,quantity:0},extra);
            if (!globalThis.Game || Game.OnAscend || Number(Game.AscendTimer)>0 || Number(Game.ReincarnateTimer)>0)
                return fail('wrong_screen','A compra exige o jogo normal e sem transição');
            if (Number(Game.buyMode)===-1)
                return fail('sell_mode','O jogo está no modo de venda; compra bloqueada');
            const objects=ids.map(id=>Game.ObjectsById && Game.ObjectsById[id]);
            if (objects.some(object=>!object || object.unlocked===0 || typeof object.buy!=='function'
                    || typeof object.getPrice!=='function'))
                return fail('missing_building','Uma construção planejada ficou indisponível');
            const before=objects.reduce((sum,object)=>sum+Number(object.amount||0),0);
            let total=0, changed=0;
            const purchases=[];
            for (const object of objects) {
                const amountBefore=Number(object.amount), cookies=Number(Game.cookies);
                let price=Infinity;
                try { price=Number(object.getPrice()); } catch(_) {}
                if (!Number.isFinite(price) || !Number.isFinite(cookies) || price>cookies) continue;
                try { object.buy(limit); }
                catch(error) {
                    return fail('operation_error',
                        `Falha no lote após ${changed} construção(ões): ${error && error.message ? error.message : error}`,
                        {quantity:total,before,after:objects.reduce((sum,item)=>sum+Number(item.amount||0),0)});
                }
                const amountAfter=Number(object.amount), executed=amountAfter-amountBefore;
                if (!Number.isFinite(executed) || executed<0 || executed>limit)
                    return fail('ambiguous_result','O jogo retornou uma quantidade inesperada no lote',
                        {quantity:total,before,after:objects.reduce((sum,item)=>sum+Number(item.amount||0),0)});
                if (executed>0) {
                    total+=Math.trunc(executed);
                    changed++;
                    purchases.push({id:Number(object.id),quantity:Math.trunc(executed)});
                }
            }
            const after=objects.reduce((sum,object)=>sum+Number(object.amount||0),0);
            const ok=total>0 && after-before===total;
            return {ok,reason:ok?'verified':'ambiguous_result',
                message:ok
                    ? `${total} unidade(s) comprada(s) em ${changed} construção(ões), das melhores para as básicas`
                    : 'O jogo não confirmou compras no lote de construções',
                quantity:total,before,after,purchases};
        })()""" % (json.dumps(ordered_ids), quantity_limit))
        result = self._parse_ascension_action(payload, "comprar_lote_construcoes")
        self._log_ascension_action(result)
        return result

    def start_ascension(self, minimum_prestige_gain: float) -> ResultadoAcaoAscensao:
        """Inicia ascensão apenas após revalidar atomicamente o ganho mínimo."""
        minimum = self._optional_float(minimum_prestige_gain)
        if minimum is None or minimum < 0:
            return self._invalid_ascension_action("ascender", "Ganho mínimo de prestígio inválido")
        payload = self.execute_js("""(() => {
            const minimum=%s, fail=(reason,message,extra={}) =>
                Object.assign({ok:false,reason,message},extra);
            if (!globalThis.Game || typeof Game.Ascend!=='function' || typeof Game.HowMuchPrestige!=='function')
                return fail('unavailable','API de ascensão indisponível');
            if (Game.OnAscend || Number(Game.AscendTimer)>0 || Number(Game.ReincarnateTimer)>0)
                return fail('wrong_screen','O jogo não está pronto para ascender');
            const current=Number(Game.prestige||0);
            const total=Number(Game.HowMuchPrestige(Number(Game.cookiesReset||0)+Number(Game.cookiesEarned||0)));
            const gain=Math.max(0,total-current);
            if (!Number.isFinite(gain) || gain<minimum)
                return fail('insufficient_prestige','Ganho mínimo de prestígio ainda não atingido',{before:gain});
            try { Game.Ascend(1); }
            catch(error) { return fail('operation_error',`Falha ao iniciar ascensão: ${error && error.message ? error.message : error}`,{before:gain}); }
            const ok=!!Game.OnAscend || Number(Game.AscendTimer)>0;
            return {ok,reason:ok?'verified':'ambiguous_result',
                message:ok?'Ascensão iniciada e verificada':'O jogo não confirmou o início da ascensão',
                before:gain,after:gain};
        })()""" % json.dumps(minimum))
        result = self._parse_ascension_action(payload, "ascender")
        self._log_ascension_action(result)
        return result

    def get_grimoire_spells(self) -> List[Dict[str, Any]]:
        """Lista as magias disponíveis no Grimoire carregado."""
        payload = self.execute_js("""(() => {
            const tower = globalThis.Game && Game.Objects
                ? Game.Objects['Wizard tower'] : null;
            const M = tower && tower.minigameLoaded ? tower.minigame : null;
            if (!M || !Array.isArray(M.spellsById)) return [];
            return M.spellsById.map(spell => ({
                id: Number(spell.id),
                name: String(spell.name || `Skill ${spell.id}`),
                description: String(spell.desc || '')
            }));
        })()""")
        if not isinstance(payload, list):
            return []
        spells = []
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            spell_id = self._optional_int(raw.get("id"))
            if spell_id is None or spell_id < 0:
                continue
            spells.append({
                "id": spell_id,
                "name": str(raw.get("name") or f"Skill {spell_id}"),
                "description": str(raw.get("description") or ""),
            })
        return spells

    def cast_grimoire_spell_when_full(self, spell_id: int) -> Dict[str, Any]:
        """Lança uma magia somente se a mana continuar cheia no runtime."""
        if isinstance(spell_id, bool) or not isinstance(spell_id, int) or spell_id < 0:
            return {"cast": False, "reason": "invalid_spell", "message": "Skill inválida"}
        payload = self.execute_js("""(() => {
            const spellId = %d;
            const fail = (reason, message, extra = {}) =>
                Object.assign({cast:false, reason, message}, extra);
            const tower = globalThis.Game && Game.Objects
                ? Game.Objects['Wizard tower'] : null;
            const M = tower && tower.minigameLoaded ? tower.minigame : null;
            if (!M || !Array.isArray(M.spellsById) || typeof M.castSpell !== 'function'
                    || typeof M.getSpellCost !== 'function') {
                return fail('unavailable', 'Grimoire indisponível');
            }
            const magic = Number(M.magic), maximum = Number(M.magicM);
            if (!Number.isFinite(magic) || !Number.isFinite(maximum) || maximum <= 0) {
                return fail('invalid_mana', 'Estado de mana inválido');
            }
            if (magic + 1e-7 < maximum) {
                return fail('waiting_mana', 'Aguardando mana máxima', {magic, maximum});
            }
            const spell = M.spellsById.find(item => Number(item && item.id) === spellId);
            if (!spell) return fail('missing_spell', 'Skill não encontrada', {magic, maximum});
            const cost = Number(M.getSpellCost(spell));
            if (!Number.isFinite(cost) || cost > magic) {
                return fail('insufficient_mana', 'Mana máxima ainda não cobre o custo da skill',
                    {magic, maximum, cost, spellName:String(spell.name || spellId)});
            }
            let accepted = false;
            try { accepted = M.castSpell(spell) === true; }
            catch (error) {
                return fail('cast_error', `Falha ao usar skill: ${error && error.message ? error.message : error}`,
                    {magic, maximum, cost, spellName:String(spell.name || spellId)});
            }
            const magicAfter = Number(M.magic);
            return accepted
                ? {cast:true, reason:'cast', message:'Skill usada', magic, maximum, magicAfter,
                    cost, spellName:String(spell.name || spellId)}
                : fail('cast_rejected', 'O jogo recusou a skill',
                    {magic, maximum, magicAfter, cost, spellName:String(spell.name || spellId)});
        })()""" % spell_id)
        if not isinstance(payload, dict):
            return {"cast": False, "reason": "invalid_response", "message": "Resposta inválida do Grimoire"}
        return payload

    # === Modo Combo ===

    def get_game_save(self) -> Optional[str]:
        """Retorna o save exportável sem abrir o prompt do jogo."""
        payload = self.execute_js("""(() => {
            if (!globalThis.Game || typeof Game.WriteSave !== 'function') return null;
            const save=Game.WriteSave(1);
            return typeof save==='string' && save.length>0 ? save : null;
        })()""")
        return payload if isinstance(payload, str) and payload else None

    def get_combo_snapshot(self, *, require_minigames: bool = True) -> Dict[str, Any]:
        """Lê em uma avaliação todo o estado usado pelo planejador de combo."""
        payload = self.execute_js("""(() => {
            const unavailable = message => ({available:false, message});
            if (!globalThis.Game || !Game.Objects) return unavailable('Runtime do jogo indisponível');
            const tower=Game.Objects['Wizard tower'];
            const temple=Game.Objects['Temple'];
            const bank=Game.Objects['Bank'];
            const M=tower && tower.minigameLoaded ? tower.minigame : {};
            const P=temple && temple.minigameLoaded ? temple.minigame : {};
            const B=bank && bank.minigameLoaded ? bank.minigame : {};
            if (__REQUIRE_MINIGAMES__ && (!tower || !tower.minigameLoaded || !temple || !temple.minigameLoaded || !bank || !bank.minigameLoaded)) return unavailable('Grimoire, Pantheon ou Stock Market não está carregado');
            const finite=(value,fallback=0)=>Number.isFinite(Number(value))?Number(value):fallback;
            const fps=Math.max(1,finite(Game.fps,30));
            const skip=M.spellsById && M.spellsById[4];
            const achievement=Game.Achievements && Game.Achievements['And a little extra'];
            const store=Array.from(Game.UpgradesInStore || []);
            const lovesick=Game.Upgrades && Game.Upgrades['Lovesick biscuit'];
            return {
                available:true,
                message:'Snapshot de combo disponível',
                screen:Game.OnAscend?'ascend':((finite(Game.AscendTimer)>0||finite(Game.ReincarnateTimer)>0)?'transition':'game'),
                version:String(Game.version), seed:String(Game.seed || ''), season:String(Game.season || ''),
                seasonSwitchAvailable:!!(lovesick && lovesick.unlocked),
                cookies:finite(Game.cookies), cookiesEarned:finite(Game.cookiesEarned),
                cookiesPs:finite(Game.cookiesPs), mouseCps:finite(Game.computedMouseCps),
                achievementWon:!!(achievement && achievement.won),
                lumps:Math.max(0,Math.trunc(finite(Game.lumps))),
                canRefillLump:typeof Game.canRefillLump==='function' && !!Game.canRefillLump(),
                lumpRefillRemaining:typeof Game.getLumpRefillRemaining==='function'
                    ? Math.max(0,finite(Game.getLumpRefillRemaining())/fps):0,
                spellsCastTotal:Math.max(0,Math.trunc(finite(M.spellsCastTotal))),
                magic:finite(M.magic), magicM:finite(M.magicM),
                skipSpellCost:skip && typeof M.getSpellCost==='function' ? finite(M.getSpellCost(skip),Infinity):Infinity,
                fthofCost:M.spellsById && M.spellsById[1] ? finite(M.getSpellCost(M.spellsById[1]),Infinity):Infinity,
                wizardTowers:Math.max(0,Math.trunc(finite(tower && tower.amount))),
                wizardTowerLevel:Math.max(0,Math.trunc(finite(tower && tower.level))),
                auras:[Math.trunc(finite(Game.dragonAura)),Math.trunc(finite(Game.dragonAura2))],
                pantheonSwaps:Math.max(0,Math.trunc(finite(P.swaps))),
                pantheonSlots:Array.from(P.slot || []).map(value=>Math.trunc(finite(value,-1))),
                officeLevel:Math.max(0,Math.trunc(finite(B.officeLevel))),
                goldenSwitchOn:store.some(upgrade=>upgrade && upgrade.name==='Golden switch [on]'),
                sugarFrenzyUsed:!!(Game.Upgrades && Game.Upgrades['Sugar frenzy'] && Game.Upgrades['Sugar frenzy'].bought),
                buffs:Object.values(Game.buffs || {}).map(buff=>({
                    id:Math.trunc(finite(buff.id,-1)), name:String(buff.name || ''),
                    type:String(buff.type && buff.type.name || ''),
                    timeSeconds:Math.max(0,finite(buff.time)/fps),
                    maxTimeSeconds:Math.max(0,finite(buff.maxTime)/fps),
                    multCpS:finite(buff.multCpS,1), multClick:finite(buff.multClick,1),
                    buildingId:Number.isFinite(Number(buff.arg2))?Math.trunc(Number(buff.arg2)):null
                })),
                shimmers:(Game.shimmers || []).filter(shimmer=>shimmer && shimmer.type==='golden').map(shimmer=>({
                    id:Math.trunc(finite(shimmer.id,-1)), force:String(shimmer.force || ''),
                    wrath:!!shimmer.wrath, lifeSeconds:Math.max(0,finite(shimmer.life)/fps)
                })),
                buildings:Object.values(Game.ObjectsById || {}).filter(Boolean).map(object=>({
                    id:Number(object.id), name:String(object.name || object.id),
                    amount:Math.max(0,Math.trunc(finite(object.amount))), level:Math.max(0,Math.trunc(finite(object.level)))
                }))
            };
        })()""".replace("__REQUIRE_MINIGAMES__", "true" if require_minigames else "false"))
        return payload if isinstance(payload, dict) else {
            "available": False, "message": "Resposta inválida do snapshot de combo"
        }

    def forecast_combo_window(self, max_ahead: int, required_total_bs: int) -> Dict[str, Any]:
        """Procura a melhor janela de Quadcast sem alterar contador, mana ou save."""
        if not isinstance(max_ahead, int) or not 4 <= max_ahead <= 100_000:
            return {"ok": False, "message": "Alcance de forecast inválido"}
        if not isinstance(required_total_bs, int) or not 1 <= required_total_bs <= 6:
            return {"ok": False, "message": "Meta de Building Specials inválida"}
        script = """(() => {
            const maxAhead=__MAX_AHEAD__, requiredTotalBs=__REQUIRED_BS__;
            const fail=message=>({ok:false,message});
            const tower=globalThis.Game && Game.Objects ? Game.Objects['Wizard tower'] : null;
            const M=tower && tower.minigameLoaded ? tower.minigame : null;
            const spell=M && M.spellsById ? M.spellsById[1] : null;
            if (!M || !spell || typeof Math.seedrandom!=='function') return fail('Grimoire ou seedrandom indisponível');
            const current=Math.trunc(Number(M.spellsCastTotal));
            if (!Number.isFinite(current)) return fail('Contador de spells inválido');
            const onscreen=Number(Game.shimmerTypes && Game.shimmerTypes.golden && Game.shimmerTypes.golden.n)||0;
            let failBase=Number(M.getFailChance(spell))-0.15*onscreen;
            if (!Number.isFinite(failBase)) return fail('Chance de backfire inválida');
            failBase=Math.max(0,Math.min(1,failBase));
            const canSeason=!!(Game.Upgrades && Game.Upgrades['Lovesick biscuit'] && Game.Upgrades['Lovesick biscuit'].unlocked);
            const currentSeason=String(Game.season || '');
            const modes=[];
            modes.push({season:currentSeason,seasonal:currentSeason==='valentines'||currentSeason==='easter'});
            if (canSeason && !modes.some(mode=>mode.season==='valentines')) modes.push({season:'valentines',seasonal:true});

            function outcome(cast,existing,seasonal) {
                const oldRandom=Math.random;
                try {
                    Math.seedrandom(String(Game.seed)+'/'+cast);
                    const successRoll=Math.random();
                    const success=successRoll < 1-(failBase+0.15*existing);
                    Math.random(); Math.random();
                    if (seasonal) Math.random();
                    let choices;
                    if (success) {
                        choices=['frenzy','multiply cookies','click frenzy'];
                        if (Math.random()<0.1) choices.push('cookie storm','cookie storm','blab');
                        if (Number(Game.BuildingsOwned)>=10 && Math.random()<0.25) choices.push('building special');
                        if (Math.random()<0.15) choices=['cookie storm drop'];
                        if (Math.random()<0.0001) choices.push('free sugar lump');
                    } else {
                        choices=['clot','ruin cookies'];
                        if (Math.random()<0.1) choices.push('cursed finger','blood frenzy');
                        if (Math.random()<0.003) choices.push('free sugar lump');
                        if (Math.random()<0.1) choices=['blab'];
                    }
                    return choices[Math.floor(Math.random()*choices.length)];
                } finally { Math.random=oldRandom; }
            }

            let best=null;
            for (const mode of modes) {
                for (let offset=0;offset<=maxAhead-4;offset++) {
                    const start=current+offset;
                    const results=[0,1,2,3].map(index=>outcome(start+index,index,mode.seasonal));
                    const ef=results.filter(value=>value==='blood frenzy').length;
                    const cf=results.filter(value=>value==='click frenzy').length;
                    const bs=results.filter(value=>value==='building special').length;
                    if (ef<1 || cf<1 || bs<1) continue;
                    const natural=Math.max(0,requiredTotalBs-bs);
                    if (natural>2) continue;
                    const score=offset+natural*250-bs*25;
                    const candidate={startCast:start,skipCount:offset,season:mode.season,results,
                        spellBuildingSpecials:bs,naturalBuildingSpecials:natural,score};
                    // Preserve a janela já alinhada na season atual: não gaste
                    // centenas de skips apenas para buscar mais um BS de spell.
                    if (offset===0 && mode.season===currentSeason)
                        return Object.assign({ok:true,seed:String(Game.seed),version:String(Game.version),currentCast:current,failBase},candidate);
                    if (!best || candidate.score<best.score ||
                            (candidate.score===best.score && candidate.skipCount<best.skipCount)) best=candidate;
                }
            }
            if (!best) return fail('Nenhuma janela EF + CF + BS encontrada');
            return Object.assign({ok:true,seed:String(Game.seed),version:String(Game.version),currentCast:current,failBase},best);
        })()""".replace("__MAX_AHEAD__", str(max_ahead)).replace("__REQUIRED_BS__", str(required_total_bs))
        payload = self.execute_js(script)
        return payload if isinstance(payload, dict) else {
            "ok": False, "message": "Resposta inválida do forecast"
        }

    def forecast_simple_farm_spell(self, max_ahead: int) -> Dict[str, Any]:
        """Prevê um único Click Frenzy sem exigir uma quantidade mínima de torres."""
        if isinstance(max_ahead, bool) or not isinstance(max_ahead, int) or not 2 <= max_ahead <= 10_000:
            return {"ok": False, "message": "Alcance do Simple Farm inválido"}
        script = """(() => {
            const maxAhead=__MAX_AHEAD__;
            const fail=message=>({ok:false,message});
            const tower=globalThis.Game && Game.Objects ? Game.Objects['Wizard tower'] : null;
            const M=tower && tower.minigameLoaded ? tower.minigame : null;
            const spell=M && M.spellsById ? M.spellsById[1] : null;
            if (!M || !spell || typeof Math.seedrandom!=='function')
                return fail('Grimoire ou seedrandom indisponível');
            const current=Math.trunc(Number(M.spellsCastTotal));
            const onscreen=Number(Game.shimmerTypes && Game.shimmerTypes.golden && Game.shimmerTypes.golden.n)||0;
            let failBase=Number(M.getFailChance(spell))-0.15*onscreen;
            if (!Number.isFinite(current) || !Number.isFinite(failBase))
                return fail('Estado do Grimoire inválido');
            failBase=Math.max(0,Math.min(1,failBase));
            const seasonal=Game.season==='valentines'||Game.season==='easter';
            function outcome(cast,existing) {
                const oldRandom=Math.random;
                try {
                    Math.seedrandom(String(Game.seed)+'/'+cast);
                    const success=Math.random()<1-(failBase+0.15*existing);
                    Math.random(); Math.random(); if (seasonal) Math.random();
                    let choices;
                    if (success) {
                        choices=['frenzy','multiply cookies','click frenzy'];
                        if (Math.random()<0.1) choices.push('cookie storm','cookie storm','blab');
                        if (Number(Game.BuildingsOwned)>=10 && Math.random()<0.25) choices.push('building special');
                        if (Math.random()<0.15) choices=['cookie storm drop'];
                        if (Math.random()<0.0001) choices.push('free sugar lump');
                    } else {
                        choices=['clot','ruin cookies'];
                        if (Math.random()<0.1) choices.push('cursed finger','blood frenzy');
                        if (Math.random()<0.003) choices.push('free sugar lump');
                        if (Math.random()<0.1) choices=['blab'];
                    }
                    return choices[Math.floor(Math.random()*choices.length)];
                } finally { Math.random=oldRandom; }
            }
            for (let offset=0;offset<maxAhead;offset++) {
                if (outcome(current+offset,0)!=='click frenzy') continue;
                return {ok:true,seed:String(Game.seed),version:String(Game.version),
                    currentCast:current,startCast:current+offset,skipCount:offset,
                    results:['click frenzy'],quality:'Click Frenzy com uma magia'};
            }
            return fail('Nenhum Click Frenzy encontrado no alcance; farm continua sem magia');
        })()""".replace("__MAX_AHEAD__", str(max_ahead))
        payload = self.execute_js(script)
        return payload if isinstance(payload, dict) else {
            "ok": False, "message": "Resposta inválida do forecast do Simple Farm"
        }

    def execute_simple_farm_spell(
        self, *, expected_cast: int, minimum_buff_seconds: float,
    ) -> Dict[str, Any]:
        """Confirma o forecast e lança/abre um único FtHoF na mesma avaliação."""
        if (isinstance(expected_cast, bool) or not isinstance(expected_cast, int)
                or expected_cast < 0 or not 3 <= minimum_buff_seconds <= 60):
            return {"ok": False, "message": "Parâmetros da magia inválidos"}
        script = """(() => {
            const expectedCast=__CAST__, minimum=__MINIMUM__;
            const fail=(message,extra={waiting:true})=>Object.assign({ok:false,message},extra);
            if (!globalThis.Game || Game.OnAscend || Game.AscendTimer || Game.ReincarnateTimer)
                return fail('Jogo em transição');
            const tower=Game.Objects && Game.Objects['Wizard tower'];
            const M=tower && tower.minigameLoaded ? tower.minigame : null;
            const spell=M && M.spellsById && M.spellsById[1];
            if (!spell || typeof Math.seedrandom!=='function') return fail('Grimoire indisponível');
            if (Number(M.spellsCastTotal)!==expectedCast) return fail('Contador de spells mudou');
            if (!(Number(M.magicM)>0) || Number(M.magic)<Number(M.magicM) ||
                Number(M.magic)<Number(M.getSpellCost(spell))) return fail('Aguardando mana suficiente e cheia');
            if ((Game.shimmers||[]).some(s=>s && s.type==='golden')) return fail('Golden Cookie em tela');
            const buffs=Object.values(Game.buffs||{});
            const has=type=>buffs.some(b=>b && b.type && b.type.name===type && b.time>0);
            if (has('dragonflight') || has('click frenzy')) return fail('Buff de clique já ativo; preservando mana');
            const fps=Math.max(1,Number(Game.fps)||30);
            if (!buffs.some(b=>b && b.type &&
                ['frenzy','dragon harvest','building buff','blood frenzy'].includes(b.type.name) &&
                Number(b.time)/fps>=minimum)) return fail('Aguardando multiplicador de produção');
            const seasonal=Game.season==='valentines'||Game.season==='easter';
            const failBase=Math.max(0,Math.min(1,Number(M.getFailChance(spell))));
            function predict(cast,existing) {
                const oldRandom=Math.random;
                try {
                    Math.seedrandom(String(Game.seed)+'/'+cast);
                    const success=Math.random()<1-(failBase+0.15*existing);
                    Math.random(); Math.random(); if (seasonal) Math.random();
                    let choices;
                    if (success) {
                        choices=['frenzy','multiply cookies','click frenzy'];
                        if (Math.random()<0.1) choices.push('cookie storm','cookie storm','blab');
                        if (Number(Game.BuildingsOwned)>=10 && Math.random()<0.25) choices.push('building special');
                        if (Math.random()<0.15) choices=['cookie storm drop'];
                        if (Math.random()<0.0001) choices.push('free sugar lump');
                    } else {
                        choices=['clot','ruin cookies'];
                        if (Math.random()<0.1) choices.push('cursed finger','blood frenzy');
                        if (Math.random()<0.003) choices.push('free sugar lump');
                        if (Math.random()<0.1) choices=['blab'];
                    }
                    return choices[Math.floor(Math.random()*choices.length)];
                } finally { Math.random=oldRandom; }
            }

            if (predict(expectedCast,0)!=='click frenzy') return fail('Previsão mudou; replanejando');
            const before=new Set((Game.shimmers||[]).map(s=>s.id));
            if (M.castSpell(spell)!==true) return fail('O jogo recusou a magia');
            const created=(Game.shimmers||[]).find(s=>s && s.type==='golden' && !before.has(s.id));
            if (!created || created.force!=='click frenzy')
                return fail('Resultado inesperado da magia; verifique o jogo',{waiting:false});
            created.pop();
            return {ok:true,message:'Click Frenzy ativado com uma magia, sem gastar cookies ou lumps'};
        })()""".replace("__CAST__", str(expected_cast)).replace("__MINIMUM__", repr(float(minimum_buff_seconds)))
        payload = self.execute_js(script)
        return payload if isinstance(payload, dict) else {"ok": False, "message": "Resposta inválida da magia"}

    def reinvest_simple_farm(
        self, cash_floor: float, max_spend_fraction: float, reserve_fraction: float = 0.80,
    ) -> Dict[str, Any]:
        """Compra produção com orçamento único e reserva conferida no saldo vivo."""
        values = (cash_floor, max_spend_fraction, reserve_fraction)
        if (any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values)
                or not 0 <= cash_floor < float("inf")
                or not 0.01 <= max_spend_fraction <= 0.20
                or not 0.60 <= reserve_fraction <= 0.99):
            return {"ok": False, "message": "Orçamento de reinvestimento inválido"}
        script = """(() => {
            const cashFloor=__FLOOR__, fraction=__FRACTION__, reserveFraction=__RESERVE__;
            const fail=(message,extra={})=>Object.assign({ok:false,message},extra);
            if (!globalThis.Game || !Game.ObjectsById) return fail('Runtime indisponível');
            if (Game.OnAscend || Game.AscendTimer || Game.ReincarnateTimer)
                return fail('Jogo em transição',{waiting:true});
            const before=Number(Game.cookies), lumpsBefore=Number(Game.lumps);
            if (!Number.isFinite(before) || before<=0) return fail('Caixa vazio',{waiting:true});
            // A avaliação inteira é atômica; Garden/Banco podem ter gasto desde o snapshot.
            const buffs=Object.values(Game.buffs||{});
            if (buffs.some(b=>b && b.time>0 && b.type &&
                ['frenzy','dragon harvest','building buff','click frenzy','blood frenzy',
                 'dragonflight','devastation','cursed finger'].includes(b.type.name)))
                return fail('Aproveitando buff; compras adiadas',{waiting:true});
            const luckyReserve=Math.max(0,Number(Game.cookiesPs)||0)*6000;
            const reserve=Math.max(cashFloor,before*reserveFraction,luckyReserve);
            const budget=Math.max(0,Math.min(before*fraction,before-reserve));
            let spent=0, upgrades=0, buildings=0;
            const items=[];
            const remaining=()=>Math.max(0,Math.min(budget-spent,Number(Game.cookies)-reserve));
            if (budget<1) return fail('Acumulando caixa; reserva para as outras farms preservada',
                {waiting:true,before,after:before,reserve,budget});
            function priority(u) {
                if (u.pool==='cookie' && u.power) return 0; // produção global em %
                if (String(u.name).toLowerCase().includes('kitten')) return 1;
                if (u.buildingTie) return 2;
                if (/mouse|finger/i.test(String(u.name))) return 3;
                return 9;
            }
            function allowed(u) {
                if (!u || u.bought || typeof u.buy!=='function' || priority(u)===9) return false;
                const name=String(u.name||'').toLowerCase();
                if (name==='sugar frenzy' || name==='chocolate egg' || Number(u.priceLumps)>0) return false;
                if (['toggle','tech','prestige'].includes(String(u.pool||''))) return false;
                if (u.clickFunction || u.choicesFunction) return false;
                try {
                    if (typeof u.isVaulted==='function' && u.isVaulted()) return false;
                    if (typeof u.canBuy==='function' && !u.canBuy()) return false;
                } catch (_) { return false; }
                return true;
            }
            // Até metade do orçamento para um upgrade; o restante fica para buildings.
            const candidates=Array.from(Game.UpgradesInStore||[]).filter(allowed).map(u=>{
                let price=Infinity;
                try { price=Number(u.getPrice()); } catch (_) {}
                const power=typeof u.power==='number' && u.power>0 ? u.power : 1;
                return {u,price,rank:priority(u),value:power/Math.max(1,price)};
            }).filter(c=>Number.isFinite(c.price) && c.price>=0 && c.price<=budget/2 && c.price<=remaining())
              .sort((a,b)=>a.rank-b.rank || b.value-a.value || a.price-b.price);
            if (candidates.length) {
                const c=candidates[0], old=Number(Game.cookies);
                c.u.buy();
                const paid=old-Number(Game.cookies);
                if (!c.u.bought || paid<0 || Number(Game.cookies)<reserve || paid>budget)
                    return fail('Compra de upgrade não confirmada dentro do orçamento');
                spent+=paid; upgrades++;
                items.push(String(c.u.name));
            }
            const buyMode=Game.buyMode;
            try {
                Game.buyMode=1;
                while (buildings<25 && remaining()>=1) {
                    const choices=Object.values(Game.ObjectsById).filter(o=>o && o.unlocked!==0 &&
                        typeof o.buy==='function').map(o=>{
                        let price=Infinity;
                        try { price=Number(o.getPrice()); } catch (_) {}
                        const amount=Number(o.amount)||0;
                        const gain=amount>0 ? Number(o.storedTotalCps)/amount : Number(o.storedCps||o.baseCps);
                        return {o,price,gain,roi:gain/price};
                    }).filter(c=>Number.isFinite(c.price) && c.price>0 && Number.isFinite(c.gain) &&
                        c.gain>0 && c.price<=remaining()).sort((a,b)=>b.roi-a.roi || a.price-b.price);
                    if (!choices.length) break;
                    const c=choices[0], amount=Number(c.o.amount), old=Number(Game.cookies);
                    c.o.buy(1);
                    const paid=old-Number(Game.cookies);
                    if (Number(c.o.amount)!==amount+1 || paid<0 || spent+paid>budget || Number(Game.cookies)<reserve)
                        return fail('Compra de construção não confirmada dentro do orçamento');
                    spent+=paid; buildings++;
                }
            } finally { Game.buyMode=buyMode; }
            const after=Number(Game.cookies);
            if (Number(Game.lumps)!==lumpsBefore) return fail('Quantidade de Sugar Lumps mudou na compra');
            if (!upgrades && !buildings) return fail('Acumulando caixa; nenhuma compra de produção cabe no orçamento',
                {waiting:true,before,after,reserve,budget});
            return {ok:true,upgrades,buildings,spent,before,after,reserve,budget,
                message:`Comprados: ${upgrades} upgrade(s)${items.length?' ('+items.join(', ')+')':''} e ${buildings} construção(ões) por retorno de CpS`};
        })()""".replace("__FLOOR__", repr(float(cash_floor))).replace(
            "__FRACTION__", repr(float(max_spend_fraction))
        ).replace("__RESERVE__", repr(float(reserve_fraction)))
        payload = self.execute_js(script)
        return payload if isinstance(payload, dict) else {"ok": False, "message": "Resposta inválida do reinvestimento"}

    def pop_combo_natural_shimmer(self, shimmer_id: int) -> Dict[str, Any]:
        """Coleta somente o shimmer natural esperado, nunca um FtHoF."""
        if not isinstance(shimmer_id, int) or shimmer_id < 0:
            return {"ok": False, "message": "Identificador de shimmer inválido"}
        payload = self.execute_js("""(() => {
            const id=__ID__;
            const shimmer=(Game.shimmers||[]).find(item=>item && item.type==='golden' && Number(item.id)===id);
            if (!shimmer) return {ok:false,gone:true,message:'Golden Cookie natural não está mais em tela'};
            if (shimmer.force) return {ok:false,message:'Shimmer pertence a uma spell; clique recusado'};
            const before=(Game.shimmers||[]).length;
            shimmer.pop();
            const removed=!(Game.shimmers||[]).some(item=>item && Number(item.id)===id);
            return {ok:removed,message:removed?'Golden Cookie natural coletado':'O clique natural não foi confirmado',before,after:(Game.shimmers||[]).length};
        })()""".replace("__ID__", str(shimmer_id)))
        return payload if isinstance(payload, dict) else {"ok": False, "message": "Resposta inválida ao clicar shimmer"}

    def pop_combo_cookie_storm_drops(self) -> Dict[str, Any]:
        """Drena somente drops de Cookie Storm, sem tocar em outros shimmers."""
        payload = self.execute_js("""(() => {
            const drops=(Game.shimmers||[]).filter(item=>item && item.type==='golden' &&
                String(item.force||'')==='cookie storm drop');
            if (!drops.length) return {ok:true,gone:true,count:0,message:'Os drops do Cookie Storm já expiraram'};
            const ids=drops.map(item=>Number(item.id));
            let count=0;
            for (const id of ids) {
                const shimmer=(Game.shimmers||[]).find(item=>item && item.type==='golden' &&
                    Number(item.id)===id && String(item.force||'')==='cookie storm drop');
                if (!shimmer) continue;
                shimmer.pop();
                if (!(Game.shimmers||[]).some(item=>item && Number(item.id)===id)) count++;
            }
            const remaining=ids.filter(id=>(Game.shimmers||[]).some(item=>item && Number(item.id)===id));
            return {ok:remaining.length===0,count,attempted:ids.length,remaining:remaining.length,
                message:remaining.length===0?'Drops do Cookie Storm coletados':'Alguns drops do Cookie Storm ainda estão em tela'};
        })()""")
        return payload if isinstance(payload, dict) else {
            "ok": False, "message": "Resposta inválida ao drenar Cookie Storm"
        }

    def set_combo_season(self, season: str) -> Dict[str, Any]:
        """Troca para Valentine/Easter pela API nativa e confirma a season."""
        triggers = {"valentines": "Lovesick biscuit", "easter": "Bunny biscuit"}
        if season not in triggers:
            return {"ok": False, "message": "Season não suportada pelo modo Combo"}
        script = """(() => {
            const season=__SEASON__,name=__NAME__;
            if (String(Game.season||'')===season) return {ok:true,message:'Season já estava configurada'};
            const upgrade=Game.Upgrades && Game.Upgrades[name];
            if (!upgrade || !upgrade.unlocked || typeof upgrade.buy!=='function')
                return {ok:false,message:'Season switcher não está disponível'};
            const before=Number(Game.cookies);
            const accepted=upgrade.buy()===1;
            const ok=String(Game.season||'')===season;
            return {ok,message:ok?'Season alterada e verificada':'O jogo não confirmou a troca de season',accepted,before,after:Number(Game.cookies)};
        })()""".replace("__SEASON__", json.dumps(season)).replace("__NAME__", json.dumps(triggers[season]))
        payload = self.execute_js(script)
        return payload if isinstance(payload, dict) else {"ok": False, "message": "Resposta inválida ao trocar season"}

    def set_combo_golden_switch(self, enabled: bool) -> Dict[str, Any]:
        """Liga/desliga o Golden Switch somente se o estado atual divergir."""
        if not isinstance(enabled, bool):
            return {"ok": False, "message": "Estado do Golden Switch inválido"}
        script = """(() => {
            const desired=__DESIRED__;
            const store=Array.from(Game.UpgradesInStore||[]);
            const current=store.some(upgrade=>upgrade && upgrade.name==='Golden switch [on]');
            if (current===desired) return {ok:true,message:'Golden Switch já estava no estado solicitado',enabled:current};
            const name=desired?'Golden switch [off]':'Golden switch [on]';
            const upgrade=Game.Upgrades && Game.Upgrades[name];
            if (!upgrade || typeof upgrade.buy!=='function') return {ok:false,message:'Toggle do Golden Switch indisponível'};
            const accepted=upgrade.buy()===1;
            const after=Array.from(Game.UpgradesInStore||[]).some(item=>item && item.name==='Golden switch [on]');
            return {ok:after===desired,message:after===desired?'Golden Switch alterado e verificado':'O jogo recusou o Golden Switch',accepted,enabled:after};
        })()""".replace("__DESIRED__", "true" if enabled else "false")
        payload = self.execute_js(script)
        return payload if isinstance(payload, dict) else {"ok": False, "message": "Resposta inválida do Golden Switch"}

    def upgrade_combo_office_once(self) -> Dict[str, Any]:
        """Compra Cursors se necessário e avança exatamente um nível de escritório."""
        payload = self.execute_js("""(() => {
            const bank=Game.Objects && Game.Objects['Bank'];
            const cursor=Game.Objects && Game.Objects['Cursor'];
            const M=bank && bank.minigameLoaded ? bank.minigame : null;
            if (!M || !cursor || !Array.isArray(M.offices)) return {ok:false,message:'Stock Market indisponível'};
            const before=Math.trunc(Number(M.officeLevel)||0);
            const office=M.offices[before];
            if (!office || !office.cost) return {ok:true,message:'Escritório já está no nível máximo',before,after:before};
            const amount=Math.max(0,Math.trunc(Number(office.cost[0])||0));
            const level=Math.max(0,Math.trunc(Number(office.cost[1])||0));
            if (Number(cursor.level)<level) return {ok:false,message:`Cursor precisa estar no nível ${level}`};
            const missing=Math.max(0,amount-Number(cursor.amount));
            if (missing>0) {
                let price=Infinity;
                try { price=Number(cursor.getSumPrice(missing)); } catch (_) {}
                if (!Number.isFinite(price) || price>Number(Game.cookies))
                    return {ok:false,message:`Cookies insuficientes para comprar ${missing} Cursors`};
                const buyMode=Game.buyMode;
                try { Game.buyMode=1; cursor.buy(missing); }
                finally { Game.buyMode=buyMode; }
            }
            if (Number(cursor.amount)<amount) return {ok:false,message:'Compra de Cursors não foi confirmada'};
            cursor.sacrifice(amount);
            M.officeLevel=before+1;
            if (M.officeLevel>=M.offices.length-1) Game.Win('Pyramid scheme');
            const after=Math.trunc(Number(M.officeLevel)||0);
            return {ok:after===before+1,message:after===before+1?'Escritório aprimorado e verificado':'Nível do escritório divergente',before,after,cursorsSpent:amount};
        })()""")
        return payload if isinstance(payload, dict) else {"ok": False, "message": "Resposta inválida ao aprimorar escritório"}

    def configure_combo_pantheon(self, desired_slots: List[int]) -> Dict[str, Any]:
        """Move no máximo um espírito por chamada e consome um worship swap real."""
        if (
            not isinstance(desired_slots, list) or len(desired_slots) != 3
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in desired_slots)
            or len(set(desired_slots)) != 3
        ):
            return {"ok": False, "message": "Configuração do Pantheon inválida"}
        script = """(() => {
            const desired=__DESIRED__;
            const temple=Game.Objects && Game.Objects['Temple'];
            const M=temple && temple.minigameLoaded ? temple.minigame : null;
            if (!M || !Array.isArray(M.slot) || typeof M.slotGod!=='function' || typeof M.useSwap!=='function')
                return {ok:false,message:'Pantheon indisponível'};
            if (desired.every((god,slot)=>Number(M.slot[slot])===god))
                return {ok:true,message:'Pantheon já estava configurado',slots:Array.from(M.slot)};
            if (Number(M.swaps)<1) return {ok:false,message:'Aguardando worship swap do Pantheon',waiting:true};
            const slot=desired.findIndex((god,index)=>Number(M.slot[index])!==god);
            const god=M.godsById && M.godsById[desired[slot]];
            if (!god) return {ok:false,message:'Espírito desejado não existe no runtime'};
            M.slotGod(god,slot);
            M.useSwap(1);
            const ok=Number(M.slot[slot])===Number(god.id);
            return {ok,message:ok?'Espírito movido e verificado':'O Pantheon não confirmou o slot',slots:Array.from(M.slot),swaps:Number(M.swaps)};
        })()""".replace("__DESIRED__", json.dumps(desired_slots))
        payload = self.execute_js(script)
        return payload if isinstance(payload, dict) else {"ok": False, "message": "Resposta inválida do Pantheon"}

    def set_combo_auras(self, primary: int, secondary: int) -> Dict[str, Any]:
        """Configura as duas auras e paga o sacrifício nativo de um prédio por troca."""
        values = (primary, secondary)
        if any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 21 for value in values):
            return {"ok": False, "message": "Aura inválida"}
        if primary == secondary:
            return {"ok": False, "message": "As duas auras precisam ser diferentes"}
        script = """(() => {
            const desired=[__PRIMARY__,__SECONDARY__];
            if (!Game.dragonAuras || Number(Game.dragonLevel)<Math.max(...desired)+4)
                return {ok:false,message:'Aura ainda não foi desbloqueada'};
            const before=[Number(Game.dragonAura),Number(Game.dragonAura2)];
            let sacrifices=0;
            function highest() {
                let result=null;
                for (const object of Object.values(Game.Objects||{})) if (Number(object.amount)>0) result=object;
                return result;
            }
            for (let slot=0;slot<2;slot++) {
                const current=slot===0?Number(Game.dragonAura):Number(Game.dragonAura2);
                if (current===desired[slot]) continue;
                const building=highest();
                if (building) { building.sacrifice(1); sacrifices++; }
                if (slot===0) Game.dragonAura=desired[slot]; else Game.dragonAura2=desired[slot];
            }
            Game.recalculateGains=1;
            const after=[Number(Game.dragonAura),Number(Game.dragonAura2)];
            const ok=after[0]===desired[0] && after[1]===desired[1];
            return {ok,message:ok?'Auras configuradas e verificadas':'O jogo não confirmou as auras',before,after,sacrifices};
        })()""".replace("__PRIMARY__", str(primary)).replace("__SECONDARY__", str(secondary))
        payload = self.execute_js(script)
        return payload if isinstance(payload, dict) else {"ok": False, "message": "Resposta inválida ao configurar auras"}

    def set_combo_wizard_towers(self, target: int) -> Dict[str, Any]:
        """Ajusta Wizard Towers para um alvo exato e confirma a quantidade."""
        if isinstance(target, bool) or not isinstance(target, int) or not 1 <= target <= 100_000:
            return {"ok": False, "message": "Alvo de Wizard Towers inválido"}
        script = """(() => {
            const target=__TARGET__;
            const tower=Game.Objects && Game.Objects['Wizard tower'];
            if (!tower) return {ok:false,message:'Wizard Towers indisponíveis'};
            const before=Math.trunc(Number(tower.amount)||0);
            if (before===target) return {ok:true,message:'Wizard Towers já estavam no alvo',before,after:before};
            if (before>target) tower.sell(before-target);
            else {
                const quantity=target-before;
                let price=Infinity;
                try { price=Number(tower.getSumPrice(quantity)); } catch (_) {}
                if (!Number.isFinite(price) || price>Number(Game.cookies))
                    return {ok:false,message:'Cookies insuficientes para recomprar Wizard Towers',before,price};
                const buyMode=Game.buyMode;
                try { Game.buyMode=1; tower.buy(quantity); }
                finally { Game.buyMode=buyMode; }
            }
            const after=Math.trunc(Number(tower.amount)||0);
            return {ok:after===target,message:after===target?'Wizard Towers ajustadas e verificadas':'Quantidade final de Wizard Towers divergente',before,after};
        })()""".replace("__TARGET__", str(target))
        payload = self.execute_js(script)
        return payload if isinstance(payload, dict) else {"ok": False, "message": "Resposta inválida ao ajustar Wizard Towers"}

    def ensure_combo_building_minimum(self, building_id: int, minimum: int) -> Dict[str, Any]:
        """Compra um prédio até o estoque mínimo usado pela venda final de Godzamok."""
        if (
            isinstance(building_id, bool) or not isinstance(building_id, int) or building_id < 0
            or isinstance(minimum, bool) or not isinstance(minimum, int) or not 1 <= minimum <= 100_000
        ):
            return {"ok": False, "message": "Estoque mínimo de prédio inválido"}
        script = """(() => {
            const id=__ID__,minimum=__MINIMUM__;
            const object=Game.ObjectsById && Game.ObjectsById[id];
            if (!object || typeof object.buy!=='function' || typeof object.getSumPrice!=='function')
                return {ok:false,message:'Prédio indisponível para recomposição',id};
            const before=Math.max(0,Math.trunc(Number(object.amount)||0));
            if (before>=minimum)
                return {ok:true,message:'Estoque de Godzamok já estava preparado',id,before,after:before,bought:0};
            const quantity=minimum-before;
            let price=Infinity;
            try { price=Number(object.getSumPrice(quantity)); } catch (_) {}
            if (!Number.isFinite(price) || price>Number(Game.cookies))
                return {ok:false,message:'Cookies insuficientes para recompor o estoque de Godzamok',id,before,price};
            const buyMode=Game.buyMode;
            try { Game.buyMode=1; object.buy(quantity); }
            finally { Game.buyMode=buyMode; }
            const after=Math.max(0,Math.trunc(Number(object.amount)||0));
            return {ok:after>=minimum,
                message:after>=minimum?'Estoque de Godzamok recomposto e verificado':'O jogo não confirmou a recomposição do prédio',
                id,before,after,bought:Math.max(0,after-before),price};
        })()""".replace("__ID__", str(building_id)).replace("__MINIMUM__", str(minimum))
        payload = self.execute_js(script)
        return payload if isinstance(payload, dict) else {
            "ok": False, "message": "Resposta inválida ao recompor prédio para Godzamok"
        }

    def cast_combo_skip(self, expected_cast: int, spell_id: int = 4) -> Dict[str, Any]:
        """Avança exatamente um contador com uma spell não-FtHoF barata."""
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in (expected_cast, spell_id)):
            return {"ok": False, "message": "Parâmetros de alinhamento inválidos"}
        script = """(() => {
            const expected=__EXPECTED__,spellId=__SPELL_ID__;
            const tower=Game.Objects && Game.Objects['Wizard tower'];
            const M=tower && tower.minigameLoaded ? tower.minigame : null;
            if (!M || !M.spellsById || typeof M.castSpell!=='function') return {ok:false,message:'Grimoire indisponível'};
            const before=Math.trunc(Number(M.spellsCastTotal)||0);
            if (before!==expected) return {ok:false,message:'Contador de spells mudou antes do alinhamento',before,expected};
            const spell=M.spellsById[spellId];
            if (!spell || spellId===1) return {ok:false,message:'Spell de alinhamento inválida'};
            const cost=Number(M.getSpellCost(spell));
            if (!Number.isFinite(cost) || Number(M.magic)<cost) return {ok:false,message:'Mana insuficiente para o próximo skip',waiting:true,cost,magic:Number(M.magic)};
            const accepted=M.castSpell(spell)===true;
            const after=Math.trunc(Number(M.spellsCastTotal)||0);
            const ok=accepted && after===before+1;
            return {ok,message:ok?'Spell de alinhamento confirmada':'O contador não avançou exatamente uma vez',before,after,cost,magic:Number(M.magic)};
        })()""".replace("__EXPECTED__", str(expected_cast)).replace("__SPELL_ID__", str(spell_id))
        payload = self.execute_js(script)
        return payload if isinstance(payload, dict) else {"ok": False, "message": "Resposta inválida no alinhamento"}

    def refill_combo_magic(self, expected_cast: int) -> Dict[str, Any]:
        """Gasta um lump sem prompt, respeitando o cooldown nativo e verificando a mana."""
        if isinstance(expected_cast, bool) or not isinstance(expected_cast, int) or expected_cast < 0:
            return {"ok": False, "message": "Contador esperado inválido"}
        script = """(() => {
            const expected=__EXPECTED__;
            const tower=Game.Objects && Game.Objects['Wizard tower'];
            const M=tower && tower.minigameLoaded ? tower.minigame : null;
            if (!M) return {ok:false,message:'Grimoire indisponível'};
            if (Math.trunc(Number(M.spellsCastTotal)||0)!==expected)
                return {ok:false,message:'Contador mudou antes da recarga'};
            if (Number(M.magic)>=Number(M.magicM)) return {ok:false,message:'Mana já está cheia'};
            if (Number(Game.lumps)<1) return {ok:false,message:'Sugar Lumps insuficientes'};
            if (typeof Game.canRefillLump!=='function' || !Game.canRefillLump())
                return {ok:false,message:'Recarga por lump ainda está em cooldown',waiting:true};
            const before=Number(M.magic),lumpsBefore=Number(Game.lumps);
            Game.lumps-=1;
            Game.lumpRefill=typeof Game.getLumpRefillMax==='function'?Game.getLumpRefillMax():Game.fps*60*15;
            M.magic=Math.min(Number(M.magicM),Number(M.magic)+100);
            Game.recalculateGains=1;
            const ok=Number(Game.lumps)===lumpsBefore-1 && Number(M.magic)>before;
            return {ok,message:ok?'Mana recarregada com um Sugar Lump':'Recarga de mana não foi confirmada',before,after:Number(M.magic),lumpsSpent:ok?1:0};
        })()""".replace("__EXPECTED__", str(expected_cast))
        payload = self.execute_js(script)
        return payload if isinstance(payload, dict) else {"ok": False, "message": "Resposta inválida na recarga"}

    def execute_combo_quadcast(
        self,
        *,
        expected_cast: int,
        expected_results: List[str],
        minimum_buff_seconds: float,
        required_natural_bs: int,
        use_sugar_frenzy: bool,
        use_loans: bool,
    ) -> Dict[str, Any]:
        """Executa e verifica a janela crítica em uma única avaliação síncrona."""
        allowed = {
            "frenzy", "multiply cookies", "click frenzy", "cookie storm",
            "blab", "building special", "cookie storm drop", "free sugar lump",
            "clot", "ruin cookies", "cursed finger", "blood frenzy",
        }
        if isinstance(expected_cast, bool) or not isinstance(expected_cast, int) or expected_cast < 0:
            return {"ok": False, "message": "Contador inicial inválido"}
        if (
            not isinstance(expected_results, list) or len(expected_results) != 4
            or any(value not in allowed for value in expected_results)
            or not {"blood frenzy", "click frenzy", "building special"}.issubset(expected_results)
        ):
            return {"ok": False, "message": "Resultados esperados inválidos"}
        if not 5 <= minimum_buff_seconds <= 120 or not 0 <= required_natural_bs <= 4:
            return {"ok": False, "message": "Precondições de buff inválidas"}
        script = """(() => {
            const expectedCast=__EXPECTED_CAST__,expectedResults=__EXPECTED_RESULTS__;
            const minimum=__MINIMUM__,requiredNaturalBs=__NATURAL_BS__;
            const useSugar=__USE_SUGAR__,useLoans=__USE_LOANS__;
            const fail=(message,extra={})=>Object.assign({ok:false,message},extra);
            const wait=message=>fail(message,{retryable:true,mutated:false,lumpsSpent:0});
            const tower=Game.Objects && Game.Objects['Wizard tower'];
            const temple=Game.Objects && Game.Objects['Temple'];
            const bank=Game.Objects && Game.Objects['Bank'];
            const M=tower && tower.minigameLoaded ? tower.minigame : null;
            const P=temple && temple.minigameLoaded ? temple.minigame : null;
            const B=bank && bank.minigameLoaded ? bank.minigame : null;
            const spell=M && M.spellsById ? M.spellsById[1] : null;
            if (!M || !P || !B || !spell) return fail('Minigames necessários não estão carregados');
            const fps=Math.max(1,Number(Game.fps)||30);
            const castNow=Math.trunc(Number(M.spellsCastTotal)||0);
            if (castNow!==expectedCast) return wait('Contador de spells divergiu antes do Quadcast');
            if (Number(tower.level)!==10 || Number(tower.amount)!==601)
                return fail('Quadcast requer exatamente 601 Wizard Towers de nível 10',{amount:Number(tower.amount),level:Number(tower.level)});
            if (Number(M.magic)+1e-7<Number(M.magicM)) return fail('Mana não está cheia no início do Quadcast');
            if ((Game.shimmers||[]).some(item=>item && item.type==='golden'))
                return wait('Há Golden/Wrath Cookie em tela antes do Quadcast');
            if (Game.hasBuff && Game.hasBuff('Dragonflight')) return wait('Dragonflight está ativo e removeria Click Frenzy do FtHoF');
            if (Number(Game.lumps)<1 || typeof Game.canRefillLump!=='function' || !Game.canRefillLump())
                return fail('A recarga por Sugar Lump não está disponível');
            const sugar=Game.Upgrades && Game.Upgrades['Sugar frenzy'];
            if (useSugar && (!sugar || typeof sugar.buy!=='function'))
                return fail('Sugar Frenzy configurada, mas indisponível');
            if (useSugar && !sugar.bought && Number(Game.lumps)<2)
                return wait('Faltam lumps para refill e Sugar Frenzy');
            if (useLoans) {
                if (Number(B.officeLevel)<5 || typeof B.takeLoan!=='function')
                    return fail('Os três loans configurados não estão disponíveis');
                for (const id of [1,2,3]) {
                    if (Game.hasBuff('Loan '+id+' (interest)'))
                        return wait('Loan '+id+' está no período de juros');
                    const active=Game.hasBuff('Loan '+id);
                    if (active && Number(active.time)/fps<minimum)
                        return wait('Loan '+id+' está prestes a expirar');
                }
            }
            if (Number(P.slot[0])!==2) return fail('Godzamok não está no slot Diamond');
            if (!Game.ObjectsById[0] || Number(Game.ObjectsById[0].amount)<601)
                return fail('São necessários pelo menos 601 Cursors para a venda final de Godzamok');

            const buffs=Object.values(Game.buffs||{});
            const timed=type=>buffs.find(buff=>buff.type && buff.type.name===type && Number(buff.time)/fps>=minimum);
            if (buffs.some(buff=>buff.type && ['cursed finger','clot','building debuff'].includes(buff.type.name)))
                return wait('Um efeito negativo incompatível está ativo');
            const needsSpellFrenzy=!timed('frenzy');
            if ((needsSpellFrenzy && !expectedResults.includes('frenzy')) || !timed('dragon harvest'))
                return wait('Frenzy ou Dragon Harvest não possui duração mínima');
            const naturalBs=buffs.filter(buff=>buff.type && buff.type.name==='building buff' &&
                Number(buff.time)/fps>=minimum && Number(buff.arg2)!==7);
            if (naturalBs.length<requiredNaturalBs)
                return wait('Building Specials naturais insuficientes ou expirando');

            // Reconfirma a previsão com o RNG carregado nesta versão antes de qualquer mutação.
            const failBase=Math.max(0,Math.min(1,Number(M.getFailChance(spell))));
            const seasonal=Game.season==='valentines'||Game.season==='easter';
            function predict(cast,existing) {
                const oldRandom=Math.random;
                try {
                    Math.seedrandom(String(Game.seed)+'/'+cast);
                    const success=Math.random()<1-(failBase+0.15*existing);
                    Math.random(); Math.random(); if (seasonal) Math.random();
                    let choices;
                    if (success) {
                        choices=['frenzy','multiply cookies','click frenzy'];
                        if (Math.random()<0.1) choices.push('cookie storm','cookie storm','blab');
                        if (Number(Game.BuildingsOwned)>=10 && Math.random()<0.25) choices.push('building special');
                        if (Math.random()<0.15) choices=['cookie storm drop'];
                        if (Math.random()<0.0001) choices.push('free sugar lump');
                    } else {
                        choices=['clot','ruin cookies'];
                        if (Math.random()<0.1) choices.push('cursed finger','blood frenzy');
                        if (Math.random()<0.003) choices.push('free sugar lump');
                        if (Math.random()<0.1) choices=['blab'];
                    }
                    return choices[Math.floor(Math.random()*choices.length)];
                } finally { Math.random=oldRandom; }
            }
            const predicted=[0,1,2,3].map(index=>predict(expectedCast+index,index));
            if (predicted.some((value,index)=>value!==expectedResults[index]))
                return wait('Forecast mudou imediatamente antes da execução');

            // getSumPrice usa a quantidade atual (601); calcule a recompra real
            // que acontecerá depois da venda, partindo de exatamente 1 torre.
            let price=0;
            try {
                for (let i=1;i<601;i++)
                    price+=Number(tower.basePrice)*Math.pow(Number(Game.priceIncrease),Math.max(0,i-Number(tower.free||0)));
                price=Math.ceil(Number(Game.modifyBuildingPrice(tower,price)));
            } catch (_) { price=Infinity; }
            if (!Number.isFinite(price) || price>Number(Game.cookies))
                return fail('Saldo insuficiente para a recompra conservadora das Wizard Towers',{price,cookies:Number(Game.cookies)});

            const created=[];
            function castOne(index) {
                const before=new Set((Game.shimmers||[]).map(item=>Number(item.id)));
                const cost=Number(M.getSpellCost(spell));
                if (!Number.isFinite(cost) || Number(M.magic)<cost) return {ok:false,message:`Mana insuficiente no cast ${index+1}`,cost,magic:Number(M.magic)};
                if (M.castSpell(spell)!==true) return {ok:false,message:`FtHoF ${index+1} foi recusado`};
                const shimmer=(Game.shimmers||[]).find(item=>item && item.type==='golden' && !before.has(Number(item.id)));
                if (!shimmer) return {ok:false,message:`Shimmer ${index+1} não foi identificado`};
                const force=String(shimmer.force||'');
                if (force!==expectedResults[index]) return {ok:false,message:`Resultado divergente no cast ${index+1}`,force,expected:expectedResults[index]};
                created.push({id:Number(shimmer.id),force,shimmer});
                return {ok:true};
            }

            const first=castOne(0); if (!first.ok) return fail(first.message,first);
            tower.sell(600);
            if (Number(tower.amount)!==1) return fail('Venda para 1 Wizard Tower não foi confirmada');
            if (typeof M.computeMagicM==='function') M.computeMagicM();
            if (Number(M.magic)>Number(M.magicM)) M.magic=Number(M.magicM);
            const second=castOne(1); if (!second.ok) return fail(second.message,second);
            const buyMode=Game.buyMode;
            try { Game.buyMode=1; tower.buy(600); }
            finally { Game.buyMode=buyMode; }
            if (Number(tower.amount)!==601) return fail('Recompra de 600 Wizard Towers não foi confirmada');
            if (typeof M.computeMagicM==='function') M.computeMagicM();
            Game.lumps-=1;
            Game.lumpRefill=typeof Game.getLumpRefillMax==='function'?Game.getLumpRefillMax():fps*60*15;
            M.magic=Math.min(Number(M.magicM),Number(M.magic)+100);
            const third=castOne(2); if (!third.ok) return fail(third.message,Object.assign({},third,{lumpsSpent:1}));
            tower.sell(600);
            if (Number(tower.amount)!==1) return fail('Segunda venda para 1 Wizard Tower não foi confirmada',{lumpsSpent:1});
            if (typeof M.computeMagicM==='function') M.computeMagicM();
            if (Number(M.magic)>Number(M.magicM)) M.magic=Number(M.magicM);
            const fourth=castOne(3); if (!fourth.ok) return fail(fourth.message,Object.assign({},fourth,{lumpsSpent:1}));

            // Descobre BS reais antes de gastar Sugar Frenzy/loans. Dois
            // cookies do mesmo prédio só somam duração, não multiplicadores.
            const spellBs=created.filter(item=>item.force==='building special');
            for (const item of spellBs) item.shimmer.pop();
            const finalBs=Object.values(Game.buffs||{}).filter(buff=>buff.type &&
                buff.type.name==='building buff' && Number(buff.time)/fps>=minimum && Number(buff.arg2)!==7);
            const requiredTotalBs=requiredNaturalBs+spellBs.length;
            if (new Set(finalBs.map(buff=>Number(buff.arg2))).size<requiredTotalBs)
                return fail('BS de spell repetiu um prédio; multiplicadores distintos insuficientes. Sugar Frenzy e loans preservados.',
                    {lumpsSpent:1,mutated:true});

            // Frenzy redundante fica em tela para Dragon's Fortune. Se falta
            // Frenzy natural, ativá-lo rende x7, superior ao x2,23 preservado.
            if (needsSpellFrenzy) {
                const frenzy=created.find(item=>item.force==='frenzy');
                if (frenzy) frenzy.shimmer.pop();
            }

            function setAuras(primary,secondary) {
                const desired=[primary,secondary];
                function highest() {
                    let result=null;
                    for (const object of Object.values(Game.Objects||{})) if (Number(object.amount)>0) result=object;
                    return result;
                }
                for (let slot=0;slot<2;slot++) {
                    const current=slot===0?Number(Game.dragonAura):Number(Game.dragonAura2);
                    if (current===desired[slot]) continue;
                    const building=highest(); if (building) building.sacrifice(1);
                    if (slot===0) Game.dragonAura=desired[slot]; else Game.dragonAura2=desired[slot];
                }
                Game.recalculateGains=1;
            }
            setAuras(16,15); // Dragon's Fortune + Radiant Appetite

            let goldenSwitch=false;
            const switchUpgrade=Game.Upgrades && Game.Upgrades['Golden switch [off]'];
            if (switchUpgrade && !Array.from(Game.UpgradesInStore||[]).some(item=>item && item.name==='Golden switch [on]')) {
                try { goldenSwitch=switchUpgrade.buy()===1; } catch (_) { goldenSwitch=false; }
            }

            let lumpsSpent=1,sugarFrenzy=false;
            if (useSugar && sugar && !sugar.bought && Number(Game.lumps)>=1) {
                // Em 2.053 o buff é criado pelo clickFunction, não por
                // buyFunction. buy(1) pula esse caminho e perde o x3.
                const before=Number(Game.lumps),askLumps=Game.prefs.askLumps;
                let sugarError='';
                try { Game.prefs.askLumps=0; sugar.buy(); }
                catch (error) { sugarError=String(error); }
                finally { Game.prefs.askLumps=askLumps; }
                const spent=before-Number(Game.lumps);
                lumpsSpent+=Math.max(0,spent);
                sugarFrenzy=!!Game.hasBuff('Sugar frenzy');
                if (sugarError || spent!==1 || !sugar.bought || !sugarFrenzy)
                    return fail('Sugar Frenzy não confirmou buff e gasto de um lump',
                        {lumpsSpent,mutated:true,sugarError});
            }

            const loans=[];
            if (useLoans && typeof B.takeLoan==='function') {
                for (const id of [1,3,2]) {
                    const required=[0,2,4,5][id];
                    if (Number(B.officeLevel)>=required && !Game.hasBuff('Loan '+id) && !Game.hasBuff('Loan '+id+' (interest)')) {
                        if (B.takeLoan(id)===true && Game.hasBuff('Loan '+id)) loans.push(id);
                        else return fail('Loan '+id+' não foi confirmado',{lumpsSpent,mutated:true});
                    }
                }
            }

            const protectedIds=new Set(Object.values(Game.buffs||{})
                .filter(buff=>buff.type && buff.type.name==='building buff')
                .map(buff=>Number(buff.arg2)));
            const sold=[];
            for (const id of [0,1,2,3,4,5,8,9]) {
                if (protectedIds.has(id) || id===6 || id===7) continue;
                const object=Game.ObjectsById[id];
                if (!object) continue;
                const quantity=Math.max(0,Math.min(600,Number(object.amount)-1));
                if (quantity>0) { object.sell(quantity); sold.push([id,quantity]); }
            }

            const cf=created.find(item=>item.force==='click frenzy');
            const ef=created.find(item=>item.force==='blood frenzy');
            if (!cf || !ef) return fail('CF ou EF desapareceu antes do clique final',{lumpsSpent,created:created.map(item=>[item.id,item.force])});
            cf.shimmer.pop();
            ef.shimmer.pop();
            const clickBuff=Object.values(Game.buffs||{}).find(buff=>buff.type && buff.type.name==='click frenzy');
            const elderBuff=Object.values(Game.buffs||{}).find(buff=>buff.type && buff.type.name==='blood frenzy');
            const devastation=Object.values(Game.buffs||{}).find(buff=>buff.type && buff.type.name==='devastation');
            if (!clickBuff || !elderBuff || !devastation)
                return fail('Buffs finais não foram confirmados',{lumpsSpent,hasCf:!!clickBuff,hasEf:!!elderBuff,hasDevastation:!!devastation});
            const stack=Object.values(Game.buffs||{}).filter(buff=>buff.type &&
                (['frenzy','dragon harvest','click frenzy','blood frenzy','devastation'].includes(buff.type.name)
                 || finalBs.includes(buff)));
            const preserved=(Game.shimmers||[]).filter(item=>item.type==='golden');
            const limitingTimes=stack.map(buff=>Number(buff.time));
            for (const shimmer of preserved) limitingTimes.push(Number(shimmer.life));
            const clickSeconds=Math.min(...limitingTimes)/fps-1;
            if (!Number.isFinite(clickSeconds) || clickSeconds<=0)
                return fail('A janela útil expirou durante a execução',{lumpsSpent,mutated:true});
            return {ok:true,message:'Quadcast e multiplicadores finais confirmados',
                results:created.map(item=>item.force),lumpsSpent,clickSeconds,sold,protectedIds:Array.from(protectedIds),
                goldenSwitch,sugarFrenzy,loans,preserved:(Game.shimmers||[]).filter(item=>item.type==='golden').map(item=>({id:Number(item.id),force:String(item.force||'')})),
                buffs:Object.values(Game.buffs||{}).map(buff=>String(buff.name||'')),wizardTowers:Number(tower.amount)};
        })()"""
        replacements = {
            "__EXPECTED_CAST__": str(expected_cast),
            "__EXPECTED_RESULTS__": json.dumps(expected_results),
            "__MINIMUM__": repr(float(minimum_buff_seconds)),
            "__NATURAL_BS__": str(required_natural_bs),
            "__USE_SUGAR__": "true" if use_sugar_frenzy else "false",
            "__USE_LOANS__": "true" if use_loans else "false",
        }
        for marker, value in replacements.items():
            script = script.replace(marker, value)
        payload = self.execute_js(script)
        return payload if isinstance(payload, dict) else {"ok": False, "message": "Resposta inválida do Quadcast"}

    def get_stock_market_status(self) -> StockMarketStatus:
        """Verifica de forma defensiva se o Stock Market está desbloqueado e pronto."""
        payload = self.execute_js("""(() => {
            if (!globalThis.Game || !Game.Objects) {
                return {available: false, unlocked: false, message: 'Runtime do jogo indisponível'};
            }
            const bank = Game.Objects['Bank'];
            if (!bank) {
                return {available: false, unlocked: false, message: 'Prédio Banco indisponível'};
            }
            const unlocked = Number(bank.level || 0) > 0;
            if (!unlocked) {
                return {available: false, unlocked: false, message: 'Stock Market ainda não foi desbloqueado'};
            }
            const M = bank.minigame;
            const ready = !!bank.minigameLoaded && !!M && Array.isArray(M.goodsById)
                && typeof M.buyGood === 'function' && typeof M.sellGood === 'function';
            return {
                available: ready,
                unlocked: true,
                message: ready ? 'Stock Market disponível' : 'Stock Market desbloqueado, mas ainda não carregado'
            };
        })()""")
        return self._parse_stock_status(payload)

    def get_garden_snapshot(self) -> GardenSnapshot:
        """Obtém um snapshot defensivo do Garden em uma única avaliação."""
        payload = self.execute_js("""(() => {
            const unavailable = (unlocked, message) => ({
                status:{available:false, unlocked:!!unlocked, message}
            });
            if (!globalThis.Game || !Game.Objects) {
                return unavailable(false, 'Runtime do jogo indisponível');
            }
            const farm = Game.Objects['Farm'];
            if (!farm) return unavailable(false, 'Prédio Fazenda indisponível');
            const unlocked = Number(farm.level || 0) > 0;
            if (!unlocked) return unavailable(false, 'Garden ainda não foi desbloqueado');
            const M = farm.minigame;
            const ready = !!farm.minigameLoaded && !!M
                && Array.isArray(M.plantsById) && Array.isArray(M.soilsById)
                && Array.isArray(M.plot) && typeof M.isTileUnlocked === 'function';
            if (!ready) return unavailable(true, 'Garden desbloqueado, mas ainda não carregado');
            const finiteOrNull = value => Number.isFinite(Number(value)) ? Number(value) : null;
            const unlockedTiles = [];
            const plants = [];
            for (let y=0; y<6; y++) for (let x=0; x<6; x++) {
                if (!M.isTileUnlocked(x,y)) continue;
                unlockedTiles.push([x,y]);
                const tile = M.plot[y] && M.plot[y][x];
                if (!Array.isArray(tile) || Number(tile[0]) < 1) continue;
                const seed = M.plantsById[Number(tile[0])-1];
                if (!seed) continue;
                const age = Number(tile[1]);
                const matureAge = Number(seed.mature);
                plants.push({
                    x,y, seedId:Number(seed.id), key:String(seed.key || ''),
                    name:String(seed.name || seed.key || ''), age:finiteOrNull(age),
                    matureAge:finiteOrNull(matureAge),
                    mature:Number.isFinite(age) && Number.isFinite(matureAge) && age>=matureAge,
                    weed:!!seed.weed, fungus:!!seed.fungus, immortal:!!seed.immortal
                });
            }
            const xs=unlockedTiles.map(tile=>tile[0]), ys=unlockedTiles.map(tile=>tile[1]);
            const currentSoil=M.soilsById[Number(M.soil)];
            const achievementName='Green, aching thumb';
            const achievement=Game.Achievements && Game.Achievements[achievementName];
            let greenAchingThumbWon=null;
            let greenAchingThumbMessage='Conquista indisponível no runtime';
            if (typeof Game.HasAchiev==='function') {
                try {
                    greenAchingThumbWon=!!Game.HasAchiev(achievementName);
                    greenAchingThumbMessage='Conquista confirmada por Game.HasAchiev';
                } catch (error) {
                    greenAchingThumbMessage='Não foi possível consultar a conquista no runtime';
                }
            } else if (achievement && (achievement.won===0 || achievement.won===1 || typeof achievement.won==='boolean')) {
                greenAchingThumbWon=!!achievement.won;
                greenAchingThumbMessage='Conquista confirmada pelo registro de achievements';
            }
            const rawHarvests=Number(M.harvests);
            const greenAchingThumbProgress=Number.isFinite(rawHarvests) && rawHarvests>=0
                ? Math.trunc(rawHarvests) : null;
            return {
                status:{available:true, unlocked:true, message:'Garden disponível'},
                farmLevel:Math.max(0,Math.trunc(Number(farm.level)||0)),
                farmAmount:Math.max(0,Math.trunc(Number(farm.amount)||0)),
                soilKey:currentSoil ? String(currentSoil.key || '') : null,
                soilName:currentSoil ? String(currentSoil.name || currentSoil.key || '') : null,
                frozen:!!M.freeze,
                nextTickAt:finiteOrNull(M.nextStep), tickSeconds:finiteOrNull(M.stepT),
                nextSoilAt:finiteOrNull(M.nextSoil),
                gameSeed:typeof Game.seed === 'string' ? Game.seed : null,
                gameVersion:Game.version === undefined ? null : String(Game.version),
                greenAchingThumbWon,
                greenAchingThumbProgress,
                greenAchingThumbMessage,
                plotWidth:xs.length ? Math.max(...xs)-Math.min(...xs)+1 : 0,
                plotHeight:ys.length ? Math.max(...ys)-Math.min(...ys)+1 : 0,
                unlockedTiles,
                cookies:finiteOrNull(Game.cookies),
                seeds:M.plantsById.map(seed=>({
                    id:Number(seed.id), key:String(seed.key || ''),
                    name:String(seed.name || seed.key || ''), unlocked:!!seed.unlocked,
                    plantable:seed.plantable !== false, matureAge:finiteOrNull(seed.mature),
                    cost:typeof M.getCost==='function' ? finiteOrNull(M.getCost(seed)) : null,
                    weed:!!seed.weed, fungus:!!seed.fungus, immortal:!!seed.immortal
                })),
                plants,
                soils:M.soilsById.map(soil=>({
                    id:Number(soil.id), key:String(soil.key || ''),
                    name:String(soil.name || soil.key || ''),
                    requiredFarms:Math.max(0,Math.trunc(Number(soil.req)||0)),
                    tickMinutes:finiteOrNull(soil.tick),
                    available:Number(farm.amount||0)>=Number(soil.req||0)
                }))
            };
        })()""")
        return self._parse_garden_snapshot(payload)

    def plant_garden_seed(self, seed_key: str, x: int, y: int) -> GardenActionResult:
        """Planta uma semente desbloqueada somente em um canteiro vazio."""
        if not self._valid_garden_key(seed_key) or not self._valid_garden_position(x, y):
            return GardenActionResult(False, "plant", "Parâmetros de plantio inválidos.", x=x, y=y)
        payload = self.execute_js("""(() => {
            const key=%s, x=%d, y=%d;
            const fail=(message,extra={})=>Object.assign({ok:false,message,x,y,seedKey:key},extra);
            const farm=globalThis.Game && Game.Objects ? Game.Objects['Farm'] : null;
            const M=farm && farm.minigameLoaded ? farm.minigame : null;
            if (!M || !Array.isArray(M.plot) || typeof M.useTool!=='function')
                return fail('Garden indisponível ou API incompatível');
            if (M.freeze) return fail('Garden está congelado');
            if (!M.isTileUnlocked(x,y)) return fail('Canteiro bloqueado');
            const seed=M.plants && M.plants[key];
            if (!seed) return fail('Semente inexistente');
            if (!seed.unlocked) return fail('Semente ainda não desbloqueada');
            if (seed.plantable===false) return fail('Esta semente não pode ser plantada');
            if (!Array.isArray(M.plot[y][x]) || Number(M.plot[y][x][0])!==0)
                return fail('Canteiro ocupado; nenhuma planta foi substituída');
            const cost=typeof M.getCost==='function' ? Number(M.getCost(seed)) : NaN;
            const cookies=Number(Game.cookies);
            if (!Number.isFinite(cost) || cost<0 || !Number.isFinite(cookies))
                return fail('Não foi possível conferir o custo do plantio');
            if (cookies<cost) return fail('Aguardando dinheiro para plantar',
                {waiting:true,reason:'insufficient_funds',requiredCookies:cost,availableCookies:cookies});
            if (typeof M.canPlant==='function' && !M.canPlant(seed))
                return fail('Plantio recusado pelo jogo');
            let accepted=false;
            try { accepted=M.useTool(Number(seed.id),x,y)===true; }
            catch (error) { return fail(`Falha ao plantar: ${error && error.message ? error.message : error}`); }
            const tile=M.plot[y][x];
            const after=Array.isArray(tile) && Number(tile[0])>0
                ? M.plantsById[Number(tile[0])-1] : null;
            const ok=accepted && after && after.key===key;
            return {ok,message:ok?'Semente plantada e verificada':'O jogo não confirmou o plantio',
                x,y,seedKey:key,beforeKey:null,afterKey:after?String(after.key):null};
        })()""" % (json.dumps(seed_key), x, y))
        return self._parse_garden_action(payload, "plant", x=x, y=y, seed_key=seed_key)

    def execute_garden_layout(self, actions) -> tuple[GardenActionResult, ...]:
        """Confere o lote inteiro antes de limpar; executa sem intercalar outras farms."""
        if not isinstance(actions, (list, tuple)) or not 1 <= len(actions) <= 72:
            return (GardenActionResult(False, "layout", "Lote de Garden inválido."),)
        payload_actions = []
        seen = set()
        for action in actions:
            if (not isinstance(action, GardenAction) or action.kind not in {"plant", "harvest"}
                    or (action.kind == "harvest" and action.require_mature)
                    or not self._valid_garden_key(action.seed_key)
                    or not self._valid_garden_position(action.x, action.y)
                    or (action.kind, action.x, action.y) in seen):
                return (GardenActionResult(False, "layout", "Ação de layout inválida."),)
            seen.add((action.kind, action.x, action.y))
            payload_actions.append(dict(kind=action.kind, x=action.x, y=action.y, seedKey=action.seed_key))
        script = """(() => {
            const actions=__ACTIONS__, results=[];
            const fail=(message,extra={})=>results.concat([Object.assign({ok:false,action:'layout',message},extra)]);
            if (!globalThis.Game || Game.OnAscend || Game.AscendTimer || Game.ReincarnateTimer)
                return fail('Jogo indisponível ou em transição');
            const farm=Game.Objects && Game.Objects.Farm;
            const M=farm && farm.minigameLoaded ? farm.minigame : null;
            if (!M || !Array.isArray(M.plot) || typeof M.getCost!=='function' ||
                    typeof M.useTool!=='function' || typeof M.harvest!=='function')
                return fail('Garden indisponível ou API incompatível');
            const plantings=actions.filter(a=>a.kind==='plant');
            if (plantings.length && M.freeze) return fail('Garden está congelado');
            const removals=new Map(actions.filter(a=>a.kind==='harvest').map(a=>[a.x+','+a.y,a]));
            const plantAt=(x,y)=>{
                const tile=M.plot[y] && M.plot[y][x];
                return Array.isArray(tile) && Number(tile[0])>0 ? M.plantsById[Number(tile[0])-1] : null;
            };
            // Valida também o estado dos canteiros antes de remover a primeira planta.
            let required=0;
            for (const a of actions) {
                if (!M.isTileUnlocked(a.x,a.y) || !Array.isArray(M.plot[a.y] && M.plot[a.y][a.x]))
                    return fail('Canteiro bloqueado ou inválido');
                const current=plantAt(a.x,a.y), removal=removals.get(a.x+','+a.y);
                if (a.kind==='harvest') {
                    if (!current || current.key!==a.seedKey) return fail('O canteiro mudou; replanejar antes de remover');
                } else {
                    const seed=M.plants && M.plants[a.seedKey];
                    if (!seed || !seed.unlocked || seed.plantable===false)
                        return fail('Semente indisponível; nenhuma planta foi removida');
                    if (current && (!removal || removal.seedKey!==current.key))
                        return fail('Canteiro ocupado por planta não prevista para remoção');
                    const cost=M.getCost(seed);
                    if (!Number.isFinite(cost) || cost<0) return fail('Custo de semente inválido; layout preservado');
                    required+=cost;
                }
            }
            const available=Number(Game.cookies);
            if (!Number.isFinite(required) || !Number.isFinite(available) || available<0)
                return fail('Orçamento indisponível; layout preservado');
            if (available<required) return fail('Aguardando dinheiro para completar o layout; plantas preservadas',
                {waiting:true,reason:'insufficient_funds',requiredCookies:required,availableCookies:available});
            // O custo nativo usa o CpS deste frame. Nenhuma outra automação roda entre
            // esta validação, as remoções e os plantios. Nunca antecipamos receita de colheita.
            const ordered=actions.filter(a=>a.kind==='harvest').concat(plantings);
            for (const a of ordered) {
                try {
                    if (a.kind==='harvest') {
                        const current=plantAt(a.x,a.y);
                        if (!current || current.key!==a.seedKey) return fail('Planta mudou durante a limpeza; lote interrompido');
                        if (M.harvest(a.x,a.y,1)!==true || (plantAt(a.x,a.y) && plantAt(a.x,a.y).key===a.seedKey))
                            return fail('A remoção não foi confirmada; lote interrompido para preservar o canteiro');
                    } else {
                        const seed=M.plants[a.seedKey];
                        if (plantAt(a.x,a.y)) return fail('Canteiro ocupado; plantio cancelado');
                        const cost=M.getCost(seed);
                        if (!Number.isFinite(cost) || cost<0) return fail('Custo mudou para um valor inválido');
                        if (Number(Game.cookies)<cost) return fail('Aguardando dinheiro; custo mudou durante o lote',
                            {waiting:true,reason:'insufficient_funds',requiredCookies:cost,availableCookies:Number(Game.cookies)});
                        if (M.useTool(Number(seed.id),a.x,a.y)!==true ||
                                !plantAt(a.x,a.y) || plantAt(a.x,a.y).key!==a.seedKey)
                            return fail('O jogo não confirmou o plantio; lote interrompido');
                        M.toCompute=true;
                    }
                    results.push({ok:true,action:a.kind,x:a.x,y:a.y,seedKey:a.seedKey,
                        message:a.kind==='plant'?'Semente plantada e verificada':'Remoção confirmada para o novo layout'});
                } catch (error) { return fail('Falha no layout: '+String(error && error.message || error)); }
            }
            return results;
        })()""".replace("__ACTIONS__", json.dumps(payload_actions))
        payload = self.execute_js(script)
        if not isinstance(payload, list) or not payload or any(not isinstance(item, dict) for item in payload):
            return (GardenActionResult(False, "layout", "Resposta inválida do lote de Garden."),)
        return tuple(self._parse_garden_action(
            item, str(item.get("action") or "layout"),
            x=self._optional_int(item.get("x")), y=self._optional_int(item.get("y")),
        ) for item in payload)

    def harvest_garden_tile(
        self, x: int, y: int, *, expected_key: Optional[str] = None,
        require_mature: bool = True,
    ) -> GardenActionResult:
        """Colhe uma planta esperada, opcionalmente exigindo maturidade."""
        if (expected_key is not None and not self._valid_garden_key(expected_key)):
            return GardenActionResult(False, "harvest", "Semente esperada inválida.", x=x, y=y)
        if not self._valid_garden_position(x, y) or not isinstance(require_mature, bool):
            return GardenActionResult(False, "harvest", "Parâmetros de colheita inválidos.", x=x, y=y)
        payload = self.execute_js("""(() => {
            const x=%d,y=%d,expected=%s,requireMature=%s;
            const fail=(message,extra={})=>Object.assign({ok:false,message,x,y,seedKey:expected},extra);
            const farm=globalThis.Game && Game.Objects ? Game.Objects['Farm'] : null;
            const M=farm && farm.minigameLoaded ? farm.minigame : null;
            if (!M || !Array.isArray(M.plot) || typeof M.harvest!=='function')
                return fail('Garden indisponível ou API incompatível');
            if (!M.isTileUnlocked(x,y)) return fail('Canteiro bloqueado');
            const tile=M.plot[y] && M.plot[y][x];
            const before=Array.isArray(tile) && Number(tile[0])>0 ? M.plantsById[Number(tile[0])-1] : null;
            if (!before) return fail('Canteiro vazio');
            const beforeKey=String(before.key||'');
            if (expected!==null && beforeKey!==expected)
                return fail('Planta divergente; colheita cancelada',{beforeKey});
            if (requireMature && Number(tile[1])<Number(before.mature))
                return fail('Planta ainda não está madura',{beforeKey});
            let accepted=false;
            try { accepted=M.harvest(x,y,1)===true; }
            catch (error) { return fail(`Falha ao colher: ${error && error.message ? error.message : error}`,{beforeKey}); }
            const afterTile=M.plot[y][x];
            const after=Array.isArray(afterTile) && Number(afterTile[0])>0
                ? M.plantsById[Number(afterTile[0])-1] : null;
            const afterKey=after?String(after.key||''):null;
            const unlocked=before && !!before.unlocked;
            const ok=accepted && afterKey!==beforeKey;
            return {ok,message:ok
                ? (unlocked?'Planta colhida e semente confirmada':'Planta colhida; semente ainda não confirmada')
                :'O jogo não confirmou a colheita',x,y,seedKey:beforeKey,beforeKey,afterKey};
        })()""" % (x, y, json.dumps(expected_key), "true" if require_mature else "false"))
        return self._parse_garden_action(payload, "harvest", x=x, y=y, seed_key=expected_key)

    def change_garden_soil(self, soil_key: str) -> GardenActionResult:
        """Troca o solo somente quando o requisito e o cooldown permitem."""
        if not self._valid_garden_key(soil_key):
            return GardenActionResult(False, "change_soil", "Solo inválido.", soil_key=soil_key)
        payload = self.execute_js("""(() => {
            const key=%s;
            const fail=message=>({ok:false,message,soilKey:key});
            const farm=globalThis.Game && Game.Objects ? Game.Objects['Farm'] : null;
            const M=farm && farm.minigameLoaded ? farm.minigame : null;
            if (!M || !M.soils || typeof M.computeStepT!=='function')
                return fail('Garden indisponível ou API de solo incompatível');
            const soil=M.soils[key];
            if (!soil) return fail('Solo inexistente');
            if (M.freeze) return fail('Descongele o Garden antes de trocar o solo');
            if (Number(M.soil)===Number(soil.id)) return {ok:true,message:'Solo já estava selecionado',soilKey:key};
            if (Number(M.nextSoil)>Date.now()) return fail('Troca de solo ainda está em cooldown');
            if (Number(farm.amount||0)<Number(soil.req||0)) return fail('Quantidade de Fazendas insuficiente para este solo');
            M.nextSoil=Date.now()+(typeof Game.Has==='function' && Game.Has('Turbo-charged soil')?1:600000);
            M.toCompute=true; M.soil=Number(soil.id); M.computeStepT();
            const ok=Number(M.soil)===Number(soil.id);
            return {ok,message:ok?'Solo alterado e verificado':'O jogo não confirmou a troca de solo',soilKey:key};
        })()""" % json.dumps(soil_key))
        return self._parse_garden_action(payload, "change_soil", soil_key=soil_key)

    def set_garden_frozen(self, frozen: bool) -> GardenActionResult:
        """Congela ou descongela o Garden e verifica o estado resultante."""
        if not isinstance(frozen, bool):
            return GardenActionResult(False, "set_freeze", "Estado de congelamento inválido.")
        payload = self.execute_js("""(() => {
            const desired=%s;
            const fail=message=>({ok:false,message});
            const farm=globalThis.Game && Game.Objects ? Game.Objects['Farm'] : null;
            const M=farm && farm.minigameLoaded ? farm.minigame : null;
            if (!M) return fail('Garden indisponível');
            if (!!M.freeze===desired) return {ok:true,message:desired?'Garden já estava congelado':'Garden já estava descongelado'};
            // A Fazendeira só solicita descongelamento automático. Congelar pode
            // matar Cheapcaps e, portanto, permanece uma operação explícita.
            if (desired) return fail('Congelamento automático bloqueado por segurança');
            M.freeze=0;
            if (typeof M.computeEffs==='function') M.computeEffs();
            const ok=!M.freeze;
            return {ok,message:ok?'Garden descongelado e verificado':'O jogo não confirmou o descongelamento'};
        })()""" % ("true" if frozen else "false"))
        return self._parse_garden_action(payload, "set_freeze")

    def get_stock_market_snapshot(self) -> StockMarketSnapshot:
        """Obtém recursos e ativos do mercado em uma única leitura consistente."""
        payload = self.execute_js("""(() => {
            if (!globalThis.Game || !Game.Objects) {
                return {status:{available:false,unlocked:false,message:'Runtime do jogo indisponível'}};
            }
            const bank = Game.Objects['Bank'];
            if (!bank) {
                return {status:{available:false,unlocked:false,message:'Prédio Banco indisponível'}};
            }
            const unlocked = Number(bank.level || 0) > 0;
            if (!unlocked) {
                return {status:{available:false,unlocked:false,message:'Stock Market ainda não foi desbloqueado'}};
            }
            const M = bank.minigame;
            const ready = !!bank.minigameLoaded && !!M && Array.isArray(M.goodsById)
                && typeof M.getGoodPrice === 'function' && typeof M.getGoodMaxStock === 'function'
                && typeof M.buyGood === 'function' && typeof M.sellGood === 'function';
            if (!ready) {
                return {status:{available:false,unlocked:true,message:'Stock Market desbloqueado, mas ainda não carregado'}};
            }
            const highestCps = Number(Game.cookiesPsRawHighest);
            const cookies = Number(Game.cookies);
            const brokers = Math.max(0, Math.trunc(Number(M.brokers) || 0));
            const overhead = 1 + 0.01 * (20 * Math.pow(0.95, brokers));
            const bankLevel = Math.max(0, Math.trunc(Number(bank.level) || 0));
            const finiteOrNull = value => Number.isFinite(Number(value)) ? Number(value) : null;
            return {
                status:{available:true,unlocked:true,message:'Stock Market disponível'},
                cookies: finiteOrNull(cookies),
                highestRawCps: finiteOrNull(highestCps),
                tradingFunds: highestCps > 0 ? finiteOrNull(cookies / highestCps) : null,
                brokers: brokers,
                brokerOverhead: finiteOrNull(overhead),
                profit: finiteOrNull(M.profit),
                tick: Math.max(0, Math.trunc(Number(M.ticks) || 0)),
                tickProgress: Math.max(0, Math.trunc(Number(M.tickT) || 0)),
                secondsPerTick: finiteOrNull(M.secondsPerTick),
                gameSeed: typeof Game.seed === 'string' ? Game.seed : null,
                bankLevel: bankLevel,
                gaseousAssetsWon: typeof Game.HasAchiev === 'function'
                    ? !!Game.HasAchiev('Gaseous assets') : false,
                assets: M.goodsById.map(good => ({
                    id: Number(good.id),
                    name: typeof good.name === 'string'
                        ? good.name.replace('%1', String(Game.bakeryName || 'You')) : `Ativo ${good.id}`,
                    symbol: typeof good.symbol === 'string' ? good.symbol : null,
                    price: finiteOrNull(M.getGoodPrice(good)),
                    priceChangePercent: typeof M.goodDelta === 'function'
                        ? finiteOrNull(M.goodDelta(Number(good.id))) : null,
                    lastBoughtPrice: finiteOrNull(good.prev),
                    priceHistory: Array.isArray(good.vals)
                        ? good.vals.slice(0, 180).map(finiteOrNull).filter(value => value !== null)
                        : [],
                    owned: Math.max(0, Math.trunc(Number(good.stock) || 0)),
                    capacity: finiteOrNull(M.getGoodMaxStock(good)),
                    restingValue: finiteOrNull(typeof M.getRestingVal === 'function'
                        ? M.getRestingVal(Number(good.id)) : 10 + 10 * Number(good.id) + bankLevel - 1)
                }))
            };
        })()""")
        return self._parse_stock_snapshot(payload)

    def buy_stock(self, asset_id: int, quantity: int) -> StockTradeResult:
        """Compra exatamente a quantidade solicitada, se a ordem for aceita."""
        return self._trade_stock("buy", asset_id, quantity)

    def sell_stock(self, asset_id: int, quantity: int) -> StockTradeResult:
        """Vende exatamente a quantidade solicitada, se a ordem for aceita."""
        return self._trade_stock("sell", asset_id, quantity)

    def buy_stock_max(self, asset_id: int, *, price_limit: Optional[float] = None,
                      require_empty: bool = False) -> StockTradeResult:
        """Compra o máximo aceito pelo runtime do jogo para o ativo."""
        return self._trade_stock(
            "buy", asset_id, GAME_MAXIMUM_ORDER_SENTINEL, is_maximum_order=True,
            price_limit=price_limit, require_empty=require_empty,
        )

    def sell_stock_max(self, asset_id: int, *, minimum_price: Optional[float] = None,
                       expected_purchase_price: Optional[float] = None) -> StockTradeResult:
        """Vende todo o estoque possuído do ativo pelo comando nativo do jogo."""
        return self._trade_stock(
            "sell", asset_id, GAME_MAXIMUM_ORDER_SENTINEL, is_maximum_order=True,
            minimum_price=minimum_price, expected_purchase_price=expected_purchase_price,
        )

    def _trade_stock(self, side: str, asset_id: int, quantity: int,
                     is_maximum_order: bool = False, *, price_limit: Optional[float] = None,
                     require_empty: bool = False, minimum_price: Optional[float] = None,
                     expected_purchase_price: Optional[float] = None) -> StockTradeResult:
        """Valida e executa uma ordem usando exclusivamente a API JS do minigame."""
        if side not in {"buy", "sell"}:
            raise ValueError("Lado da ordem inválido")
        if (isinstance(asset_id, bool) or not isinstance(asset_id, int)
                or not 0 <= asset_id <= MAX_STOCK_ASSET_ID):
            return self._invalid_trade(side, asset_id, quantity, "Identificador de ativo inválido")
        if (isinstance(quantity, bool) or not isinstance(quantity, int)
                or not 1 <= quantity <= MAX_STOCK_TRADE_QUANTITY):
            return self._invalid_trade(side, asset_id, quantity, "Quantidade deve estar entre 1 e 1.000.000.000")
        if not is_maximum_order and quantity == GAME_MAXIMUM_ORDER_SENTINEL:
            return self._invalid_trade(side, asset_id, quantity, "Use a ordem máxima para a quantidade 10.000")
        guards = {
            "priceLimit": price_limit,
            "minimumPrice": minimum_price,
            "expectedPurchasePrice": expected_purchase_price,
        }
        for key, value in guards.items():
            if value is not None:
                parsed = self._optional_float(value)
                if (not isinstance(value, (int, float)) or parsed is None or parsed <= 0):
                    return self._invalid_trade(side, asset_id, quantity, "Limite de preço inválido")
                guards[key] = parsed
        if not isinstance(require_empty, bool):
            return self._invalid_trade(side, asset_id, quantity, "Validação de estoque inválida")
        guards["requireEmpty"] = require_empty

        script = """(() => {
            const side = '%s', assetId = %d, quantity = %d, isMaximum = %s;
            const guards = %s;
            const fail = (message, extra = {}) => Object.assign({ok:false,message}, extra);
            if (!globalThis.Game || !Game.Objects) return fail('Runtime do jogo indisponível');
            const bank = Game.Objects['Bank'];
            if (!bank || Number(bank.level || 0) <= 0) return fail('Stock Market não está desbloqueado');
            const M = bank.minigame;
            if (!bank.minigameLoaded || !M || !Array.isArray(M.goodsById)) return fail('Stock Market não está carregado');
            const operation = side === 'buy' ? M.buyGood : M.sellGood;
            if (typeof operation !== 'function' || typeof M.getGoodPrice !== 'function') return fail('API de trading incompatível');
            const good = M.goodsById.find(item => Number(item && item.id) === assetId);
            if (!good) return fail('Ativo inexistente');
            const before = Math.max(0, Math.trunc(Number(good.stock) || 0));
            const price = Number(M.getGoodPrice(good));
            if (!Number.isFinite(price) || price < 0) return fail('Preço do ativo inválido', {before});
            if (side === 'buy' && guards.requireEmpty && before !== 0)
                return fail('Compra bloqueada: o ativo já possui estoque', {before,price});
            if (side === 'buy' && guards.priceLimit !== null && price >= guards.priceLimit)
                return fail('Compra bloqueada: preço atual atingiu o limite', {before,price});
            if (side === 'sell' && guards.expectedPurchasePrice !== null
                    && Number(good.prev) !== guards.expectedPurchasePrice)
                return fail('Venda bloqueada: o preço de compra mudou; reavaliando a posição', {before,price});
            if (side === 'sell' && guards.minimumPrice !== null && price <= guards.minimumPrice)
                return fail('Venda bloqueada: preço atual não garante lucro sobre o custo', {before,price});
            const capacity = typeof M.getGoodMaxStock === 'function' ? Math.max(0, Math.trunc(Number(M.getGoodMaxStock(good)) || 0)) : null;
            if (!isMaximum && side === 'buy' && capacity !== null && quantity > capacity - before) return fail('Quantidade excede a capacidade disponível', {before,price});
            if (!isMaximum && side === 'sell' && quantity > before) return fail('Quantidade excede o estoque possuído', {before,price});
            const cps = Number(Game.cookiesPsRawHighest);
            const brokers = Math.max(0, Math.trunc(Number(M.brokers) || 0));
            const overhead = 1 + 0.01 * (20 * Math.pow(0.95, brokers));
            const total = price * quantity * (side === 'buy' ? overhead : 1);
            if (!isMaximum && side === 'buy' && (!Number.isFinite(cps) || cps <= 0 || Number(Game.cookies) < total * cps)) return fail('Cookies insuficientes para a compra', {before,price,total});
            let accepted = false;
            try { accepted = operation.call(M, assetId, quantity) === true; }
            catch (error) { return fail(`Erro da API de trading: ${error && error.message ? error.message : error}`, {before,price,total}); }
            const after = Math.max(0, Math.trunc(Number(good.stock) || 0));
            const executed = side === 'buy' ? after - before : before - after;
            if (!accepted || (isMaximum ? executed <= 0 : executed !== quantity)) return fail(accepted ? 'Quantidade executada divergiu da solicitada' : 'Ordem recusada pelo jogo (aguarde o próximo tick)', {before,after,executed,price,total});
            const action = side === 'buy' ? 'Compra' : 'Venda';
            const executedTotal = price * executed * (side === 'buy' ? overhead : 1);
            return {ok:true,message:isMaximum ? `${action} máxima executada` : `${action} executada`,before,after,executed,price,total:executedTotal};
        })()""" % (side, asset_id, quantity, str(is_maximum_order).lower(), json.dumps(guards, allow_nan=False))
        payload = self.execute_js(script)
        if not isinstance(payload, dict):
            message = "Bridge desconectado ou resposta inválida do CDP"
            logger.error(f"Stock Market: {message}")
            return StockTradeResult(False, side, asset_id, quantity, 0, message)

        result = StockTradeResult(
            success=payload.get("ok") is True,
            side=side,
            asset_id=asset_id,
            requested_quantity=quantity,
            executed_quantity=self._safe_int(payload.get("executed"), 0),
            message=str(payload.get("message") or "Resposta inválida da operação"),
            stock_before=self._optional_int(payload.get("before")),
            stock_after=self._optional_int(payload.get("after")),
            unit_price=self._optional_float(payload.get("price")),
            total_value=self._optional_float(payload.get("total")),
            is_maximum_order=is_maximum_order,
        )
        log = logger.debug if result.success else logger.warning
        log(f"Stock Market: {result.message} (lado={side}, ativo={asset_id}, quantidade={quantity}, executada={result.executed_quantity})")
        return result

    @staticmethod
    def _invalid_trade(side: str, asset_id: Any, quantity: Any, message: str) -> StockTradeResult:
        logger.warning(f"Stock Market: {message} (lado={side}, ativo={asset_id}, quantidade={quantity})")
        valid_asset_id = asset_id if isinstance(asset_id, int) and not isinstance(asset_id, bool) else -1
        valid_quantity = quantity if isinstance(quantity, int) and not isinstance(quantity, bool) else 0
        return StockTradeResult(False, side, valid_asset_id, valid_quantity, 0, message)

    def _parse_stock_status(self, payload: Any) -> StockMarketStatus:
        if not isinstance(payload, dict):
            return StockMarketStatus(False, False, "Bridge desconectado ou resposta inválida do CDP")
        return StockMarketStatus(
            available=payload.get("available") is True,
            unlocked=payload.get("unlocked") is True,
            message=str(payload.get("message") or "Estado do Stock Market desconhecido"),
        )

    def _parse_stock_snapshot(self, payload: Any) -> StockMarketSnapshot:
        if not isinstance(payload, dict):
            status = StockMarketStatus(False, False, "Bridge desconectado ou resposta inválida do CDP")
            logger.error(f"Stock Market: {status.message}")
            return StockMarketSnapshot(status=status)
        status = self._parse_stock_status(payload.get("status"))
        if not status.available:
            logger.warning(f"Stock Market: {status.message}")
            return StockMarketSnapshot(status=status)
        raw_assets = payload.get("assets")
        if not isinstance(raw_assets, list):
            status = StockMarketStatus(False, status.unlocked, "Lista de ativos inválida")
            logger.error("Stock Market: lista de ativos inválida recebida do runtime")
            return StockMarketSnapshot(status=status)
        assets = []
        try:
            for raw in raw_assets:
                if not isinstance(raw, dict):
                    raise ValueError("item não é um objeto")
                asset_id = self._safe_int(raw.get("id"))
                price = self._optional_float(raw.get("price"))
                if asset_id < 0 or price is None or price < 0:
                    raise ValueError("id ou preço inválido")
                assets.append(StockAsset(
                    asset_id=asset_id,
                    name=str(raw.get("name") or f"Ativo {asset_id}"),
                    symbol=str(raw["symbol"]) if raw.get("symbol") else None,
                    price=price,
                    owned=max(0, self._safe_int(raw.get("owned"))),
                    capacity=self._optional_int(raw.get("capacity")),
                    price_change_percent=self._optional_float(raw.get("priceChangePercent")),
                    last_bought_price=self._optional_float(raw.get("lastBoughtPrice")),
                    price_history=self._parse_price_history(raw.get("priceHistory")),
                    resting_value=self._optional_float(raw.get("restingValue")),
                ))
        except (TypeError, ValueError) as error:
            logger.error(f"Stock Market: ativo inválido na resposta: {error}")
            return StockMarketSnapshot(status=StockMarketStatus(False, True, "Dados de ativos inválidos"))
        return StockMarketSnapshot(
            status=status,
            cookies=self._optional_float(payload.get("cookies")),
            highest_raw_cps=self._optional_float(payload.get("highestRawCps")),
            trading_funds=self._optional_float(payload.get("tradingFunds")),
            brokers=self._optional_int(payload.get("brokers")),
            broker_overhead=self._optional_float(payload.get("brokerOverhead")),
            profit=self._optional_float(payload.get("profit")),
            tick=self._optional_int(payload.get("tick")),
            tick_progress=self._optional_int(payload.get("tickProgress")),
            seconds_per_tick=self._optional_float(payload.get("secondsPerTick")),
            game_seed=str(payload["gameSeed"]) if payload.get("gameSeed") else None,
            assets=tuple(assets),
            bank_level=self._optional_int(payload.get("bankLevel")),
            gaseous_assets_won=payload.get("gaseousAssetsWon") is True,
        )

    def _parse_garden_snapshot(self, payload: Any) -> GardenSnapshot:
        """Converte dados não confiáveis do JavaScript em modelos tipados."""
        if not isinstance(payload, dict):
            return GardenSnapshot(GardenStatus(False, False, "Resposta inválida da bridge do Garden"))
        raw_status = payload.get("status")
        if not isinstance(raw_status, dict):
            return GardenSnapshot(GardenStatus(False, False, "Estado inválido do Garden"))
        status = GardenStatus(
            bool(raw_status.get("available")), bool(raw_status.get("unlocked")),
            str(raw_status.get("message") or "Estado do Garden sem mensagem"),
        )
        if not status.available:
            return GardenSnapshot(status)

        seeds = []
        for raw in payload.get("seeds", ()):
            if not isinstance(raw, dict):
                continue
            seed_id = self._optional_int(raw.get("id"))
            mature_age = self._optional_float(raw.get("matureAge"))
            key = raw.get("key")
            if seed_id is None or mature_age is None or mature_age < 0 or not self._valid_garden_key(key):
                continue
            seeds.append(GardenSeed(
                seed_id, key, str(raw.get("name") or key), bool(raw.get("unlocked")),
                bool(raw.get("plantable", True)), mature_age, bool(raw.get("weed")),
                bool(raw.get("fungus")), bool(raw.get("immortal")),
                cost=self._optional_float(raw.get("cost")),
            ))
        if not seeds:
            return GardenSnapshot(GardenStatus(False, True, "Catálogo de sementes ausente ou inválido no runtime"))

        plants = []
        for raw in payload.get("plants", ()):
            if not isinstance(raw, dict):
                continue
            x, y = self._optional_int(raw.get("x")), self._optional_int(raw.get("y"))
            seed_id = self._optional_int(raw.get("seedId"))
            age = self._optional_float(raw.get("age"))
            mature_age = self._optional_float(raw.get("matureAge"))
            key = raw.get("key")
            if (x is None or y is None or not self._valid_garden_position(x, y)
                    or seed_id is None or age is None or mature_age is None
                    or not self._valid_garden_key(key)):
                continue
            plants.append(GardenPlant(
                x, y, seed_id, key, str(raw.get("name") or key), age, mature_age,
                bool(raw.get("mature")), bool(raw.get("weed")), bool(raw.get("fungus")),
                bool(raw.get("immortal")),
            ))

        soils = []
        for raw in payload.get("soils", ()):
            if not isinstance(raw, dict) or not self._valid_garden_key(raw.get("key")):
                continue
            soil_id = self._optional_int(raw.get("id"))
            required = self._optional_int(raw.get("requiredFarms"))
            tick = self._optional_float(raw.get("tickMinutes"))
            if soil_id is None or required is None or tick is None or tick <= 0:
                continue
            soils.append(GardenSoil(
                soil_id, raw["key"], str(raw.get("name") or raw["key"]), required,
                tick, bool(raw.get("available")),
            ))

        unlocked_tiles = []
        for raw in payload.get("unlockedTiles", ()):
            if not isinstance(raw, list) or len(raw) != 2:
                continue
            x, y = self._optional_int(raw[0]), self._optional_int(raw[1])
            if x is not None and y is not None and self._valid_garden_position(x, y):
                unlocked_tiles.append((x, y))

        return GardenSnapshot(
            status=status,
            cookies=self._optional_float(payload.get("cookies")),
            farm_level=self._optional_int(payload.get("farmLevel")),
            farm_amount=self._optional_int(payload.get("farmAmount")),
            soil_key=str(payload["soilKey"]) if self._valid_garden_key(payload.get("soilKey")) else None,
            soil_name=str(payload.get("soilName")) if payload.get("soilName") is not None else None,
            frozen=bool(payload.get("frozen")),
            next_tick_at=self._garden_timestamp(payload.get("nextTickAt")),
            tick_seconds=self._optional_float(payload.get("tickSeconds")),
            next_soil_at=self._garden_timestamp(payload.get("nextSoilAt")),
            game_seed=str(payload.get("gameSeed")) if payload.get("gameSeed") is not None else None,
            game_version=str(payload.get("gameVersion")) if payload.get("gameVersion") is not None else None,
            plot_width=self._optional_int(payload.get("plotWidth")) or 0,
            plot_height=self._optional_int(payload.get("plotHeight")) or 0,
            unlocked_tiles=tuple(sorted(set(unlocked_tiles), key=lambda pos: (pos[1], pos[0]))),
            seeds=tuple(sorted(seeds, key=lambda seed: seed.seed_id)),
            plants=tuple(sorted(plants, key=lambda plant: (plant.y, plant.x))),
            soils=tuple(sorted(soils, key=lambda soil: soil.soil_id)),
            green_aching_thumb_won=(
                payload.get("greenAchingThumbWon")
                if isinstance(payload.get("greenAchingThumbWon"), bool) else None
            ),
            green_aching_thumb_progress=self._optional_int(payload.get("greenAchingThumbProgress")),
            green_aching_thumb_message=str(
                payload.get("greenAchingThumbMessage")
                or "Estado da conquista Green, aching thumb indisponível no runtime."
            ),
        )

    @staticmethod
    def _parse_garden_action(
        payload: Any, action: str, *, x: Optional[int] = None, y: Optional[int] = None,
        seed_key: Optional[str] = None, soil_key: Optional[str] = None,
    ) -> GardenActionResult:
        if not isinstance(payload, dict):
            return GardenActionResult(
                False, action, "Resposta inválida ou bridge desconectada.",
                x=x, y=y, seed_key=seed_key, soil_key=soil_key,
            )
        runtime_seed = payload.get("seedKey") or seed_key
        runtime_soil = payload.get("soilKey") or soil_key
        return GardenActionResult(
            bool(payload.get("ok")), action,
            str(payload.get("message") or "Operação sem mensagem do runtime"),
            x=x, y=y,
            seed_key=str(runtime_seed) if runtime_seed else None,
            soil_key=str(runtime_soil) if runtime_soil else None,
            before_key=str(payload.get("beforeKey")) if payload.get("beforeKey") is not None else None,
            after_key=str(payload.get("afterKey")) if payload.get("afterKey") is not None else None,
            waiting=payload.get("waiting") is True,
            reason=str(payload.get("reason") or ""),
            required_cookies=CookieClickerBridge._optional_float(payload.get("requiredCookies")),
            available_cookies=CookieClickerBridge._optional_float(payload.get("availableCookies")),
        )

    @staticmethod
    def _valid_garden_key(value: Any) -> bool:
        return isinstance(value, str) and 1 <= len(value) <= 64 and value.replace("_", "").isalnum()

    @staticmethod
    def _valid_garden_position(x: Any, y: Any) -> bool:
        return (
            isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 5
            and isinstance(y, int) and not isinstance(y, bool) and 0 <= y <= 5
        )

    @staticmethod
    def _garden_timestamp(value: Any) -> Optional[float]:
        parsed = CookieClickerBridge._optional_float(value)
        if parsed is None:
            return None
        return parsed / 1000.0 if parsed > 10_000_000_000 else parsed

    @classmethod
    def _parse_ascension_snapshot(cls, payload: Any) -> SnapshotAscensao:
        """Converte dados do runtime sem propagar tipos ou números inválidos."""
        if not isinstance(payload, dict) or payload.get("available") is not True:
            message = payload.get("message") if isinstance(payload, dict) else None
            return SnapshotAscensao(
                False, "indisponivel",
                str(message or "Resposta inválida ou bridge desconectada."),
            )
        screen = str(payload.get("screen") or "indisponivel")
        if screen not in {"jogo", "ascensao", "transicao"}:
            return SnapshotAscensao(False, "indisponivel", "Tela informada pelo runtime é inválida.")

        heavenly = []
        for raw in payload.get("heavenly", ()):
            if not isinstance(raw, dict):
                continue
            upgrade_id = cls._optional_int(raw.get("id"))
            price = cls._optional_float(raw.get("price"))
            if upgrade_id is None or price is None or price < 0:
                continue
            heavenly.append(HeavenlyUpgrade(
                upgrade_id, str(raw.get("name") or upgrade_id), price,
                bool(raw.get("eligible")), str(raw.get("reason") or ""),
            ))

        normal = []
        for raw in payload.get("normal", ()):
            if not isinstance(raw, dict):
                continue
            upgrade_id = cls._optional_int(raw.get("id"))
            price = cls._optional_float(raw.get("price"))
            if upgrade_id is None or price is None or price < 0:
                continue
            normal.append(UpgradeNormal(
                upgrade_id, str(raw.get("name") or upgrade_id), price,
                bool(raw.get("eligible")), str(raw.get("reason") or ""),
            ))

        buildings = []
        for raw in payload.get("buildings", ()):
            if not isinstance(raw, dict):
                continue
            building_id = cls._optional_int(raw.get("id"))
            amount = cls._optional_int(raw.get("amount"))
            maximum = cls._optional_int(raw.get("maximum"))
            unit_price = cls._optional_float(raw.get("unitPrice"))
            if None in (building_id, amount, maximum, unit_price) or unit_price < 0:
                continue
            buildings.append(Construcao(
                building_id, str(raw.get("name") or building_id), amount,
                unit_price, maximum, bool(raw.get("unlocked")),
            ))

        number = lambda key: max(0.0, cls._optional_float(payload.get(key)) or 0.0)
        return SnapshotAscensao(
            disponivel=True,
            tela=screen,
            mensagem=str(payload.get("message") or "Estado disponível"),
            versao=str(payload["version"]) if payload.get("version") is not None else None,
            cookies=number("cookies"),
            cookies_por_segundo=number("cookiesPerSecond"),
            prestigio_atual=number("prestige"),
            ganho_prestigio=number("prestigeGain"),
            heavenly_chips=number("heavenlyChips"),
            ascend_timer=number("ascendTimer"),
            reincarnate_timer=number("reincarnateTimer"),
            compra_todos_disponivel=bool(payload.get("buyAllAvailable")),
            heavenly_upgrades=tuple(sorted(heavenly, key=lambda item: item.id)),
            upgrades_normais=tuple(sorted(normal, key=lambda item: item.id)),
            construcoes=tuple(sorted(buildings, key=lambda item: item.id)),
        )

    @classmethod
    def _parse_ascension_action(
        cls, payload: Any, action: str, target_id: Optional[int] = None,
    ) -> ResultadoAcaoAscensao:
        if not isinstance(payload, dict):
            return ResultadoAcaoAscensao(
                False, action, "Resposta inválida ou bridge desconectada.",
                id_alvo=target_id, motivo="invalid_response",
            )
        runtime_id = cls._optional_int(payload.get("id"))
        quantity = cls._optional_int(payload.get("quantity")) or 0
        return ResultadoAcaoAscensao(
            sucesso=payload.get("ok") is True,
            acao=action,
            mensagem=str(payload.get("message") or "Operação sem mensagem do runtime"),
            id_alvo=runtime_id if runtime_id is not None else target_id,
            quantidade_executada=quantity,
            antes=cls._optional_float(payload.get("before")),
            depois=cls._optional_float(payload.get("after")),
            motivo=str(payload.get("reason") or ""),
        )

    @staticmethod
    def _invalid_ascension_action(action: str, message: str) -> ResultadoAcaoAscensao:
        result = ResultadoAcaoAscensao(False, action, message, motivo="invalid_arguments")
        logger.warning(f"Auto Ascensão: {action} recusada antes do runtime — {message}")
        return result

    @staticmethod
    def _log_ascension_action(result: ResultadoAcaoAscensao) -> None:
        context = (
            f"ação={result.acao}, alvo={result.id_alvo}, "
            f"quantidade={result.quantidade_executada}, motivo={result.motivo or 'sem código'}"
        )
        if result.sucesso:
            logger.info(f"Auto Ascensão: {result.mensagem} ({context})")
        else:
            logger.warning(f"Auto Ascensão: {result.mensagem} ({context})")

    def set_stock_market_owned_only_view(self, enabled: bool) -> bool:
        """Controla os olhos nativos para exibir apenas ativos com estoque."""
        script = """(() => {
            const bank = globalThis.Game && Game.Objects && Game.Objects['Bank'];
            const M = bank && bank.minigame;
            if (!bank || !bank.minigameLoaded || !M || !Array.isArray(M.goodsById)) return false;
            if (typeof M.updateGoodStyle !== 'function') return false;
            const ownedOnly = %s;
            for (const good of M.goodsById) {
                if (!good) continue;
                good.hidden = ownedOnly ? Number(good.stock || 0) <= 0 : false;
                M.updateGoodStyle(good.id);
            }
            return true;
        })()""" % str(bool(enabled)).lower()
        result = self.execute_js(script)
        if result is not True:
            logger.warning("Stock Market: não foi possível atualizar a visualização dos ativos")
            return False
        return True

    @staticmethod
    def _safe_int(value: Any, default: int = -1) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        try:
            parsed_float = float(value)
            return int(parsed_float) if parsed_float.is_integer() else default
        except (TypeError, ValueError, OverflowError):
            return default

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        parsed = CookieClickerBridge._safe_int(value)
        return parsed if parsed >= 0 else None

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        if isinstance(value, bool):
            return None
        try:
            parsed = float(value)
            return parsed if parsed == parsed and abs(parsed) != float("inf") else None
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _parse_price_history(value: Any) -> tuple[float, ...]:
        if not isinstance(value, list):
            return tuple()
        return tuple(
            parsed for item in value
            if (parsed := CookieClickerBridge._optional_float(item)) is not None and parsed >= 0
        )

    def get_cookie_position(self) -> Optional[Dict[str, int]]:
        """Retorna a posição do cookie principal."""
        # Tentar diferentes formas de obter a posição
        # Primeiro, verificar se há propriedades diretas
        x = self.execute_js("Game.cookieX || Game.bigCookie?.x")
        y = self.execute_js("Game.cookieY || Game.bigCookie?.y")

        if x is not None and y is not None:
            return {"x": int(x), "y": int(y)}

        # Se não funcionar, tentar através do DOM
        pos = self.execute_js("""(() => {
            const cookie = document.getElementById('bigCookie');
            if (cookie) {
                const rect = cookie.getBoundingClientRect();
                return {x: Math.round(rect.left + rect.width/2), y: Math.round(rect.top + rect.height/2)};
            }
            return null;
        })()""")

        if pos:
            return pos

        logger.warning("Não foi possível obter a posição do cookie")
        return None

    def get_cps(self) -> Optional[float]:
        """Retorna cookies por segundo."""
        return self.execute_js("Game.cookiesPs")

    def get_sugar_lump_type(self) -> Optional[int]:
        """Retorna o tipo atual do Sugar Lump."""
        return self.execute_js("typeof Game.lumpCurrentType !== 'undefined' ? Game.lumpCurrentType : null")

    def get_sugar_lump_status(self) -> Optional[Dict[str, Any]]:
        """Retorna o estado atual do Sugar Lump."""
        return self.execute_js("""(() => {
            const lump = Array.isArray(Game.lumps) ? Game.lumps[0] : null;
            if (!lump) return null;
            return {
                type: typeof Game.lumpCurrentType !== 'undefined' ? Game.lumpCurrentType : lump.type,
                ready: !!lump.ready,
                progress: lump.progress || lump.value || 0,
                typeName: lump.typeName || null,
            };
        })()""")

    def harvest_sugar_lump(self) -> bool:
        """Tenta colher o Sugar Lump atual diretamente via JS."""
        script = """(() => {
            const lump = Array.isArray(Game.lumps) ? Game.lumps[0] : null;
            if (!lump) return false;

            if (typeof lump.pop === 'function') {
                lump.pop();
                return true;
            }

            if (typeof lump.click === 'function') {
                lump.click();
                return true;
            }

            const lumpElement = document.querySelector('#lumps');
            if (lumpElement) {
                lumpElement.click();
            }

            const button = Array.from(document.querySelectorAll('button')).find(
                el => /harvest|coletar|yes|sim/i.test(el.innerText)
            );
            if (button) {
                button.click();
                return true;
            }

            return false;
        })()"""
        result = self.execute_js(script)
        return bool(result)

    def get_golden_cookie(self) -> Optional[Dict]:
        """Retorna o shimmer do golden cookie se existir."""
        return self.execute_js("Game.shimmers.find(s => s.type === 'golden')")

    def get_reindeer(self) -> Optional[Dict]:
        """Retorna o shimmer da rena se existir."""
        return self.execute_js("Game.shimmers.find(s => s.type === 'reindeer')")

    def has_fortune_cookie(self) -> bool:
        """Verifica se há fortune cookie ativa."""
        result = self.execute_js("Game.TickerEffect && Game.TickerEffect.type === 'fortune'")
        return bool(result)

    def pop_golden_cookie(self) -> bool:
        """Coleta o golden cookie sem mover o mouse."""
        golden = self.get_golden_cookie()
        if not golden:
            return False
        
        # Confirma a remoção pelo id. Outros Golden Cookies podem continuar
        # em tela durante um Cookie Storm sem transformar o clique em falha.
        result = self.execute_js("""(() => {
            const gc = Game.shimmers.find(s => s.type === 'golden');
            if (!gc) return false;
            const id = Number(gc.id);
            gc.pop();
            return !Game.shimmers.some(s => s.type === 'golden' && Number(s.id) === id);
        })()""")
        
        if result:
            return True
        
        logger.info("[FAIL] Golden cookie detectado mas pop() falhou")
        return False

    def pop_reindeer(self) -> bool:
        """Coleta a rena sem mover o mouse."""
        reindeer = self.get_reindeer()
        if not reindeer:
            return False
        
        # Usar um script que verifica se o shimmer foi removido
        result = self.execute_js("""(() => {
            const rd = Game.shimmers.find(s => s.type === 'reindeer');
            if (!rd) return false;
            rd.pop();
            const rdAfter = Game.shimmers.find(s => s.type === 'reindeer');
            return !rdAfter;  // True se foi removido
        })()""")
        
        if result:
            return True
        
        # logger.info("[FAIL] Rena detectada mas pop() falhou")
        return False

    def get_wrinklers(self) -> Optional[List[Dict[str, Any]]]:
        """Retorna a lista de wrinklers com informação básica."""
        return self.execute_js("""(() => {
            if (!Game.wrinklers) return null;
            return Game.wrinklers.map((w, idx) => ({
                index: idx,
                type: w.type,
                hp: w.hp,
                maxHp: w.maxHp,
                isShiny: w.type === 1
            }));
        })()""")

    def pop_wrinkler_by_index(self, index: int) -> bool:
        """Popa um wrinkler específico pelo índice, preservando dourados/shiny."""
        script = """(() => {
            const i = %d;
            if (!Array.isArray(Game.wrinklers) || i < 0 || i >= Game.wrinklers.length) return false;
            const w = Game.wrinklers[i];
            if (!w || w.hp <= 0 || w.type === 1) return false;
            if (typeof w.pop === 'function') {
                w.pop();
            } else {
                w.hp = 0;
                if (typeof Game.recalculateWrinklers === 'function') {
                    Game.recalculateWrinklers();
                }
            }
            return true;
        })()""" % index
        result = self.execute_js(script)
        return bool(result)

    def click_fortune(self) -> bool:
        """Clica na fortune cookie."""
        if self.has_fortune_cookie():
            result = self.execute_js("""(() => {
                if (!Game.tickerL) return false;
                Game.tickerL.click();
                return true;
            })()""")
            if result is True:
                return True
        return False

    def poll_game_state(self) -> Dict[str, Any]:
        """
        Polling leve do estado do jogo para detecção de eventos.

        Returns:
            Dicionário com estado atual
        """
        return {
            'cps': self.get_cps(),
            'golden_cookie': self.get_golden_cookie() is not None,
            'fortune_cookie': self.has_fortune_cookie(),
        }

    # def get_game_save(self) -> Optional[str]:
    #     """Exporta o save atual do jogo."""
    #     return self.execute_js("Game.export()")

    # def load_game_save(self, save_data: str) -> bool:
    #     """Carrega um save no jogo."""
    #     # Escapar aspas na string do save
    #     escaped_save = save_data.replace('"', '\\"').replace("'", "\\'")
    #     script = f'Game.importSave("{escaped_save}")'
    #     result = self.execute_js(script)
    #     return result is not None
