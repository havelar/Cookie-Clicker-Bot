"""
Sistema de logging centralizado para o Cookie Clicker Bot.
"""
import logging
import logging.handlers
from pathlib import Path
from typing import Optional

from app.config.settings import app_config


class BotLogger:
    """Logger personalizado com suporte a arquivo e console."""

    def __init__(self):
        self.logger = logging.getLogger('cookie_clicker_bot')
        self.logger.setLevel(getattr(logging, app_config.log_level))

        # Remover handlers existentes
        self.logger.handlers.clear()

        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # File handler (se habilitado)
        if app_config.log_to_file:
            log_path = Path(app_config.log_file_path)
            log_path.parent.mkdir(exist_ok=True)

            file_handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

    def get_logger(self) -> logging.Logger:
        """Retorna o logger configurado."""
        return self.logger


# Instância global do logger
bot_logger = BotLogger()
logger = bot_logger.get_logger()


def add_ui_handler(emitter: 'LogSignalEmitter') -> None:
    """
    Adiciona handler para interface gráfica.

    Args:
        emitter: Emissor de sinais para logs
    """
    from app.ui.log_handler import UIHandler
    ui_handler = UIHandler(emitter)
    ui_handler.setLevel(logging.INFO)
    logger.addHandler(ui_handler)