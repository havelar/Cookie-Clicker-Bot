"""
Configurações centralizadas do Cookie Clicker Bot.
"""
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import QSettings


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
    enable_wrinkler_popper: bool = False
    wrinkler_pop_delay: float = 15.0

    # Futuro: outras automações
    enable_reindeer: bool = False  # Para Natal


# Instância global das configurações
app_config = AppConfig()
automation_config = AutomationConfig()


def load_automation_settings() -> None:
    """Carrega as configurações de automação do QSettings."""
    settings = QSettings("CookieClickerBot", "CookieClickerBot")
    settings.beginGroup("Automation")
    automation_config.enable_cookie_clicker = settings.value(
        "enable_cookie_clicker",
        automation_config.enable_cookie_clicker,
        type=bool,
    )
    automation_config.enable_golden_cookie = settings.value(
        "enable_golden_cookie",
        automation_config.enable_golden_cookie,
        type=bool,
    )
    automation_config.enable_fortune_cookie = settings.value(
        "enable_fortune_cookie",
        automation_config.enable_fortune_cookie,
        type=bool,
    )
    automation_config.enable_reindeer = settings.value(
        "enable_reindeer",
        automation_config.enable_reindeer,
        type=bool,
    )
    automation_config.enable_wrinkler_popper = settings.value(
        "enable_wrinkler_popper",
        automation_config.enable_wrinkler_popper,
        type=bool,
    )
    automation_config.wrinkler_pop_delay = settings.value(
        "wrinkler_pop_delay",
        automation_config.wrinkler_pop_delay,
        type=float,
    )
    settings.endGroup()


def save_automation_settings() -> None:
    """Salva as configurações de automação no QSettings."""
    settings = QSettings("CookieClickerBot", "CookieClickerBot")
    settings.beginGroup("Automation")
    settings.setValue("enable_cookie_clicker", automation_config.enable_cookie_clicker)
    settings.setValue("enable_golden_cookie", automation_config.enable_golden_cookie)
    settings.setValue("enable_fortune_cookie", automation_config.enable_fortune_cookie)
    settings.setValue("enable_reindeer", automation_config.enable_reindeer)
    settings.setValue("enable_wrinkler_popper", automation_config.enable_wrinkler_popper)
    settings.setValue("wrinkler_pop_delay", automation_config.wrinkler_pop_delay)
    settings.endGroup()
    settings.sync()