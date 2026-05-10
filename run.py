from input import Input
from js_bridge import CookieClickerBridge
import time
import win32gui
import win32process
import threading
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def listar_janelas_cookie():
    janelas = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            titulo = win32gui.GetWindowText(hwnd)
            if "cookie" in titulo.lower():
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                janelas.append((hwnd, pid, titulo))
        return True

    win32gui.EnumWindows(callback, None)
    return janelas[0][1] if janelas else None


class Macro:
    """Define uma sequência de ações a serem executadas."""

    def __init__(self, commands):
        """
        commands: lista de tuplas (ação, parâmetros, delay)
        Exemplos:
            ("click_cookie", None, 0.01)
            ("check_golden", None, 0.1)
            ("check_fortune", None, 0.1)
            ("move", (100, 150), 0.01)
            ("send_key", ("SPACE",), 0.01)
        """
        self.commands = commands

    def execute(self, input_handler, bridge=None):
        """Executa todas as ações do macro."""
        for cmd, param, delay in self.commands:
            if cmd == "click_cookie":
                input_handler.click_cookie(bridge)
                logger.info("Clicou no cookie principal")
            elif cmd == "check_golden":
                if bridge and bridge.pop_golden_cookie():
                    logger.info("Golden cookie detectado e coletado")
            elif cmd == "check_fortune":
                if bridge and bridge.click_fortune():
                    logger.info("Fortune cookie detectada e clicada")
            elif cmd == "move":
                input_handler.move(*param)
                logger.info(f"Moved to {param}")
            elif cmd == "send_key":
                input_handler.send_key(param[0])
                logger.info(f"Key sent: {param[0]}")
            time.sleep(delay)


# Classe Macro mantida para compatibilidade futura, mas não usada na implementação atual


class Run:
    """Gerencia a execução do macro com controle de liga/desliga usando threads separadas."""

    def __init__(self, pid, bridge, toggle_key="SCROLLLOCK"):
        """
        pid: PID do processo
        bridge: instância de CookieClickerBridge
        toggle_key: tecla para ligar/desligar o macro
        """
        self.bridge = bridge
        self.toggle_key = toggle_key
        self.is_running = False
        self.stop_event = threading.Event()

        self.cookie_position = None
        self.input_handler = InputHandler(pid=pid, restore_game=False, cookie_position=None)

        # Threads separadas
        self.detector_thread = None
        self.clicker_thread = None

    def update_cookie_position(self) -> bool:
        """Atualiza a posição do cookie antes de iniciar o clique."""
        cookie_pos = self.bridge.get_cookie_position()
        if not cookie_pos:
            logger.error("Não foi possível obter a posição do cookie ao iniciar o macro")
            return False

        self.cookie_position = (cookie_pos['x'], cookie_pos['y'])
        self.input_handler.cookie_position = self.cookie_position
        logger.info(f"Posição do cookie atualizada: {self.cookie_position}")
        return True

    def toggle(self):
        """Liga ou desliga o macro."""
        if not self.is_running:
            if not self.update_cookie_position():
                return

        self.is_running = not self.is_running
        status = "INICIADO" if self.is_running else "PARADO"
        logger.info(f"Macro {status}!")

    def detector_loop(self):
        """Thread dedicada para detectar Golden Cookies e Fortunes."""
        logger.info("Thread detector iniciada. Pegando golden cookies e fortunes...")

        while not self.stop_event.is_set():
            try:
                # Verificar golden cookie
                if self.bridge.pop_golden_cookie():
                    logger.info("Golden cookie detectado e coletado")

                # Verificar fortune cookie
                if self.bridge.click_fortune():
                    logger.info("Fortune cookie detectada e clicada")

                # Delay maior para detecção (não precisa ser tão frequente)
                time.sleep(0.2)

            except Exception as e:
                logger.error(f"Erro na thread detector: {e}")
                time.sleep(1)  # Delay maior em caso de erro

    def clicker_loop(self):
        """Thread dedicada para clicar no cookie principal."""
        logger.info(f"Thread clicker iniciada. Pressione {self.toggle_key} para ligar/desligar.")

        while not self.stop_event.is_set():
            try:
                if self.is_running:
                    # Clique direto sem consultar bridge (posição já conhecida)
                    self.input_handler.click_cookie()
                    # Delay mínimo para não sobrecarregar
                    time.sleep(0.005)  # 5ms entre cliques

                # Verificar toggle
                if self.input_handler.is_key_pressed(self.toggle_key):
                    self.toggle()
                    time.sleep(0.3)  # Debounce

                # Pequeno delay quando parado
                if not self.is_running:
                    time.sleep(0.01)

            except Exception as e:
                logger.error(f"Erro na thread clicker: {e}")
                time.sleep(0.1)

    def run(self):
        """Executa as threads separadas."""
        # logger.info(f"Macro iniciado. Pressione {self.toggle_key} para ligar/desligar.")

        # Iniciar threads
        self.detector_thread = threading.Thread(target=self.detector_loop, daemon=True, name="Detector")
        self.clicker_thread = threading.Thread(target=self.clicker_loop, daemon=True, name="Clicker")

        self.detector_thread.start()
        self.clicker_thread.start()

        # Aguardar threads terminarem (nunca, pois são daemon)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Interrupção recebida, parando threads...")
            self.stop_event.set()

    def run_async(self):
        """Executa o macro em uma thread separada."""
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread


if __name__ == "__main__":
    pid = listar_janelas_cookie()
    if not pid:
        logger.error("Nenhuma janela do Cookie Clicker encontrada!")
        exit(1)

    logger.info(f"PID encontrado: {pid}")

    # Conectar bridge no início
    bridge = CookieClickerBridge()
    if not bridge.connect():
        logger.error("Falha ao conectar ao bridge JS. Saindo.")
        exit(1)

    # Criar runner com threads separadas
    runner = Run(pid=pid, bridge=bridge, toggle_key="SCROLLLOCK")
    runner.run()
