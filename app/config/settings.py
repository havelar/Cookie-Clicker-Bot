"""
Configurações centralizadas do Cookie Clicker Bot.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class AppConfig:
    """Configurações principais da aplicação."""

    # Debug e logging
    debug: bool = False
    log_level: str = "INFO"
    log_to_file: bool = True
    log_file_path: str = "logs/cookie_clicker_bot.log"

    # Remote debugging
    remote_debugging_host: str = "localhost"
    remote_debugging_port: int = 9222
    connection_timeout: int = 5

    # Automação timing
    click_interval: float = 0.005  # 5ms entre cliques
    detect_interval: float = 0.2   # 200ms para detecção

    # UI
    ui_update_interval: float = 0.1  # 100ms para updates da UI

    # Toggle keys
    toggle_key: str = "SCROLLLOCK"

    # Window detection
    window_title_pattern: str = "cookie"


@dataclass
class AutomationConfig:
    """Configurações específicas das automações."""

    # Cookie clicker
    enable_cookie_clicker: bool = True
    enable_golden_cookie: bool = True
    enable_fortune_cookie: bool = True

    # Futuro: outras automações
    enable_reindeer: bool = False  # Para Natal


# Instância global das configurações
app_config = AppConfig()
automation_config = AutomationConfig()