#!/usr/bin/env python3
"""
Ponto de entrada principal do Cookie Clicker Bot.
"""
import sys
import signal
from typing import Optional

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from app.bridge.js_bridge import CookieClickerBridge
from app.config.settings import load_automation_settings, save_automation_settings
from app.core.run import AutomationRunner
from app.core.window_finder import find_cookie_window
from app.ui.main_window import create_ui_app
from app.utils.logger import logger, add_ui_handler


class Application:
    """Classe principal da aplicação."""

    def __init__(self):
        self.app: Optional[QApplication] = None
        self.window = None
        self.bridge: Optional[CookieClickerBridge] = None
        self.runner: Optional[AutomationRunner] = None
        self.pid: Optional[int] = None

    def initialize(self) -> bool:
        """
        Inicializa a aplicação.

        Returns:
            True se inicializou com sucesso, False caso contrário
        """
        logger.info("Inicializando Cookie Clicker Bot...")
        load_automation_settings()

        # Encontrar janela do jogo
        self.pid = find_cookie_window()
        if not self.pid:
            logger.error("Nenhuma janela do Cookie Clicker encontrada!")
            return False

        logger.info(f"Janela do jogo encontrada (PID: {self.pid})")

        # Conectar bridge
        self.bridge = CookieClickerBridge()
        if not self.bridge.connect():
            logger.error("Falha ao conectar ao bridge JavaScript")
            return False

        logger.info("Bridge JavaScript conectado com sucesso")

        # Criar UI
        self.app, self.window = create_ui_app()

        # Conectar logger à UI
        add_ui_handler(self.window.log_emitter)

        # Conectar UI ao runner (será definido após criar runner)
        # self.window.runner = None  # Placeholder

        # Atualizar status na UI
        self.window.update_bridge_status(True)

        # Criar runner
        self.runner = AutomationRunner(
            pid=self.pid,
            bridge=self.bridge,
            state_change_callback=self.window.clicker_state_changed.emit,
        )

        # Conectar UI ao runner
        self.window.runner = self.runner

        logger.info("Aplicação inicializada com sucesso")
        return True

    def run(self) -> int:
        """
        Executa a aplicação.

        Returns:
            Código de saída
        """
        if not self.initialize():
            return 1

        # Configurar sinais para shutdown graceful
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

        # Mostrar janela
        self.window.show()

        # Iniciar threads de automação após o event loop estar ativo
        QTimer.singleShot(0, self.runner.start)

        # Executar aplicação Qt
        try:
            return self.app.exec_()
        except KeyboardInterrupt:
            self.shutdown()
            return 0

    def shutdown(self, signum=None, frame=None):
        """Encerra a aplicação de forma graceful."""
        logger.info("Encerrando aplicação...")
        save_automation_settings()

        if self.runner:
            self.runner.stop()

        if self.bridge:
            self.bridge.disconnect()

        if self.app:
            self.app.quit()

        logger.info("Aplicação encerrada")


def main():
    """Função principal."""
    application = Application()
    sys.exit(application.run())


if __name__ == "__main__":
    main()