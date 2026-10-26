"""Localiza a instalação Steam e inicia Cookie Clicker com CDP local."""
from dataclasses import dataclass
from pathlib import Path
import csv
import io
import json
import os
import re
import subprocess
import threading
import time
from urllib.request import urlopen
from app.bridge.js_bridge import CookieClickerBridge
from app.config.settings import app_config
from app.core.window_finder import find_cookie_window

@dataclass
class GameLaunchResult:
    ok: bool
    message: str
    bridge: object = None
    pid: int | None = None
    executable: str = ''
    reason: str = ''
    snapshot: dict | None = None


def steam_roots():
    roots = []
    try:
        import winreg
        for hive, key, value in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                                 (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath')):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    roots.append(Path(winreg.QueryValueEx(handle, value)[0]))
            except OSError:
                pass
    except ImportError:
        pass
    for base in (os.environ.get('ProgramFiles(x86)'), os.environ.get('ProgramFiles')):
        if base:
            roots.append(Path(base) / 'Steam')
    roots.extend((Path('D:/Steam'), Path('C:/Steam')))
    return list(dict.fromkeys(roots))


def find_game_executable(configured=''):
    if configured:
        selected = Path(configured)
        if selected.is_file() and selected.name.casefold() == 'cookie clicker.exe':
            return selected
    libraries = list(steam_roots())
    for root in list(libraries):
        try:
            content = (root / 'steamapps/libraryfolders.vdf').read_text(encoding='utf-8')
            libraries.extend(Path(p.replace('\\\\', '\\')) for p in re.findall(r'"path"\s+"([^"]+)"', content))
        except OSError:
            pass
    for library in dict.fromkeys(libraries):
        folder = 'Cookie Clicker'
        try:
            manifest = (library / 'steamapps/appmanifest_1454400.acf').read_text(encoding='utf-8')
            match = re.search(r'"installdir"\s+"([^"]+)"', manifest)
            if match:
                folder = match[1]
        except OSError:
            pass
        candidate = library / 'steamapps/common' / folder / 'Cookie Clicker.exe'
        if candidate.is_file():
            return candidate
    return None


def cookie_process_running():
    if find_cookie_window():
        return True
    if os.name != 'nt':
        return False
    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Cookie Clicker.exe', '/FO', 'CSV', '/NH'],
                            capture_output=True, text=True, errors='replace', timeout=5,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return any(row and row[0].casefold() == 'cookie clicker.exe' for row in csv.reader(io.StringIO(result.stdout)))

class GameLauncher:
    def __init__(self, *, configured='', timeout=45, bridge_factory=CookieClickerBridge):
        self.configured = configured
        self.timeout = timeout
        self.bridge_factory = bridge_factory
        self.cancel = threading.Event()
        self.connected_bridge = None

    def stop(self):
        self.cancel.set()

    def _game_tab(self):
        try:
            with urlopen(f'http://{app_config.remote_debugging_host}:{app_config.remote_debugging_port}/json/list', timeout=0.75) as response:
                tabs = json.load(response)
            for tab in tabs:
                url = str(tab.get('url', '')).lower()
                if tab.get('type') == 'page' and ('cookieclicker/' in url or ('cookie%20clicker/' in url and 'index.html' in url) or ('cookie clicker/' in url and 'index.html' in url)):
                    return tab.get('id')
        except (OSError, ValueError, TypeError):
            pass
        return None

    def _connect(self):
        if self.cancel.is_set():
            return None
        tab_id = self._game_tab()
        pid = find_cookie_window() if tab_id else None
        if not tab_id or not pid:
            return None
        bridge = self.bridge_factory(timeout=2)
        try:
            if bridge.connect(tab_id=tab_id) and bridge.execute_js("!!(globalThis.Game && Game.ready && Game.Objects && typeof Game.WriteSave==='function')") is True:
                snapshot = bridge.get_connection_snapshot()
                if not isinstance(snapshot, dict) or not isinstance(snapshot.get('identity'), str):
                    bridge.disconnect()
                    return None
                if self.cancel.is_set():
                    bridge.disconnect()
                    return None
                self.connected_bridge = bridge
                return GameLaunchResult(True, 'Jogo conectado ao debugger.', bridge, pid, snapshot=snapshot)
        except Exception:
            pass
        bridge.disconnect()
        return None

    def connect_existing(self):
        if self.cancel.is_set():
            return GameLaunchResult(False, 'Conexão cancelada.', reason='cancelled')
        return self._connect() or GameLaunchResult(False, 'Abra o jogo pelo botão Abrir jogo para habilitar o debugger.', reason='not_connected')

    def launch(self):
        if self.cancel.is_set():
            return GameLaunchResult(False, 'Abertura cancelada.', reason='cancelled')
        existing = self._connect()
        if existing:
            return existing
        if cookie_process_running():
            return GameLaunchResult(False, 'O jogo já está aberto sem um debugger disponível. Salve e feche o jogo; depois use Abrir jogo. Não é possível adicionar esse argumento a um processo já aberto.', reason='already_running')
        executable = find_game_executable(self.configured)
        if executable is None:
            return GameLaunchResult(False, 'Selecione Cookie Clicker.exe na instalação Steam.', reason='missing_executable')
        if self.cancel.is_set():
            return GameLaunchResult(False, 'Abertura cancelada.', reason='cancelled')
        subprocess.Popen([str(executable), f'--remote-debugging-port={app_config.remote_debugging_port}'], cwd=str(executable.parent))
        deadline = time.monotonic() + self.timeout
        while not self.cancel.is_set() and time.monotonic() < deadline:
            connected = self._connect()
            if connected:
                connected.executable = str(executable)
                return connected
            self.cancel.wait(0.5)
        return GameLaunchResult(False, 'Abertura cancelada.' if self.cancel.is_set() else 'O jogo foi iniciado, mas o debugger não ficou pronto. Verifique se a Steam está aberta e use Abrir jogo para tentar conectar novamente.', executable=str(executable), reason='cancelled' if self.cancel.is_set() else 'timeout')
