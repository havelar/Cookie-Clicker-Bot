#!/usr/bin/env python3
"""Inicializa a interface mesmo com o jogo fechado; conexão em background."""
import sys
import signal
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
        opened = bool(current_pid)
        if (not opened or current_pid != self.pid) and self.window._bot_enabled:
            self.window.set_bot_enabled(False)
        self.window._game_open = opened
        if not opened:
            self.window.update_bridge_status(False)
        self.window.refresh_bot_control()

    def open_game(self):
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

    def _connect(self, *, launch):
        if self.launch_worker or self._closing:
            return
        self.launcher = GameLauncher(configured=app_config.game_executable_path)
        self.launch_worker = StockMarketWorker(self.launcher.launch if launch else self.launcher.connect_existing, self.window)
        self.launch_worker.completed.connect(self._connection_completed)
        self.launch_worker.failed.connect(self._connection_failed)
        self.launch_worker.finished.connect(self._connection_finished)
        self.window._connection_busy = True
        self.window.open_game_button.setEnabled(False)
        self.window.open_game_button.setText('Abrindo…' if launch else 'Conectando…')
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
            self.window.add_log(result.message)
            self.window.update_bridge_status(False)
            if result.reason == 'missing_executable':
                QTimer.singleShot(0, self._choose_executable)
            return
        if self.pid == result.pid and self.runner and self.bridge and self.bridge.connected:
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
        self.bridge, self.pid = result.bridge, result.pid
        try:
            self.runner = AutomationRunner(pid=self.pid, bridge=self.bridge,
                                           state_change_callback=self.window.clicker_state_changed.emit)
            self.window.attach_game(self.bridge, self.runner)
            self.runner.start()
            if self._enable_after_connect:
                self.window.set_bot_enabled(True)
            self.window.add_log('Jogo conectado. Debugger ativo na porta ' + str(app_config.remote_debugging_port) + '.')
        except Exception as error:
            self.bridge.disconnect()
            self._connection_failed(str(error))

    def _connection_failed(self, message):
        self.window.update_bridge_status(False)
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
