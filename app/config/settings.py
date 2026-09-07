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
    max_log_lines: int = 500

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

    # Sugar Lump
    enable_sugar_lump_harvest: bool = False
    preserve_sugar_lump_type_0: bool = False
    preserve_sugar_lump_type_1: bool = False
    preserve_sugar_lump_type_2: bool = True
    preserve_sugar_lump_type_3: bool = False
    preserve_sugar_lump_type_4: bool = True

    # Futuro: outras automações
    enable_reindeer: bool = False  # Para Natal

    enable_wrinkler_hp_log: bool = False # Nova configuração para log de HP dos wrinklers

    # Stock Market
    enable_stock_market_auto_trade: bool = False
    stock_market_buy_price_limit: float = 20.0
    stock_market_sell_price_limit: float = 80.0


@dataclass
class BackupConfig:
    """Configurações de backup de saves."""

    backup_folder: str = "save_backups"
    max_backups: int = 50
    auto_backup_enabled: bool = False


# Instância global das configurações
app_config = AppConfig()
automation_config = AutomationConfig()
backup_config = BackupConfig()


def load_app_settings() -> None:
    """Carrega as configurações gerais da aplicação do QSettings."""
    settings = QSettings("CookieClickerBot", "CookieClickerBot")
    settings.beginGroup("Application")
    app_config.max_log_lines = max(1, settings.value(
        "max_log_lines", app_config.max_log_lines, type=int
    ))
    settings.endGroup()


def save_app_settings() -> None:
    """Salva as configurações gerais da aplicação no QSettings."""
    settings = QSettings("CookieClickerBot", "CookieClickerBot")
    settings.beginGroup("Application")
    settings.setValue("max_log_lines", max(1, app_config.max_log_lines))
    settings.endGroup()
    settings.sync()


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
    automation_config.enable_sugar_lump_harvest = settings.value(
        "enable_sugar_lump_harvest",
        automation_config.enable_sugar_lump_harvest,
        type=bool,
    )
    automation_config.preserve_sugar_lump_type_0 = settings.value(
        "preserve_sugar_lump_type_0",
        automation_config.preserve_sugar_lump_type_0,
        type=bool,
    )
    automation_config.preserve_sugar_lump_type_1 = settings.value(
        "preserve_sugar_lump_type_1",
        automation_config.preserve_sugar_lump_type_1,
        type=bool,
    )
    automation_config.preserve_sugar_lump_type_2 = settings.value(
        "preserve_sugar_lump_type_2",
        automation_config.preserve_sugar_lump_type_2,
        type=bool,
    )
    automation_config.preserve_sugar_lump_type_3 = settings.value(
        "preserve_sugar_lump_type_3",
        automation_config.preserve_sugar_lump_type_3,
        type=bool,
    )
    automation_config.preserve_sugar_lump_type_4 = settings.value(
        "preserve_sugar_lump_type_4",
        automation_config.preserve_sugar_lump_type_4,
        type=bool,
    )
    automation_config.enable_stock_market_auto_trade = settings.value(
        "enable_stock_market_auto_trade",
        automation_config.enable_stock_market_auto_trade,
        type=bool,
    )
    automation_config.stock_market_buy_price_limit = settings.value(
        "stock_market_buy_price_limit",
        automation_config.stock_market_buy_price_limit,
        type=float,
    )
    automation_config.stock_market_sell_price_limit = settings.value(
        "stock_market_sell_price_limit",
        automation_config.stock_market_sell_price_limit,
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
    settings.setValue("enable_sugar_lump_harvest", automation_config.enable_sugar_lump_harvest)
    settings.setValue("preserve_sugar_lump_type_0", automation_config.preserve_sugar_lump_type_0)
    settings.setValue("preserve_sugar_lump_type_1", automation_config.preserve_sugar_lump_type_1)
    settings.setValue("preserve_sugar_lump_type_2", automation_config.preserve_sugar_lump_type_2)
    settings.setValue("preserve_sugar_lump_type_3", automation_config.preserve_sugar_lump_type_3)
    settings.setValue("preserve_sugar_lump_type_4", automation_config.preserve_sugar_lump_type_4)
    settings.setValue("enable_stock_market_auto_trade", automation_config.enable_stock_market_auto_trade)
    settings.setValue("stock_market_buy_price_limit", automation_config.stock_market_buy_price_limit)
    settings.setValue("stock_market_sell_price_limit", automation_config.stock_market_sell_price_limit)
    settings.endGroup()
    settings.sync()


def load_backup_settings() -> None:
    """Carrega as configurações de backup do QSettings."""
    settings = QSettings("CookieClickerBot", "CookieClickerBot")
    settings.beginGroup("Backup")
    backup_config.backup_folder = settings.value(
        "backup_folder",
        backup_config.backup_folder,
        type=str,
    )
    backup_config.max_backups = settings.value(
        "max_backups",
        backup_config.max_backups,
        type=int,
    )
    backup_config.auto_backup_enabled = settings.value(
        "auto_backup_enabled",
        backup_config.auto_backup_enabled,
        type=bool,
    )
    settings.endGroup()


def save_backup_settings() -> None:
    """Salva as configurações de backup no QSettings."""
    settings = QSettings("CookieClickerBot", "CookieClickerBot")
    settings.beginGroup("Backup")
    settings.setValue("backup_folder", backup_config.backup_folder)
    settings.setValue("max_backups", backup_config.max_backups)
    settings.setValue("auto_backup_enabled", backup_config.auto_backup_enabled)
    settings.endGroup()
    settings.sync()
