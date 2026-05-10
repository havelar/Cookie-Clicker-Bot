"""
Utilitários para encontrar e gerenciar janelas do Cookie Clicker.
"""
import win32gui
import win32process
from typing import Optional

from app.utils.logger import logger


def find_cookie_window() -> Optional[int]:
    """
    Procura pela janela do Cookie Clicker e retorna o PID do processo.

    Returns:
        PID do processo se encontrado, None caso contrário
    """
    def callback(hwnd, pids):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if "Cookie Clicker" in title:
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    pids.append(pid)
                    logger.info(f"Janela encontrada: '{title}' (PID: {pid})")
                except Exception as e:
                    logger.warning(f"Erro ao obter PID da janela '{title}': {e}")

    pids = []
    win32gui.EnumWindows(callback, pids)

    if pids:
        # Retorna o primeiro PID encontrado
        return pids[0]

    logger.warning("Nenhuma janela do Cookie Clicker encontrada")
    return None