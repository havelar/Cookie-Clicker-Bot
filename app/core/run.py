"""
Lógica principal de execução das automações do Cookie Clicker Bot.
"""
import time
import threading
from typing import Callable, Optional, Tuple

from app.automation.input import InputHandler
from app.bridge.js_bridge import CookieClickerBridge
from app.config.settings import app_config, automation_config
from app.core.window_finder import find_cookie_window
from app.utils.logger import logger, ActivitySummary


class Macro:
    """Define uma sequência de ações a serem executadas (mantido para compatibilidade)."""

    def __init__(self, commands):
        """
        commands: lista de tuplas (ação, parâmetros, delay)
        """
        self.commands = commands

    def execute(self, input_handler, bridge=None):
        """Executa todas as ações do macro."""
        for cmd, param, delay in self.commands:
            if cmd == "click_cookie":
                input_handler.click_cookie(bridge)
                logger.info("Clicou no cookie principal")
            elif cmd == "check_golden":
                if bridge and bridge.pop_golden_cookie():
                    logger.info("Golden cookie detectado e coletado")
            elif cmd == "check_fortune":
                if bridge and bridge.click_fortune():
                    logger.info("Fortune cookie detectada e clicada")
            elif cmd == "move":
                input_handler.move(*param)
                logger.info(f"Moved to {param}")
            elif cmd == "send_key":
                input_handler.send_key(param[0])
                logger.info(f"Key sent: {param[0]}")
            time.sleep(delay)


# Classe Macro mantida para compatibilidade futura, mas não usada na implementação atual


class AutomationRunner:
    """Gerencia a execução das automações com threads separadas."""

    def __init__(self, pid: int, bridge: CookieClickerBridge, state_change_callback: Optional[Callable[[bool], None]] = None):
        """
        Inicializa o runner das automações.

        Args:
            pid: ID do processo do jogo
            bridge: Instância do bridge JS
            state_change_callback: Callback para notificar mudanças do clicker
        """
        self.bridge = bridge
        self.is_running = False
        self.mouse_clicker_running = False
        self.cookie_hold_active = False
        self.mouse_hold_active = False
        self.mouse_clicks = 0
        self.mouse_clicker_over_game = False
        self.hotkey_capture_active = threading.Event()
        self.stop_event = threading.Event()
        self.paused = threading.Event()
        self._collection_summary = ActivitySummary(logger)
        self._clicker_state_lock = threading.RLock()
        self._exclusive_lock = threading.RLock()
        self._exclusive_owner: Optional[str] = None
        self._simple_farm_active = False
        self._simple_farm_manual_clicker = False
        self._simple_farm_clicker_requested = False
        self.on_clicker_state_change = state_change_callback

        self.cookie_position: Optional[Tuple[int, int]] = None
        self.input_handler = InputHandler(pid=pid, restore_game=False, cookie_position=None)
        self._next_wrinkler_check = 0.0
        self._wrinkler_blocked = False
        self._cash_requests: dict[str, dict] = {}
        self._cash_request_lock = threading.RLock()
        self._next_krumblor_check = 0.0
        self._last_krumblor_state = None
        self._last_grimoire_attempt_at = 0.0
        self._last_grimoire_failure: Optional[tuple] = None

        # Contadores de eventos
        self.cookies_clicked: int = 0
        self.golden_cookies_clicked: int = 0
        self.reindeer_popped: int = 0
        self.wrinklers_popped: int = 0
        self.sugar_lumps_harvested: int = 0

        # Threads
        self.detector_thread: Optional[threading.Thread] = None
        self.clicker_thread: Optional[threading.Thread] = None

    def set_paused(self, paused: bool):
        """Bloqueia detector, atalhos e clicker sem alterar as preferências."""
        if paused:
            self.paused.set()
            self.cookie_hold_active = self.mouse_hold_active = False
            self.mouse_clicker_running = False
            with self._cash_request_lock:
                self._cash_requests.clear()
            self._collection_summary.flush()
            self.ensure_clicker_stopped()
        else:
            self.paused.clear()
            self.reset_krumblor_schedule()
            self._next_wrinkler_check = 0.0

    def update_cookie_position(self) -> bool:
        """
        Atualiza a posição do cookie antes de iniciar o clique.

        Returns:
            True se conseguiu atualizar, False caso contrário
        """
        cookie_pos = self.bridge.get_cookie_position()
        if not cookie_pos:
            logger.error("Não foi possível obter a posição do cookie ao iniciar o macro")
            return False

        self.cookie_position = (cookie_pos['x'], cookie_pos['y'])
        self.input_handler.cookie_position = self.cookie_position
        logger.debug(f"Posição do cookie atualizada: {self.cookie_position}")
        return True

    def toggle_clicker(self) -> None:
        """Liga/desliga o clicker do cookie."""
        if self.paused.is_set():
            return
        with self._exclusive_lock:
            if self._simple_farm_active:
                self._simple_farm_manual_clicker = not self._simple_farm_manual_clicker
                self.set_simple_farm_clicker(self._simple_farm_clicker_requested)
                return
            if self._exclusive_owner is not None:
                logger.warning(
                    "Toggle manual do clicker bloqueado pelo modo exclusivo %s",
                    self._exclusive_owner,
                )
                return
        with self._clicker_state_lock:
            if not self.is_running and not self.update_cookie_position():
                return
            self.is_running = not self.is_running
            current_state = self.is_running
        status = "INICIADO" if current_state else "PARADO"
        logger.info("Clicker: %s.", "ligado" if current_state else "desligado")

        if self.on_clicker_state_change:
            try:
                self.on_clicker_state_change(current_state)
            except Exception as e:
                logger.error(f"Erro no callback de estado do clicker: {e}")

    def toggle_mouse_clicker(self):
        with self._exclusive_lock:
            if self.paused.is_set() or self.stop_event.is_set() or self._exclusive_owner is not None:
                return False
            self.mouse_clicker_running = not self.mouse_clicker_running
            logger.info("Clicker do mouse: %s.", "ligado" if self.mouse_clicker_running else "desligado")
            return self.mouse_clicker_running

    def reset_manual_clicker(self, mouse=False):
        """Limpa o acionamento manual ao mudar o modo, preservando as farms."""
        with self._exclusive_lock:
            if mouse:
                self.mouse_clicker_running = self.mouse_hold_active = False
            else:
                self.cookie_hold_active = False
                if self._simple_farm_active:
                    self._simple_farm_manual_clicker = False
                    self.set_simple_farm_clicker(self._simple_farm_clicker_requested)
                elif self._exclusive_owner is None:
                    self.ensure_clicker_stopped()

    def ensure_clicker_running(self) -> bool:
        """Habilita o clicker de forma idempotente para a fase de produção."""
        with self._clicker_state_lock:
            if self.stop_event.is_set() or self.paused.is_set():
                logger.warning("Clicker não foi habilitado porque o runner está encerrando")
                return False
            if self.is_running:
                return True
            if not self.update_cookie_position():
                return False
            self.is_running = True
        logger.info("Clicker habilitado por uma automação controlada")
        if self.on_clicker_state_change:
            try:
                self.on_clicker_state_change(True)
            except Exception as error:
                logger.error(f"Erro no callback de estado do clicker: {error}")
        return True

    @property
    def exclusive_owner(self) -> Optional[str]:
        """Nome da automação que detém exclusividade, se houver."""
        with self._exclusive_lock:
            return self._exclusive_owner

    def acquire_exclusive(self, owner: str) -> bool:
        """Pausa o detector compartilhado e reserva ações mutáveis para ``owner``."""
        if not owner:
            return False
        with self._exclusive_lock:
            if self._simple_farm_active or self._exclusive_owner not in (None, owner):
                return False
            self._exclusive_owner = owner
            self.cookie_hold_active = self.mouse_hold_active = False
            self.mouse_clicker_running = False
        self.ensure_clicker_stopped()
        logger.info("Modo exclusivo adquirido por %s", owner)
        return True

    def acquire_simple_farm(self) -> bool:
        """Reserva apenas GC/Grimoire; detector, Garden e Banco continuam ativos."""
        with self._exclusive_lock:
            if self._exclusive_owner is not None or self._simple_farm_active:
                return False
            self._simple_farm_active = True
            self._simple_farm_manual_clicker = self.is_running
            self._simple_farm_clicker_requested = False
            return True

    def set_simple_farm_clicker(self, enabled: bool) -> bool:
        with self._exclusive_lock:
            if not self._simple_farm_active:
                return False
            self._simple_farm_clicker_requested = enabled
            desired = enabled or self._simple_farm_manual_clicker
            return self.ensure_clicker_running() if desired else self.ensure_clicker_stopped()

    def release_simple_farm(self) -> None:
        with self._exclusive_lock:
            if self._simple_farm_active:
                self.set_simple_farm_clicker(False)
                self._simple_farm_active = False

    def release_exclusive(self, owner: str) -> bool:
        """Libera a reserva sem religar automaticamente nenhuma automação."""
        with self._exclusive_lock:
            if self._exclusive_owner != owner:
                return False
            self._exclusive_owner = None
        if owner in {"save_scum", "backup_restore"}:
            self.reset_krumblor_schedule()
            self._next_wrinkler_check = 0.0
            with self._cash_request_lock:
                self._cash_requests.clear()
        logger.info("Modo exclusivo liberado por %s", owner)
        return True

    def ensure_clicker_stopped(self) -> bool:
        """Desabilita o clicker de forma idempotente durante transições seguras."""
        with self._clicker_state_lock:
            if not self.is_running:
                return True
            self.is_running = False
        logger.info("Clicker desabilitado por uma automação controlada")
        if self.on_clicker_state_change:
            try:
                self.on_clicker_state_change(False)
            except Exception as error:
                logger.error(f"Erro no callback de estado do clicker: {error}")
        return True

    def detector_loop(self) -> None:
        """Thread dedicada às coletas e automações baseadas no runtime."""
        logger.debug("Detector: thread iniciada")

        while not self.stop_event.is_set():
            try:
                if self.paused.is_set() or self.exclusive_owner is not None:
                    # O dono exclusivo usa a mesma bridge e decide quais ações
                    # são seguras; o detector comum permanece totalmente passivo.
                    time.sleep(app_config.detect_interval)
                    continue
                # A exclusividade aguarda todo o ciclo de ações em andamento.
                with self._exclusive_lock:
                    if self._exclusive_owner is None and not self.paused.is_set():
                        self._run_detector_cycle()

                # Só acelera o polling enquanto o próximo carinho estiver próximo.
                delay = app_config.detect_interval
                if automation_config.enable_krumblor_upgrades and self._next_krumblor_check > 0:
                    delay = min(delay, max(0.01, self._next_krumblor_check - time.monotonic()))
                self.stop_event.wait(delay)

            except Exception as e:
                logger.error(f"Erro na thread detector: {e}")
                time.sleep(1)

    def _run_detector_cycle(self):
        if self.paused.is_set():
            return
        # A mesma trava aguarda uma coleta/cast em andamento ao iniciar o farm.
        with self._exclusive_lock:
            if not self._simple_farm_active and self._exclusive_owner is None:
                if automation_config.enable_golden_cookie and self.bridge.pop_golden_cookie():
                    self.golden_cookies_clicked += 1
                    self._collection_summary.record("Golden Cookies")
                self._run_grimoire_cycle()

        # Verificar fortune cookie
        if not self.paused.is_set() and automation_config.enable_fortune_cookie and self.bridge.click_fortune():
            self._collection_summary.record("Fortunes")

        # Verificar rena
        if not self.paused.is_set() and automation_config.enable_reindeer and self.bridge.pop_reindeer():
            self.reindeer_popped += 1
            self._collection_summary.record("Renas")

        self._run_wrinkler_cycle()

        self._run_sugar_lump_cycle()
        self._run_krumblor_cycle()

    def request_wrinkler_cash(self, source, target=0, seed=None, ttl=120):
        """Pedido temporário de uma ação real bloqueada por falta de cookies."""
        import math
        with self._cash_request_lock:
            self._cash_requests.pop(source, None)
            if seed and math.isfinite(target) and target > 0 and not self.paused.is_set():
                self._cash_requests[source] = dict(source=source, target=target, seed=seed,
                                                   expires=time.monotonic() + ttl)

    def _run_wrinkler_cycle(self, now=None):
        if (self.paused.is_set() or self.stop_event.is_set() or self.exclusive_owner is not None
                or not automation_config.enable_wrinkler_popper):
            return False
        current = time.monotonic() if now is None else now
        if current < self._next_wrinkler_check:
            return False
        self._next_wrinkler_check = current + 2.0
        with self._cash_request_lock:
            self._cash_requests = {k: v for k, v in self._cash_requests.items() if v['expires'] > current}
            requests = [dict(v) for v in self._cash_requests.values()]
        result = self.bridge.manage_wrinklers(automation_config.wrinkler_free_slots, requests)
        if not isinstance(result, dict):
            return False
        with self._cash_request_lock:
            for source in result.get('funded', []):
                # Não apaga um pedido mais recente enviado durante a chamada à bridge.
                sent = next((v for v in requests if v['source'] == source), None)
                if self._cash_requests.get(source) == sent:
                    self._cash_requests.pop(source, None)
        popped = result.get('popped', [])
        self.wrinklers_popped += len(popped)
        vacancies = sum(v['reason'] == 'vacancy' for v in popped)
        if vacancies:
            for _ in range(vacancies):
                self._collection_summary.record("Wrinklers (vagas para Shiny)")
        cash = sum(v['reason'] == 'cash' for v in popped)
        if cash:
            logger.info("Wrinklers: %s normais coletados para liberar caixa para Garden/Banco; Shiny preservados.", cash)
        blocked = bool(result.get('blocked'))
        if blocked and not self._wrinkler_blocked:
            logger.info("Wrinklers: não há normais suficientes para abrir as vagas; Shiny permanecem protegidos.")
        self._wrinkler_blocked = blocked
        return bool(popped)

    def reset_krumblor_schedule(self):
        self._next_krumblor_check = 0.0
        self._last_krumblor_state = None

    def _run_krumblor_cycle(self, now=None):
        if (self.paused.is_set() or self.stop_event.is_set()
                or self.exclusive_owner is not None or not automation_config.enable_krumblor_upgrades):
            return False
        current = time.monotonic() if now is None else now
        if current < self._next_krumblor_check:
            return False
        # Reserva o prazo antes da chamada, inclusive se a bridge lançar erro.
        self._next_krumblor_check = current + 60
        result = self.bridge.collect_krumblor_upgrade()
        retry = result.get("retryAfterMs", 60000)
        if not isinstance(retry, (int, float)) or not 0 < retry <= 900000:
            retry = 60000
        if result.get("reason") == "petting":
            interval = min(5.0, max(0.05, automation_config.krumblor_pet_interval_seconds))
            remaining = result.get("windowRemainingMs", interval * 1000)
            if not isinstance(remaining, (int, float)) or not 0 < remaining <= 900000:
                remaining = interval * 1000
            retry = min(remaining, interval * 1000)
        completed = time.monotonic() if now is None else current
        self._next_krumblor_check = completed + max(0.05, retry / 1000)
        reason = result.get("reason")
        drop = result.get("drop", "upgrade")
        state = (reason, drop if reason != "complete" else None, result.get("collected"))
        if state != self._last_krumblor_state:
            if result.get("unlocked"):
                logger.info("Krumblor: %s liberado (%s/4). Não foi comprado. Próxima faixa: %s.",
                            drop, result.get("collected", "?"), result.get("nextWindow", "—"))
            elif reason == "waiting_window":
                logger.info("Krumblor: %s já liberado ou comprado; próxima faixa às %s.",
                            drop, result.get("nextWindow", "—"))
            elif reason == "petting":
                logger.info("Krumblor: coletando %s nesta faixa.", drop)
            else:
                logger.info("Krumblor: %s", result.get("message", "Aguardando."))
            self._last_krumblor_state = state
        return result.get("unlocked") is True

    def _run_sugar_lump_cycle(self):
        if self.paused.is_set() or not automation_config.enable_sugar_lump_harvest:
            return False
        status = self.bridge.get_sugar_lump_status()
        if not status or not status.get("mature") or status.get("overripe"):
            return False
        preserved = tuple(t for t in range(5) if getattr(automation_config, f"preserve_sugar_lump_type_{t}"))
        if status.get("type") in preserved and not status.get("ready"):
            return False
        if self.bridge.harvest_sugar_lump(preserved_types=preserved):
            self.sugar_lumps_harvested += 1
            logger.info("Sugar Lump %s colhido; colheita garantida=%s", status.get("typeName"), status.get("ready"))
            return True
        return False

    def _run_grimoire_cycle(self, now: Optional[float] = None) -> bool:
        """Tenta uma vez por segundo; a bridge decide atomicamente se a mana está cheia."""
        if self.paused.is_set() or not automation_config.enable_grimoire_spell_spam:
            self._last_grimoire_failure = None
            return False
        current_time = time.monotonic() if now is None else now
        if current_time - self._last_grimoire_attempt_at < 1.0:
            return False
        self._last_grimoire_attempt_at = current_time
        result = self.bridge.cast_grimoire_spell_when_full(
            automation_config.grimoire_spell_id
        )
        if result.get("cast") is True:
            logger.info(f"Grimoire: {result.get('spellName', 'skill')} usada com mana máxima.")
            self._last_grimoire_failure = None
            return True
        if result.get("reason") == "waiting_mana":
            self._last_grimoire_failure = None
            return False
        failure = (result.get("reason"), result.get("message"))
        if failure != self._last_grimoire_failure:
            logger.warning(f"Grimoire: {failure[1] or 'não foi possível usar a skill'}")
            self._last_grimoire_failure = failure
        return False

    def clicker_loop(self) -> None:
        """Thread dedicada para clicar no cookie principal."""
        logger.debug("Clicker: thread iniciada; atalho %s", app_config.toggle_key)

        deadlines = {"cookie": 0.0, "mouse": 0.0}
        previous_keys = {"cookie": app_config.toggle_key, "mouse": app_config.mouse_toggle_key}
        previous_modes = {"cookie": app_config.clicker_mode, "mouse": app_config.mouse_clicker_mode}
        held = {"cookie": False, "mouse": False}
        hold_started = {"cookie": False, "mouse": False}
        while not self.stop_event.is_set():
            try:
                keys = {"cookie": app_config.toggle_key, "mouse": app_config.mouse_toggle_key}
                modes = {"cookie": app_config.clicker_mode, "mouse": app_config.mouse_clicker_mode}
                for mode, key in keys.items():
                    down = self.input_handler.is_key_pressed(key)
                    if key != previous_keys[mode] or modes[mode] != previous_modes[mode]:
                        previous_keys[mode], held[mode] = key, down
                        previous_modes[mode] = modes[mode]
                        hold_started[mode] = False
                    manual_allowed = (not self.paused.is_set() and not self.hotkey_capture_active.is_set()
                                      and self._exclusive_owner is None)
                    if not down or not manual_allowed:
                        hold_started[mode] = False
                    if down and not held[mode] and manual_allowed:
                        if modes[mode] == "toggle":
                            self.toggle_clicker() if mode == "cookie" else self.toggle_mouse_clicker()
                        else:
                            hold_started[mode] = mode == "mouse" or bool(self.cookie_position) or self.update_cookie_position()
                    setattr(self, "cookie_hold_active" if mode == "cookie" else "mouse_hold_active",
                            modes[mode] == "hold" and hold_started[mode] and down and manual_allowed)
                    held[mode] = down
                # Uma única fila envia down/up completos de cada clique.
                now = time.monotonic()
                allowed = not self.paused.is_set() and not self.hotkey_capture_active.is_set()
                active = {"cookie": (self.is_running or self.cookie_hold_active) and allowed,
                          "mouse": (self.mouse_clicker_running or self.mouse_hold_active) and allowed and self._exclusive_owner is None}
                for mode, enabled in active.items():
                    if not enabled:
                        deadlines[mode] = now
                        continue
                    if now < deadlines[mode]:continue
                    if mode == "cookie":
                        self.input_handler.click_cookie()
                        self.cookies_clicked += 1
                        interval = app_config.click_interval
                    else:
                        # Leituras lentas do detector não bloqueiam os cliques no cookie.
                        acquired = self._exclusive_lock.acquire(blocking=False)
                        interval = 0.01
                        if acquired:
                            try:
                                if (self._exclusive_owner is None and (self.mouse_clicker_running or self.mouse_hold_active)
                                        and not self.paused.is_set() and not self.hotkey_capture_active.is_set()):
                                    self.mouse_clicker_over_game = self.input_handler.click_at_cursor()
                                    if self.mouse_clicker_over_game:self.mouse_clicks += 1
                                    interval = app_config.mouse_click_interval
                            finally:
                                self._exclusive_lock.release()
                    deadlines[mode] = time.monotonic() + interval
                due = [deadlines[mode] - time.monotonic() for mode in active if active[mode]]
                self.stop_event.wait(min(0.01, max(0.001, min(due))) if due else 0.01)
            except Exception as error:
                logger.error("Erro na thread clicker: %s", error)
                self.stop_event.wait(0.1)

    def start(self) -> None:
        """Inicia as threads de automação em background."""
        logger.debug("Preparando threads de automação")

        # Iniciar threads
        self.detector_thread = threading.Thread(target=self.detector_loop, daemon=True, name="Detector")
        self.clicker_thread = threading.Thread(target=self.clicker_loop, daemon=True, name="Clicker")

        self.detector_thread.start()
        self.clicker_thread.start()

        logger.debug("Threads de automação prontas; execução depende do controle geral")

    def stop(self) -> None:
        """Para todas as threads."""
        self.stop_event.set()
        self._collection_summary.flush()
        logger.info("Automações paradas")


if __name__ == "__main__":
    pid = find_cookie_window()
    if not pid:
        logger.error("Nenhuma janela do Cookie Clicker encontrada!")
        exit(1)

    logger.info(f"PID encontrado: {pid}")

    # Conectar bridge
    bridge = CookieClickerBridge()
    if not bridge.connect():
        logger.error("Falha ao conectar ao bridge JS. Saindo.")
        exit(1)

    # Criar e iniciar runner
    runner = AutomationRunner(pid=pid, bridge=bridge)
    runner.start()
