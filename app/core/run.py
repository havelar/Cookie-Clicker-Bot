"""
Lógica principal de execução das automações do Cookie Clicker Bot.
"""
import time
import threading
from typing import Callable, Optional, Tuple

from app.automation.input import InputHandler
from app.bridge.js_bridge import CookieClickerBridge
from app.config.settings import app_config, automation_config
from app.core.window_finder import find_cookie_window
from app.utils.logger import logger


class Macro:
    """Define uma sequência de ações a serem executadas (mantido para compatibilidade)."""

    def __init__(self, commands):
        """
        commands: lista de tuplas (ação, parâmetros, delay)
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


class AutomationRunner:
    """Gerencia a execução das automações com threads separadas."""

    def __init__(self, pid: int, bridge: CookieClickerBridge, state_change_callback: Optional[Callable[[bool], None]] = None):
        """
        Inicializa o runner das automações.

        Args:
            pid: ID do processo do jogo
            bridge: Instância do bridge JS
            state_change_callback: Callback para notificar mudanças do clicker
        """
        self.bridge = bridge
        self.is_running = False
        self.stop_event = threading.Event()
        self.on_clicker_state_change = state_change_callback

        self.cookie_position: Optional[Tuple[int, int]] = None
        self.input_handler = InputHandler(pid=pid, restore_game=False, cookie_position=None)

        # Threads
        self.detector_thread: Optional[threading.Thread] = None
        self.clicker_thread: Optional[threading.Thread] = None

    def update_cookie_position(self) -> bool:
        """
        Atualiza a posição do cookie antes de iniciar o clique.

        Returns:
            True se conseguiu atualizar, False caso contrário
        """
        cookie_pos = self.bridge.get_cookie_position()
        if not cookie_pos:
            logger.error("Não foi possível obter a posição do cookie ao iniciar o macro")
            return False

        self.cookie_position = (cookie_pos['x'], cookie_pos['y'])
        self.input_handler.cookie_position = self.cookie_position
        logger.info(f"Posição do cookie atualizada: {self.cookie_position}")
        return True

    def toggle_clicker(self) -> None:
        """Liga/desliga o clicker do cookie."""
        if not self.is_running:
            if not self.update_cookie_position():
                return

        self.is_running = not self.is_running
        status = "INICIADO" if self.is_running else "PARADO"
        logger.info(f"Macro {status}!")

        if self.on_clicker_state_change:
            try:
                self.on_clicker_state_change(self.is_running)
            except Exception as e:
                logger.error(f"Erro no callback de estado do clicker: {e}")

    def detector_loop(self) -> None:
        """Thread dedicada para detectar Golden Cookies, Fortunes e Renas."""
        logger.info("Thread detector iniciada. Procurando golden cookies, fortunes e renas...")

        while not self.stop_event.is_set():
            try:
                # Verificar golden cookie
                if automation_config.enable_golden_cookie and self.bridge.pop_golden_cookie():
                    logger.info("Golden cookie detectado e coletado")

                # Verificar fortune cookie
                if automation_config.enable_fortune_cookie and self.bridge.click_fortune():
                    logger.info("Fortune cookie detectada e clicada")

                # Verificar rena
                if automation_config.enable_reindeer and self.bridge.pop_reindeer():
                    logger.info("Rena detectada e coletada")

                # Verificar wrinklers normais
                if automation_config.enable_wrinkler_popper and self.bridge.pop_normal_wrinkler():
                    logger.info("Wrinkler normal detectado e popado")

                # Delay configurável
                time.sleep(app_config.detect_interval)

            except Exception as e:
                logger.error(f"Erro na thread detector: {e}")
                time.sleep(1)

    def clicker_loop(self) -> None:
        """Thread dedicada para clicar no cookie principal."""
        logger.info(f"Thread clicker iniciada. Pressione {app_config.toggle_key} para ligar/desligar.")

        while not self.stop_event.is_set():
            try:
                if self.is_running and automation_config.enable_cookie_clicker:
                    # Clique direto sem consultar bridge
                    self.input_handler.click_cookie()
                    # Delay configurável
                    time.sleep(app_config.click_interval)

                # Verificar toggle
                if self.input_handler.is_key_pressed(app_config.toggle_key):
                    self.toggle_clicker()
                    time.sleep(0.3)  # Debounce

                # Pequeno delay quando parado
                if not self.is_running:
                    time.sleep(0.01)

            except Exception as e:
                logger.error(f"Erro na thread clicker: {e}")
                time.sleep(0.1)

    def start(self) -> None:
        """Inicia as threads de automação em background."""
        logger.info("Iniciando automações...")

        # Iniciar threads
        self.detector_thread = threading.Thread(target=self.detector_loop, daemon=True, name="Detector")
        self.clicker_thread = threading.Thread(target=self.clicker_loop, daemon=True, name="Clicker")

        self.detector_thread.start()
        self.clicker_thread.start()

        logger.info("Threads de automação iniciadas em background")

    def stop(self) -> None:
        """Para todas as threads."""
        self.stop_event.set()
        logger.info("Automações paradas")


if __name__ == "__main__":
    pid = find_cookie_window()
    if not pid:
        logger.error("Nenhuma janela do Cookie Clicker encontrada!")
        exit(1)

    logger.info(f"PID encontrado: {pid}")

    # Conectar bridge
    bridge = CookieClickerBridge()
    if not bridge.connect():
        logger.error("Falha ao conectar ao bridge JS. Saindo.")
        exit(1)

    # Criar e iniciar runner
    runner = AutomationRunner(pid=pid, bridge=bridge)
    runner.start()
