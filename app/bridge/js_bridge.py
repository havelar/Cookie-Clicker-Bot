"""
Bridge para comunicação com o runtime JavaScript do Cookie Clicker.
"""
import time
import threading
from typing import Optional, Any, Dict, List

try:
    import pychrome
except ImportError:
    raise ImportError("pychrome não encontrado. Instale com 'pip install pychrome'")

from app.config.settings import app_config
from app.models.stock_market import (
    StockAsset,
    StockMarketSnapshot,
    StockMarketStatus,
    StockTradeResult,
)
from app.utils.logger import logger

MAX_STOCK_ASSET_ID = 10_000
MAX_STOCK_TRADE_QUANTITY = 1_000_000_000
GAME_MAXIMUM_ORDER_SENTINEL = 10_000


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
                assets: M.goodsById.map(good => ({
                    id: Number(good.id),
                    name: typeof good.name === 'string' ? good.name : `Ativo ${good.id}`,
                    symbol: typeof good.symbol === 'string' ? good.symbol : null,
                    price: finiteOrNull(M.getGoodPrice(good)),
                    priceChangePercent: typeof M.goodDelta === 'function'
                        ? finiteOrNull(M.goodDelta(Number(good.id))) : null,
                    lastBoughtPrice: finiteOrNull(good.prev),
                    priceHistory: Array.isArray(good.vals)
                        ? good.vals.slice(0, 180).map(finiteOrNull).filter(value => value !== null)
                        : [],
                    owned: Math.max(0, Math.trunc(Number(good.stock) || 0)),
                    capacity: finiteOrNull(M.getGoodMaxStock(good))
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

    def buy_stock_max(self, asset_id: int) -> StockTradeResult:
        """Compra o máximo aceito pelo runtime do jogo para o ativo."""
        return self._trade_stock("buy", asset_id, GAME_MAXIMUM_ORDER_SENTINEL, is_maximum_order=True)

    def sell_stock_max(self, asset_id: int) -> StockTradeResult:
        """Vende todo o estoque possuído do ativo pelo comando nativo do jogo."""
        return self._trade_stock("sell", asset_id, GAME_MAXIMUM_ORDER_SENTINEL, is_maximum_order=True)

    def _trade_stock(self, side: str, asset_id: int, quantity: int,
                     is_maximum_order: bool = False) -> StockTradeResult:
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

        script = """(() => {
            const side = '%s', assetId = %d, quantity = %d, isMaximum = %s;
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
        })()""" % (side, asset_id, quantity, str(is_maximum_order).lower())
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
        )

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
        
        # Usar um script que verifica se o shimmer foi removido
        result = self.execute_js("""(() => {
            const gc = Game.shimmers.find(s => s.type === 'golden');
            if (!gc) return false;
            gc.pop();
            const gcAfter = Game.shimmers.find(s => s.type === 'golden');
            return !gcAfter;  // True se foi removido
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
