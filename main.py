#!/usr/bin/env python3
"""Inicializa a interface mesmo com o jogo fechado; conexão em background."""
import sys
import signal
import time
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QFileDialog
from app.config.settings import (app_config, load_app_settings, save_app_settings,
                                 load_automation_settings, save_automation_settings,
                                 load_backup_settings)
from app.core.game_launcher import GameLauncher
from app.core.window_finder import find_cookie_window
from app.core.run import AutomationRunner
from app.ui.main_window import create_ui_app, StockMarketWorker
from app.utils.logger import logger, add_ui_handler

class Application:
    def __init__(self):
        self.app = self.window = self.bridge = self.runner = self.pid = None
        self.launcher = self.launch_worker = None
        self._closing = False
        self._enable_after_connect = False
        self.health_worker = None
        self._recovering = False
        self._recover_resume = False
        self._recover_cookie = False
        self._recover_special = False
        self._connection_identity = None
        self._retry_at = 0.0
        self._retry_delay = 2.0
        self._automatic_connect = False

    def initialize(self):
        load_app_settings()
        load_automation_settings()
        load_backup_settings()
        self.app, self.window = create_ui_app()
        add_ui_handler(self.window.log_emitter)
        self.window.open_game_requested.connect(self.open_game)
        self.window.game_connection_shutdown = self._stop_game_connection
        self.app.aboutToQuit.connect(self.cleanup)
        self.game_state_timer = QTimer(self.window)
        self.game_state_timer.timeout.connect(self._refresh_game_state)
        self.game_state_timer.start(2000)
        return True

    def connect_existing(self):
        self._connect(launch=False)

    def _refresh_game_state(self):
        if self.launch_worker or self._closing:
            return
        current_pid = find_cookie_window()
        self.window._game_open = bool(current_pid)
        if (self.bridge or self.window._bot_enabled) and not self._recovering and (current_pid != self.pid or not self.bridge or not self.bridge.connected):
            self._begin_recovery()
        if self._recovering:
            self.window.set_connection_recovery(True, self._recover_resume)
            if (current_pid and time.monotonic() >= self._retry_at
                    and not self._old_operations_running()):
                self._connect(launch=False, automatic=True)
        elif self.bridge and current_pid == self.pid and not self.health_worker:
            bridge, pid = self.bridge, self.pid
            worker = StockMarketWorker(bridge.get_connection_snapshot, self.window)
            self.health_worker = worker
            worker.completed.connect(lambda snapshot: self._health_completed(bridge, pid, snapshot))
            worker.failed.connect(lambda _: self._health_completed(bridge, pid, None))
            worker.finished.connect(self._health_finished)
            worker.start()
        elif current_pid and not self.bridge and time.monotonic() >= self._retry_at:
            self._connect(launch=False, automatic=True)
        if not current_pid:
            self.window.update_bridge_status(False)
        self.window.refresh_bot_control()

    def _health_completed(self, bridge, pid, snapshot):
        if self._closing or bridge is not self.bridge or pid != self.pid or self._recovering:
            return
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get('identity'), str):
            self._begin_recovery()
        else:
            # Ascensão e importações legítimas podem mudar a identidade enquanto conectado.
            self._connection_identity = snapshot['identity']

    def _health_finished(self):
        worker, self.health_worker = self.health_worker, None
        if worker:
            worker.deleteLater()

    def _old_operations_running(self):
        if self.window._bot_workers_running():
            return True
        for worker in (self.health_worker, self.window._sugar_lump_worker,
                       self.window.backup_dialog.worker if self.window.backup_dialog else None):
            if worker and worker.isRunning():
                return True
        if self.runner:
            for thread in (self.runner.detector_thread, self.runner.clicker_thread):
                if thread and thread.is_alive():
                    return True
        return False

    def _begin_recovery(self):
        if self._recovering or self._closing:
            return
        self._recovering = True
        self._recover_resume = bool(self.window._bot_enabled)
        self._recover_special = bool(self.window._combo_worker or self.window._auto_ascension_worker
                                     or self.window._save_scum_exclusive)
        self._recover_cookie = bool(self.runner and self.runner.is_running
                                    and not self.runner._simple_farm_active and not self._recover_special
                                    and app_config.clicker_mode == 'toggle')
        if self.bridge:
            self.bridge.managed_connection = True
            self.bridge.connected = False
        if self.window._bot_enabled:
            self.window.set_bot_enabled(False)
        if self.runner:
            self.runner.set_paused(True)
            self.runner.stop()
        self.window._resume_clicker = self.window._resume_mouse_clicker = False
        self.window.update_bridge_status(False)
        self.window.set_connection_recovery(True, self._recover_resume)
        self.window.add_log('Conexão perdida. Ações pausadas; aguardando o jogo para reconectar.')
        self._retry_at = 0.0
        self._retry_delay = 2.0

    def open_game(self):
        if self._recovering and self.window._game_open:
            self._recover_resume = False
            self.window.set_connection_recovery(True, False)
            self.window.add_log("Retomada automática cancelada. O jogo continuará sendo reconectado.")
            return
        if self.window._bot_enabled:
            self.window.set_bot_enabled(False)
        elif self.window._game_open:
            if self.bridge and self.bridge.connected and self.runner and find_cookie_window() == self.pid:
                self.window.set_bot_enabled(True)
            else:
                self._enable_after_connect = True
                self._connect(launch=False)
        else:
            self._enable_after_connect = False
            self._connect(launch=True)

    def _connect(self, *, launch, automatic=False):
        if self.launch_worker or self._closing:
            return
        self._automatic_connect = automatic
        self.launcher = GameLauncher(configured=app_config.game_executable_path)
        self.launch_worker = StockMarketWorker(self.launcher.launch if launch else self.launcher.connect_existing, self.window)
        self.launch_worker.completed.connect(self._connection_completed)
        self.launch_worker.failed.connect(self._connection_failed)
        self.launch_worker.finished.connect(self._connection_finished)
        self.window._connection_busy = True
        self.window.open_game_button.setEnabled(False)
        self.window.open_game_button.setText('Abrindo…' if launch else 'Conectando…')
        if not automatic:
            self.window.add_log('Abrindo jogo com debugger…' if launch else 'Procurando jogo com debugger…')
        self.launch_worker.start()

    def _connection_completed(self, result):
        if self._closing:
            if result.bridge:
                result.bridge.disconnect()
            return
        if result.executable:
            app_config.game_executable_path = result.executable
            save_app_settings()
        if not result.ok:
            self._retry_at = time.monotonic() + self._retry_delay
            self._retry_delay = min(30.0, self._retry_delay * 2)
            if not self._recovering and not self._automatic_connect:
                self.window.add_log(result.message)
            self.window.update_bridge_status(False)
            if result.reason == 'missing_executable':
                QTimer.singleShot(0, self._choose_executable)
            return
        if self._recovering and (self._old_operations_running() or find_cookie_window() != result.pid):
            result.bridge.disconnect()
            return
        if not self._recovering and self.pid == result.pid and self.runner and self.bridge and self.bridge.connected:
            result.bridge.disconnect()
            self.window.update_bridge_status(True)
            if self._enable_after_connect:
                self.window.set_bot_enabled(True)
            self.window.add_log('Jogo já conectado; nenhuma instância adicional foi aberta.')
            return
        if self.runner:
            self.runner.stop()
        if self.bridge:
            self.bridge.disconnect()
        recovering = self._recovering
        previous_runner = self.runner
        previous_identity = self._connection_identity
        self.bridge, self.pid = result.bridge, result.pid
        self.bridge.managed_connection = True
        self._connection_identity = (result.snapshot or {}).get("identity")
        try:
            self.runner = AutomationRunner(pid=self.pid, bridge=self.bridge,
                                           state_change_callback=self.window.clicker_state_changed.emit)
            if recovering and previous_runner:
                for field in ('cookies_clicked', 'mouse_clicks', 'golden_cookies_clicked',
                              'reindeer_popped', 'wrinklers_popped', 'sugar_lumps_harvested'):
                    value = getattr(previous_runner, field, 0)
                    if isinstance(value, int):
                        setattr(self.runner, field, value)
            self.window.attach_game(self.bridge, self.runner)
            self.runner.require_fresh_hotkeys = recovering
            self.runner.start()
            self._recovering = False
            self._retry_at = 0.0
            self._retry_delay = 2.0
            self.window.set_connection_recovery(False)
            if recovering:
                if self.window._save_scum_exclusive:
                    self.runner.acquire_exclusive(self.window._exclusive_session_owner)
                    if self.window.save_scum_tab.automation:
                        self.window.save_scum_tab.automation.bridge = self.bridge
                same_save = previous_identity is not None and previous_identity == self._connection_identity
                safe = (same_save and not (result.snapshot or {}).get('ascending', True)
                        and not self._recover_special and not self.window._save_scum_exclusive
                        and not self.window._combo_exclusive)
                self.window._resume_clicker = self._recover_cookie and safe
                self.window._resume_mouse_clicker = False
                if self._recover_resume and safe:
                    self.window.set_bot_enabled(True)
                    self.window.add_log('Conexão recuperada. Estado atualizado; automações retomadas.')
                else:
                    self.window.add_log('Conexão recuperada. Bot pausado: ' +
                                        ('confira a ação interrompida antes de ligar.' if self._recover_special else
                                         'o save mudou ou o jogo está em ascensão; confira antes de ligar.' if not safe else
                                         'a pausa foi mantida.'))
                self._recover_resume = False
            if self._enable_after_connect and not recovering:
                self.window.set_bot_enabled(True)
            if not recovering:
                self.window.add_log('Jogo conectado. Debugger ativo na porta ' + str(app_config.remote_debugging_port) + '.')
        except Exception as error:
            if self.runner:
                self.runner.set_paused(True)
                self.runner.stop()
            self.bridge.disconnect()
            self._recovering = recovering
            if recovering:
                self._connection_identity = previous_identity
            self.window.set_connection_recovery(recovering, self._recover_resume)
            self._connection_failed(str(error))

    def _connection_failed(self, message):
        self._retry_at = time.monotonic() + self._retry_delay
        self._retry_delay = min(30.0, self._retry_delay * 2)
        self.window.update_bridge_status(False)
        if not self._recovering and not self._automatic_connect:
            self.window.add_log('Não foi possível conectar ao jogo: ' + message)

    def _connection_finished(self):
        worker, self.launch_worker = self.launch_worker, None
        self.window._connection_busy = False
        self._enable_after_connect = False
        self._refresh_game_state()
        if worker:
            worker.deleteLater()

    def _choose_executable(self):
        if self._closing:
            return
        executable, _ = QFileDialog.getOpenFileName(self.window, 'Localizar Cookie Clicker.exe', '', 'Cookie Clicker (Cookie Clicker.exe)')
        if executable:
            from pathlib import Path
            if Path(executable).name.casefold() != 'cookie clicker.exe':
                self.window.add_log('Selecione o executável Cookie Clicker.exe da instalação Steam.')
                return
            app_config.game_executable_path = executable
            save_app_settings()
            if self.launch_worker:
                self.window.add_log('Caminho salvo. Use Abrir jogo para continuar.')
            else:
                self.open_game()

    def run(self):
        if not self.initialize():
            return 1
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
        self.window.show()
        QTimer.singleShot(0, self.connect_existing)
        try:
            return self.app.exec_()
        except KeyboardInterrupt:
            self.shutdown()
            return 0

    def _stop_game_connection(self):
        if self.launcher:
            self.launcher.stop()
        if self.health_worker and self.health_worker.isRunning() and not self.health_worker.wait(5000):
            return False
        return self.launch_worker.wait(10000) if self.launch_worker and self.launch_worker.isRunning() else True

    def cleanup(self):
        self._closing = True
        self._stop_game_connection()
        if self.launcher and self.launcher.connected_bridge and self.launcher.connected_bridge is not self.bridge:
            self.launcher.connected_bridge.disconnect()
        if self.runner:
            self.runner.stop()
        if self.bridge:
            self.bridge.disconnect()
        save_app_settings()
        save_automation_settings()

    def shutdown(self, signum=None, frame=None):
        if self.window:
            self.window.close()
        else:
            self.cleanup()
            if self.app:
                self.app.quit()

def main():
    application = Application()
    sys.exit(application.run())

if __name__ == '__main__':
    main()
