"""
Sistema de logging centralizado para o Cookie Clicker Bot.
"""
import logging
import logging.handlers
import threading
import time
from collections import OrderedDict, Counter
from pathlib import Path
from typing import Optional

from app.config.settings import app_config


class RepeatedProblemFilter(logging.Filter):
    """Mostra a primeira falha e resume repetições, com memória limitada."""

    def __init__(self, interval=30.0, capacity=256, clock=time.monotonic):
        super().__init__()
        self.interval, self.capacity, self.clock = interval, capacity, clock
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def filter(self, record):
        if record.levelno < logging.WARNING:
            return True
        message = record.getMessage()
        key = (record.pathname, record.lineno, record.levelno, message)
        now = self.clock()
        with self.lock:
            previous = self.entries.get(key)
            if previous and now - previous[0] < self.interval:
                self.entries[key] = (previous[0], previous[1] + 1)
                self.entries.move_to_end(key)
                return False
            repeated = previous[1] if previous else 0
            self.entries[key] = (now, 0)
            self.entries.move_to_end(key)
            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)
        if repeated:
            record.msg = message + f" (mais {repeated} ocorrência(s) igual(is) nos últimos {self.interval:g} s)"
            record.args = ()
        return True


class ActivitySummary:
    """Agrupa coletas frequentes; contadores da interface seguem em tempo real."""

    def __init__(self, output, interval=60.0, clock=time.monotonic):
        self.output, self.interval, self.clock = output, interval, clock
        self.started = clock()
        self.counts = Counter()
        self.lock = threading.Lock()

    def record(self, name):
        with self.lock:
            self.counts[name] += 1
            self._flush_if_due()

    def _flush_if_due(self, force=False):
        now = self.clock()
        if self.counts and (force or now - self.started >= self.interval):
            text = ", ".join(f"{count} {name}" for name, count in self.counts.items())
            self.counts.clear()
            self.output.info("Coletas automáticas: %s.", text)
            self.started = now

    def flush(self):
        with self.lock:
            self._flush_if_due(force=True)


class BotLogger:
    """Logger personalizado com suporte a arquivo e console."""

    def __init__(self):
        self.logger = logging.getLogger('cookie_clicker_bot')
        self.logger.setLevel(getattr(logging, app_config.log_level))

        # Remover handlers existentes
        for handler in self.logger.handlers:
            handler.close()
        self.logger.handlers.clear()
        self.logger.filters.clear()
        self.logger.addFilter(RepeatedProblemFilter())
        self.logger.propagate = False

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
                backupCount=5,
                encoding="utf-8",
                errors="backslashreplace"
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
    for old_handler in list(logger.handlers):
        if isinstance(old_handler, UIHandler):
            logger.removeHandler(old_handler)
            old_handler.close()
    ui_handler = UIHandler(emitter)
    ui_handler.setLevel(logging.INFO)
    logger.addHandler(ui_handler)