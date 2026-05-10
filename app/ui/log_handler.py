"""
Handler de logging para interface gráfica.
"""
import logging

from app.ui.main_window import LogSignalEmitter


class UIHandler(logging.Handler):
    """Handler que envia logs para a interface gráfica via sinais."""

    def __init__(self, emitter: LogSignalEmitter):
        super().__init__()
        self.emitter = emitter
        self.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))

    def emit(self, record):
        """Emite o log formatado via sinal."""
        try:
            msg = self.format(record)
            self.emitter.log_signal.emit(msg)
        except Exception:
            self.handleError(record)