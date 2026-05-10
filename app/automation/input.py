"""
Gerenciamento de entrada (mouse e teclado) para automação do Cookie Clicker.
"""
import time
from typing import Optional, Tuple

import win32api
import win32con
import win32gui
import win32process

from app.utils.logger import logger

# Constantes do Windows
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001


class InputHandler:
    """Classe responsável por gerenciar interações de entrada (mouse e teclado)."""

    VK_MAP = {
        # Teclas de função
        "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
        "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
        "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,

        # Letras A-Z
        **{chr(i): i for i in range(0x41, 0x5B)},  # A-Z

        # Dígitos 0-9
        **{str(i): 0x30 + i for i in range(10)},

        # Controle e edição
        "ESC": 0x1B, "TAB": 0x09, "CAPSLOCK": 0x14, "SPACE": 0x20,
        "ENTER": 0x0D, "BACKSPACE": 0x08, "INS": 0x2D, "DEL": 0x2E,
        "HOME": 0x24, "END": 0x23, "PGUP": 0x21, "PGDOWN": 0x22,

        # Setas
        "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,

        # Shift / Ctrl / Alt
        "SHIFT": 0x10, "CTRL": 0x11, "ALT": 0x12,
        "LSHIFT": 0xA0, "RSHIFT": 0xA1,
        "LCTRL": 0xA2, "RCTRL": 0xA3,
        "LALT": 0xA4, "RALT": 0xA5,

        # Teclado numérico
        **{f"NUMPAD{i}": 0x60 + i for i in range(10)},
        "NUMPAD_DIV": 0x6F, "NUMPAD_MUL": 0x6A,
        "NUMPAD_SUB": 0x6D, "NUMPAD_ADD": 0x6B, "NUMPAD_DOT": 0x6E,

        # Pontuação e símbolos
        "OEM_COMMA": 0xBC, "OEM_PERIOD": 0xBE,
        "OEM_MINUS": 0xBD, "OEM_PLUS": 0xBB,
        "OEM_SLASH": 0xBF, "OEM_SEMICOLON": 0xBA,
        "OEM_QUOTE": 0xDE, "OEM_BRACKET_LEFT": 0xDB,
        "OEM_BRACKET_RIGHT": 0xDD, "OEM_BACKSLASH": 0xDC,
        "OEM_TILDE": 0xC0,

        # Teclas extras
        "PRINTSCREEN": 0x2C, "SCROLLLOCK": 0x91,
        "PAUSE": 0x13, "NUMLOCK": 0x90,
        "APPS": 0x5D, "WIN": 0x5B,
    }

    def __init__(self, pid: int, restore_game: bool = True, cookie_position: Optional[Tuple[int, int]] = None):
        """
        Inicializa o handler de entrada.

        Args:
            pid: ID do processo do jogo
            restore_game: Se deve restaurar a janela do jogo
            cookie_position: Posição fixa do cookie (x, y)
        """
        self._get_hwnd(pid=pid)
        self.timeout = 5000
        self.cookie_position = cookie_position

        if restore_game:
            self._restore_window()


    # === Funções de Ações ===
    def click(self, x=50, y=50) -> bool:
        """
        Envia um clique esquerdo virtual em uma posição fixa (melhor performance).
        """
        try:
            # Clique no canto superior esquerdo da janela (ex: (5,5))
            lparam = self._make_lparam(x, y)

            self._send_message(WM_LBUTTONDOWN, MK_LBUTTON, lparam)
            self._send_message(WM_LBUTTONUP, 0, lparam)
            return True
        except Exception as e:
            print(f"Erro ao enviar clique virtual: {e}")
            return False

    def click_cookie(self, bridge=None) -> bool:
        """
        Clica no cookie principal usando posição fixa ou obtida do bridge.
        """
        try:
            if self.cookie_position:
                x, y = self.cookie_position
            else:
                # Fallback: perguntar ao bridge
                position = bridge.get_cookie_position() if bridge else None
                if not position:
                    print("Não foi possível obter a posição do cookie")
                    return False
                x, y = position['x'], position['y']

            # Clicar diretamente na posição sem mover o mouse
            return self.click(x, y)
        except Exception as e:
            print(f"Erro ao clicar no cookie: {e}")
            return False

    def move(self, x: int, y: int) -> bool:
        """
        Move o cursor físico para a posição (x, y) dentro da janela do jogo.
        """
        try:
            left, top, _, _ = win32gui.GetWindowRect(self.hwnd)
            screen_x = left + x
            screen_y = top + y
            win32api.SetCursorPos((screen_x, screen_y))
            return True
        except Exception as e:
            print(f"Erro ao mover o mouse: {e}")
            return False

    def send_key(self, key: str) -> None:
        """
        Envia um pressionamento e liberação de tecla para a janela do jogo.
        """
        vk_code = self.VK_MAP[key]
        scan_code = win32api.MapVirtualKey(vk_code, 0)
        lparamdown = (scan_code << 16) | 1
        lparamup = (1 << 31) | (1 << 30) | (scan_code << 16) | 1

        try:
            self._send_message(win32con.WM_KEYDOWN, vk_code, lparamdown)
            self._send_message(win32con.WM_KEYUP, vk_code, lparamup)
        except Exception as e:
            print(f"ERRO ao enviar tecla '{key}': {e}")

    @staticmethod
    def is_key_pressed(key: str) -> bool:
        """
        Verifica se a tecla está fisicamente pressionada no momento.

        Args:
            key: Nome da tecla (ex: "F12", "SPACE")

        Returns:
            True se a tecla estiver pressionada
        """
        vk_code = InputHandler.VK_MAP[key]
        state = win32api.GetAsyncKeyState(vk_code)
        return (state & 0x8000) != 0

    def _send_message(self, msg: int, wparam: int, lparam: int, flags: int = win32con.SMTO_BLOCK, timeout: Optional[int] = None) -> int:
        """
        Envia uma mensagem para a janela com timeout.

        Args:
            msg: Código da mensagem
            wparam: Parâmetro W
            lparam: Parâmetro L
            flags: Flags da mensagem
            timeout: Timeout em milissegundos

        Returns:
            Resultado da mensagem
        """
        if timeout is None:
            timeout = self.timeout
        return win32gui.SendMessageTimeout(self.hwnd, msg, wparam, lparam, flags, timeout)

    def _make_lparam(self, x: int, y: int) -> int:
        """
        Constrói o valor LPARAM para coordenadas.

        Args:
            x: Coordenada X
            y: Coordenada Y

        Returns:
            Valor LPARAM
        """
        return y << 16 | x

    def _restore_window(self) -> None:
        """Restaura e traz a janela do jogo para frente."""
        win32gui.ShowWindow(self.hwnd, 5)
        win32gui.SetForegroundWindow(self.hwnd)

    def _get_hwnd(self, pid: int) -> None:
        """
        Obtém o identificador de janela (HWND) do processo.

        Args:
            pid: ID do processo

        Raises:
            Exception: Se nenhuma janela for encontrada
        """
        def callback(hwnd: int, result: list) -> bool:
            if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
                _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                if window_pid == pid:
                    result.append(hwnd)
            return True

        hwnds = []
        win32gui.EnumWindows(callback, hwnds)

        if hwnds:
            self.hwnd = hwnds[0]
        else:
            raise Exception(f"Nenhuma janela encontrada para o PID {pid}")
