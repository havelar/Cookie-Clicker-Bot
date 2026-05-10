"""
Bridge para comunicação com o runtime JavaScript do Cookie Clicker.
"""
import time
from typing import Optional, Any, Dict, List

try:
    import pychrome
except ImportError:
    raise ImportError("pychrome não encontrado. Instale com 'pip install pychrome'")

from app.config.settings import app_config
from app.utils.logger import logger


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

    def connect(self) -> bool:
        """
        Conecta ao remote debugging do CEF.

        Returns:
            True se conectado com sucesso, False caso contrário
        """
        try:
            self.browser = pychrome.Browser(url=f"http://{self.host}:{self.port}")
            tabs = self.browser.list_tab()
            if not tabs:
                logger.error("Nenhuma aba encontrada no remote debugging")
                return False

            # Assume a primeira aba é o jogo
            self.tab = tabs[0]
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
        if not self.connected or not self.tab:
            logger.warning("Bridge não conectado. Tentando reconectar...")
            if not self.connect():
                return None

        try:
            result = self.tab.Runtime.evaluate(expression=code, returnByValue=True)
            if 'result' in result and 'value' in result['result']:
                return result['result']['value']
            elif 'exceptionDetails' in result:
                logger.error(f"Erro JS: {result['exceptionDetails']}")
                return None
            else:
                return None
        except Exception as e:
            logger.error(f"Erro ao executar JS: {e}")
            self.connected = False  # Marcar como desconectado para tentar reconectar
            return None

    # === Helpers específicos do Cookie Clicker ===

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
        if golden:
            result = self.execute_js("Game.shimmers.find(s => s.type === 'golden').pop()")
            if result is not None:
                logger.info("Golden cookie coletado via JS")
                return True
        return False

    def pop_reindeer(self) -> bool:
        """Coleta a rena sem mover o mouse."""
        reindeer = self.get_reindeer()
        if reindeer:
            result = self.execute_js("Game.shimmers.find(s => s.type === 'reindeer').pop()")
            if result is not None:
                logger.info("Rena coletada via JS")
                return True
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

    def pop_normal_wrinkler(self) -> bool:
        """Popa o primeiro wrinkler normal, preservando dourados/shiny."""
        result = self.execute_js("""(() => {
            if (!Array.isArray(Game.wrinklers) || Game.wrinklers.length === 0) return false;
            for (let i = 0; i < Game.wrinklers.length; i++) {
                const w = Game.wrinklers[i];
                if (!w) continue;
                if (w.hp <= 0) continue;
                if (w.type === 1) continue;
                if (typeof w.pop === 'function') {
                    w.pop();
                } else {
                    w.hp = 0;
                    if (typeof Game.recalculateWrinklers === 'function') {
                        Game.recalculateWrinklers();
                    }
                }
                return true;
            }
            return false;
        })()""")
        return bool(result)

    def click_fortune(self) -> bool:
        """Clica na fortune cookie."""
        if self.has_fortune_cookie():
            result = self.execute_js("Game.tickerL.click()")
            if result is not None:
                logger.info("Fortune cookie clicada via JS")
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