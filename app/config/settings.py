"""
Configurações centralizadas do Cookie Clicker Bot.
"""
from dataclasses import dataclass, field
import json
from typing import Optional

from PyQt5.QtCore import QSettings
from app.core.stock_policy import valid_limits


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
    enable_grimoire_spell_spam: bool = False
    grimoire_spell_id: int = 0

    # Sugar Lump
    enable_sugar_lump_harvest: bool = False
    preserve_sugar_lump_type_0: bool = False
    preserve_sugar_lump_type_1: bool = False
    preserve_sugar_lump_type_2: bool = True
    preserve_sugar_lump_type_3: bool = False
    preserve_sugar_lump_type_4: bool = True

    # Futuro: outras automações
    enable_reindeer: bool = False  # Para Natal

    # Stock Market
    enable_stock_market_auto_trade: bool = False
    stock_market_buy_price_limit: float = 20.0
    stock_market_sell_price_limit: float = 80.0
    stock_market_trend_ticks: int = 5
    stock_market_reversal_percent: float = 5.0
    enable_stock_market_owned_only_view: bool = False
    stock_market_use_reference_prices: bool = True
    stock_market_asset_limits: dict = field(default_factory=dict)

    # Garden: seguro por padrão; intervalo usado somente se M.nextStep faltar.
    enable_garden_automation: bool = False
    enable_green_aching_thumb: bool = False
    garden_poll_interval_seconds: int = 60

    # Auto Ascensão: sempre desativada por padrão e confirmada a cada execução real.
    enable_auto_ascension: bool = False
    auto_ascension_target_cycles: int = 1
    auto_ascension_minimum_prestige_gain: float = 1.0
    auto_ascension_poll_interval_seconds: float = 0.1
    auto_ascension_max_cycle_seconds: int = 86_400

    # Combo endgame: execução real sempre parte desligada.
    enable_combo_automation: bool = False
    combo_target_cookies: float = 1e72
    combo_max_search_ahead: int = 5_000
    combo_max_skip_lumps: int = 64
    combo_required_building_specials: int = 2
    combo_poll_interval_seconds: float = 0.2
    combo_minimum_buff_seconds: float = 12.0
    combo_max_wait_minutes: int = 180
    combo_use_sugar_frenzy: bool = True
    combo_use_loans: bool = True
    combo_pause_before_last_skips: bool = False

    # Simple Farm: farm paralelo com reserva majoritária, sem venda de torres.
    enable_simple_farm: bool = False
    simple_farm_max_search_ahead: int = 250
    simple_farm_poll_interval_seconds: float = 0.2
    simple_farm_minimum_buff_seconds: float = 8.0
    simple_farm_cash_reserve_percent: float = 80.0
    simple_farm_investment_percent: float = 5.0


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
    automation_config.enable_grimoire_spell_spam = settings.value(
        "enable_grimoire_spell_spam",
        automation_config.enable_grimoire_spell_spam,
        type=bool,
    )
    automation_config.grimoire_spell_id = max(0, settings.value(
        "grimoire_spell_id",
        automation_config.grimoire_spell_id,
        type=int,
    ))
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
    automation_config.stock_market_trend_ticks = max(2, settings.value(
        "stock_market_trend_ticks",
        automation_config.stock_market_trend_ticks,
        type=int,
    ))
    automation_config.stock_market_reversal_percent = max(0.01, settings.value(
        "stock_market_reversal_percent",
        automation_config.stock_market_reversal_percent,
        type=float,
    ))
    automation_config.enable_stock_market_owned_only_view = settings.value(
        "enable_stock_market_owned_only_view",
        automation_config.enable_stock_market_owned_only_view,
        type=bool,
    )
    automation_config.stock_market_use_reference_prices = settings.value(
        "stock_market_use_reference_prices", True, type=bool,
    )
    try:
        limits = json.loads(settings.value("stock_market_asset_limits", "{}", type=str))
        automation_config.stock_market_asset_limits = {
            key: value for key, value in limits.items()
            if key.isdigit() and valid_limits(value)
        } if isinstance(limits, dict) else {}
    except (ValueError, TypeError):
        automation_config.stock_market_asset_limits = {}
    automation_config.enable_garden_automation = settings.value(
        "enable_garden_automation", False, type=bool,
    )
    automation_config.enable_green_aching_thumb = settings.value(
        "enable_green_aching_thumb", False, type=bool,
    )
    automation_config.garden_poll_interval_seconds = min(3600, max(30, settings.value(
        "garden_poll_interval_seconds",
        automation_config.garden_poll_interval_seconds,
        type=int,
    )))
    automation_config.enable_auto_ascension = settings.value(
        "enable_auto_ascension", False, type=bool,
    )
    automation_config.auto_ascension_target_cycles = min(10_000, max(1, settings.value(
        "auto_ascension_target_cycles",
        automation_config.auto_ascension_target_cycles,
        type=int,
    )))
    automation_config.auto_ascension_minimum_prestige_gain = max(0.0, settings.value(
        "auto_ascension_minimum_prestige_gain",
        automation_config.auto_ascension_minimum_prestige_gain,
        type=float,
    ))
    automation_config.auto_ascension_poll_interval_seconds = min(3600.0, max(0.1, settings.value(
        "auto_ascension_poll_interval_seconds",
        automation_config.auto_ascension_poll_interval_seconds,
        type=float,
    )))
    automation_config.auto_ascension_max_cycle_seconds = min(31_536_000, max(1, settings.value(
        "auto_ascension_max_cycle_seconds",
        automation_config.auto_ascension_max_cycle_seconds,
        type=int,
    )))
    automation_config.enable_combo_automation = settings.value(
        "enable_combo_automation", False, type=bool,
    )
    automation_config.combo_target_cookies = max(1.0, settings.value(
        "combo_target_cookies", automation_config.combo_target_cookies, type=float,
    ))
    automation_config.combo_max_search_ahead = min(100_000, max(4, settings.value(
        "combo_max_search_ahead", automation_config.combo_max_search_ahead, type=int,
    )))
    automation_config.combo_max_skip_lumps = min(10_000, max(0, settings.value(
        "combo_max_skip_lumps", automation_config.combo_max_skip_lumps, type=int,
    )))
    automation_config.combo_required_building_specials = min(6, max(1, settings.value(
        "combo_required_building_specials",
        automation_config.combo_required_building_specials,
        type=int,
    )))
    automation_config.combo_poll_interval_seconds = min(60.0, max(0.1, settings.value(
        "combo_poll_interval_seconds", automation_config.combo_poll_interval_seconds, type=float,
    )))
    automation_config.combo_minimum_buff_seconds = min(120.0, max(5.0, settings.value(
        "combo_minimum_buff_seconds", automation_config.combo_minimum_buff_seconds, type=float,
    )))
    automation_config.combo_max_wait_minutes = min(1440, max(1, settings.value(
        "combo_max_wait_minutes", 180, type=int,
    )))
    # Migração única dos antigos padrões: o usuário pediu uma busca em horas.
    # Valores diferentes dos padrões antigos continuam preservados.
    if settings.value("combo_strategy_revision", 0, type=int) < 2:
        for name, old, new in (
            ("combo_required_building_specials", 3, 2),
            ("combo_poll_interval_seconds", 1.0, 0.2),
            ("combo_minimum_buff_seconds", 15.0, 12.0),
        ):
            if getattr(automation_config, name) == old:
                setattr(automation_config, name, new)
            settings.setValue(name, getattr(automation_config, name))
        settings.setValue("combo_strategy_revision", 2)
    automation_config.combo_use_sugar_frenzy = settings.value(
        "combo_use_sugar_frenzy", True, type=bool,
    )
    automation_config.combo_use_loans = settings.value(
        "combo_use_loans", True, type=bool,
    )
    automation_config.combo_pause_before_last_skips = settings.value(
        "combo_pause_before_last_skips", False, type=bool,
    )
    automation_config.enable_simple_farm = settings.value(
        "enable_simple_farm", False, type=bool,
    )
    automation_config.simple_farm_max_search_ahead = min(10_000, max(2, settings.value(
        "simple_farm_max_search_ahead",
        automation_config.simple_farm_max_search_ahead,
        type=int,
    )))
    automation_config.simple_farm_poll_interval_seconds = min(10.0, max(0.1, settings.value(
        "simple_farm_poll_interval_seconds",
        automation_config.simple_farm_poll_interval_seconds,
        type=float,
    )))
    automation_config.simple_farm_minimum_buff_seconds = min(60.0, max(3.0, settings.value(
        "simple_farm_minimum_buff_seconds",
        automation_config.simple_farm_minimum_buff_seconds,
        type=float,
    )))
    automation_config.simple_farm_cash_reserve_percent = min(99.0, max(60.0, settings.value(
        "simple_farm_cash_reserve_percent",
        automation_config.simple_farm_cash_reserve_percent,
        type=float,
    )))
    automation_config.simple_farm_investment_percent = min(20.0, max(1.0, settings.value(
        "simple_farm_investment_percent",
        automation_config.simple_farm_investment_percent,
        type=float,
    )))
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
    settings.setValue("enable_grimoire_spell_spam", automation_config.enable_grimoire_spell_spam)
    settings.setValue("grimoire_spell_id", automation_config.grimoire_spell_id)
    settings.setValue("enable_sugar_lump_harvest", automation_config.enable_sugar_lump_harvest)
    settings.setValue("preserve_sugar_lump_type_0", automation_config.preserve_sugar_lump_type_0)
    settings.setValue("preserve_sugar_lump_type_1", automation_config.preserve_sugar_lump_type_1)
    settings.setValue("preserve_sugar_lump_type_2", automation_config.preserve_sugar_lump_type_2)
    settings.setValue("preserve_sugar_lump_type_3", automation_config.preserve_sugar_lump_type_3)
    settings.setValue("preserve_sugar_lump_type_4", automation_config.preserve_sugar_lump_type_4)
    settings.setValue("enable_stock_market_auto_trade", automation_config.enable_stock_market_auto_trade)
    settings.setValue("stock_market_buy_price_limit", automation_config.stock_market_buy_price_limit)
    settings.setValue("stock_market_sell_price_limit", automation_config.stock_market_sell_price_limit)
    settings.setValue("stock_market_trend_ticks", automation_config.stock_market_trend_ticks)
    settings.setValue("stock_market_reversal_percent", automation_config.stock_market_reversal_percent)
    settings.setValue("enable_stock_market_owned_only_view", automation_config.enable_stock_market_owned_only_view)
    settings.setValue("stock_market_use_reference_prices", automation_config.stock_market_use_reference_prices)
    settings.setValue("stock_market_asset_limits", json.dumps(automation_config.stock_market_asset_limits))
    settings.setValue("enable_garden_automation", automation_config.enable_garden_automation)
    settings.setValue("enable_green_aching_thumb", automation_config.enable_green_aching_thumb)
    settings.setValue("garden_poll_interval_seconds", automation_config.garden_poll_interval_seconds)
    settings.setValue("enable_auto_ascension", automation_config.enable_auto_ascension)
    settings.setValue("auto_ascension_target_cycles", automation_config.auto_ascension_target_cycles)
    settings.setValue(
        "auto_ascension_minimum_prestige_gain",
        automation_config.auto_ascension_minimum_prestige_gain,
    )
    settings.setValue(
        "auto_ascension_poll_interval_seconds",
        automation_config.auto_ascension_poll_interval_seconds,
    )
    settings.setValue(
        "auto_ascension_max_cycle_seconds",
        automation_config.auto_ascension_max_cycle_seconds,
    )
    settings.setValue("enable_combo_automation", automation_config.enable_combo_automation)
    settings.setValue("combo_target_cookies", automation_config.combo_target_cookies)
    settings.setValue("combo_max_search_ahead", automation_config.combo_max_search_ahead)
    settings.setValue("combo_max_skip_lumps", automation_config.combo_max_skip_lumps)
    settings.setValue(
        "combo_required_building_specials",
        automation_config.combo_required_building_specials,
    )
    settings.setValue("combo_poll_interval_seconds", automation_config.combo_poll_interval_seconds)
    settings.setValue("combo_minimum_buff_seconds", automation_config.combo_minimum_buff_seconds)
    settings.setValue("combo_max_wait_minutes", automation_config.combo_max_wait_minutes)
    settings.setValue("combo_strategy_revision", 2)
    settings.setValue("combo_use_sugar_frenzy", automation_config.combo_use_sugar_frenzy)
    settings.setValue("combo_use_loans", automation_config.combo_use_loans)
    settings.setValue("combo_pause_before_last_skips", automation_config.combo_pause_before_last_skips)
    settings.setValue("enable_simple_farm", automation_config.enable_simple_farm)
    settings.setValue("simple_farm_max_search_ahead", automation_config.simple_farm_max_search_ahead)
    settings.setValue("simple_farm_poll_interval_seconds", automation_config.simple_farm_poll_interval_seconds)
    settings.setValue("simple_farm_minimum_buff_seconds", automation_config.simple_farm_minimum_buff_seconds)
    settings.setValue("simple_farm_cash_reserve_percent", automation_config.simple_farm_cash_reserve_percent)
    settings.setValue("simple_farm_investment_percent", automation_config.simple_farm_investment_percent)
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
