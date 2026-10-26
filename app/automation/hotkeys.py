"""Atalhos reconhecidos pelo teclado e pelos botões adicionais do mouse."""
HOTKEY_CODES = {
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
    "MOUSE3": 0x04, "MOUSE4": 0x05, "MOUSE5": 0x06,
}


def hotkey_name(key):
    names = {"SCROLLLOCK": "Scroll Lock", "MOUSE3": "Botão do meio", "MOUSE4": "Lateral 1",
             "MOUSE5": "Lateral 2", "INS": "Insert", "DEL": "Delete", "PAUSE": "Pause",
             "CAPSLOCK": "Caps Lock", "NUMLOCK": "Num Lock", "SPACE": "Espaço",
             "PGUP": "Page Up", "PGDOWN": "Page Down", "PRINTSCREEN": "Print Screen"}
    return names.get(key, key)
