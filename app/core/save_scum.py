"""Save scum de Sugar Lumps com checkpoint imutável e restauração verificada."""
from dataclasses import dataclass
import threading
from typing import Callable

LUMP_NAMES = ("Normal", "Bifurcado", "Dourado", "Carnudo", "Caramelizado")

@dataclass(frozen=True)
class SaveScumConfig:
    targets: tuple = (2, 4)
    max_attempts: int = 1000
    interval_seconds: float = 0.2

@dataclass(frozen=True)
class SaveScumReport:
    state: str
    message: str
    attempts: int = 0
    current_type: int | None = None
    backup_path: str = ""
    safe_to_resume: bool = True

class SaveScumAutomation:
    def __init__(self, bridge, backup_manager, config=SaveScumConfig()):
        self.bridge = bridge
        self.backups = backup_manager
        self.config = config
        self.stop = threading.Event()
        self.checkpoint = None
        self.backup_path = ""
        self.attempts = 0
        self.dirty = False
        self.last_start = None
        self.report = SaveScumReport("desligada", "Selecione os tipos e ligue para iniciar.")

    def parar(self):
        self.stop.set()

    def _report(self, state, message, current_type=None, safe=True):
        self.report = SaveScumReport(state, message, self.attempts, current_type, self.backup_path, safe)
        return self.report

    def gerar_previa(self):
        status = self.bridge.get_sugar_lump_status()
        if not status:
            return self._report("indisponível", "Sugar Lumps indisponíveis ou leitura inválida.")
        name = LUMP_NAMES[status['type']]
        if status['type'] in self.config.targets:
            return self._report("alvo encontrado", f"O lump atual já é {name}; preserve até a colheita garantida.", status['type'])
        if not status['mature']:
            return self._report("aguardando", f"Lump {name}: faltam {status['remainingMatureMs']/60000:.1f} min para maturar.", status['type'])
        return self._report("pronto", f"Lump {name} pronto para tentativa. " +
                            ("Colheita garantida." if status['ready'] else "Colheita antecipada: 50% de chance de não ganhar lumps."), status['type'])

    def _restore(self):
        result = self.bridge.restore_sugar_lump_checkpoint(self.checkpoint)
        if not result.get('ok'):
            raise RuntimeError(result.get('message', 'Falha ao restaurar o checkpoint'))
        self.dirty = False

    def recuperar(self):
        try:
            self._restore()
            return self._report("restaurado", "Backup inicial restaurado e verificado.")
        except Exception as error:
            return self._report("restauração pendente", str(error), safe=False)

    def executar(self, updated: Callable = lambda report: None):
        try:
            if not self.config.targets or any(t not in range(5) for t in self.config.targets):
                raise ValueError("Selecione pelo menos um tipo válido.")
            if self.config.max_attempts < 1 or self.config.interval_seconds < 0.05:
                raise ValueError("Limite e intervalo inválidos.")
            self.checkpoint = self.bridge.get_sugar_lump_checkpoint()
            if not self.checkpoint:
                raise RuntimeError("Não foi possível exportar um checkpoint válido.")
            status = self.checkpoint['status']
            if status['type'] in self.config.targets:
                return self._report("alvo encontrado", "O lump atual já é um alvo; nenhuma tentativa necessária.", status['type'])
            if not status['mature'] or status['remainingAutoMs'] < 30000:
                return self._report("aguardando", "O lump precisa estar maduro e ter pelo menos 30 segundos antes da colheita automática.", status['type'])
            backup = self.backups.create_backup(self.checkpoint['save'], "antes-do-save-scum")
            self.backup_path = str(backup.file_path)
            updated(self._report("rodando", "Backup inicial salvo; iniciando tentativas.", status['type']))
            while not self.stop.is_set() and self.attempts < self.config.max_attempts:
                if self.dirty:
                    self._restore()
                if self.stop.wait(self.config.interval_seconds):
                    break
                self.dirty = True  # Uma falha de transporte pode ocorrer após a colheita.
                result = self.bridge.harvest_sugar_lump_result(
                    preserved_types=self.config.targets, expected_start=status['started'],
                    after_start=self.last_start,
                )
                if not result.get('ok'):
                    if result.get('reason') == 'same_timestamp':
                        self._restore()
                        continue
                    raise RuntimeError(result.get('message', 'Colheita não confirmada'))
                self.attempts += 1
                self.last_start = result['newStart']
                new_type = result['newType']
                if new_type in self.config.targets:
                    found = self.bridge.get_sugar_lump_checkpoint()
                    if not found or found['status']['started'] != self.last_start or found['status']['type'] != new_type:
                        raise RuntimeError("O novo lump mudou antes de confirmar o resultado.")
                    self.backups.create_backup(found['save'], "save-scum-alvo-encontrado")
                    if not self.bridge.persist_game_save():
                        raise RuntimeError("Não foi possível gravar o resultado no save do jogo.")
                    self.dirty = False
                    return self._report("alvo encontrado", f"{LUMP_NAMES[new_type]} encontrado e salvo; aguardar a colheita garantida.", new_type)
                updated(self._report("rodando", f"Tentativa {self.attempts}: {LUMP_NAMES[new_type]}; restaurando o início.", new_type))
            if self.dirty:
                self._restore()
            return self._report("desligada", "Backup inicial restaurado. " +
                                ("Interrompido pelo usuário." if self.stop.is_set() else "Limite de tentativas atingido."), status['type'])
        except Exception as error:
            if self.dirty and self.checkpoint:
                try:
                    self._restore()
                except Exception as restore_error:
                    return self._report("restauração pendente", f"{error}. {restore_error}. Use Restaurar início ou o backup em disco.", safe=False)
            return self._report("erro", str(error))
