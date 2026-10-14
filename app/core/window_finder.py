"""
Utilitários para encontrar e gerenciar janelas do Cookie Clicker.
"""
import ctypes
from ctypes import wintypes
from pathlib import PureWindowsPath
import win32gui
import win32process
from typing import Optional

from app.utils.logger import logger


def is_cookie_process(pid: int) -> bool:
    """Valida o executável; títulos de navegador/editor não identificam o jogo."""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                 wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        path = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(path))
        if not kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(length)):
            return False
        return PureWindowsPath(path.value).name.casefold() == 'cookie clicker.exe'
    finally:
        kernel.CloseHandle(handle)


def find_cookie_window() -> Optional[int]:
    """
    Procura pela janela do Cookie Clicker e retorna o PID do processo.

    Returns:
        PID do processo se encontrado, None caso contrário
    """
    def callback(hwnd, pids):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if "Cookie Clicker" in title and "Cookie Clicker Bot" not in title:
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if not is_cookie_process(pid):
                        return
                    pids.append(pid)
                    logger.debug(f"Janela encontrada: '{title}' (PID: {pid})")
                except Exception as e:
                    logger.warning(f"Erro ao obter PID da janela '{title}': {e}")

    pids = []
    win32gui.EnumWindows(callback, pids)

    if pids:
        # Retorna o primeiro PID encontrado
        return pids[0]

    logger.debug("Jogo fechado: nenhuma janela do Cookie Clicker encontrada")
    return None