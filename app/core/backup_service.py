"""Captura e restaura backups diretamente pelo runtime do jogo."""
from dataclasses import dataclass
import base64
from urllib.parse import unquote

@dataclass
class BackupResult:
    ok: bool
    message: str
    backup: object = None
    recovery: object = None
    safe_to_resume: bool = True

def save_identity(save):
    try:
        raw = base64.b64decode(unquote(save.strip()).split('!END!')[0], validate=True).decode('utf-8')
        parts = raw.split('|')
        stats = parts[2].split(';')
        version = float(parts[0])
        if len(parts) < 5 or version < 2 or not stats[4]:
            raise ValueError()
        return (stats[4], int(stats[0]), int(stats[1]))
    except (ValueError, IndexError, UnicodeError, TypeError) as error:
        raise ValueError('Arquivo de save inválido ou versão não suportada.') from error

class BackupService:
    def __init__(self, bridge, manager):
        self.bridge, self.manager = bridge, manager

    def capture(self, name=''):
        try:
            save = self.bridge.get_game_save()
            if not save:
                raise RuntimeError('Não foi possível obter o save do jogo. Verifique a conexão.')
            save_identity(save)
            backup = self.manager.create_backup(save, name)
            return BackupResult(True, f'Backup salvo: {backup.display_name}', backup)
        except Exception as error:
            return BackupResult(False, str(error))

    def import_file(self, file_path, name=''):
        from pathlib import Path
        try:
            source = Path(file_path)
            save = source.read_text(encoding='utf-8-sig').strip()
            save_identity(save)
            backup = self.manager.create_backup(save, name or source.stem)
            return BackupResult(True, f'Arquivo adicionado: {backup.display_name}', backup)
        except Exception as error:
            return BackupResult(False, str(error))

    def _load_verified(self, save):
        expected = save_identity(save)
        if not self.bridge.load_game_save(save):
            raise RuntimeError('O jogo rejeitou a restauração ou não confirmou a importação.')
        actual = self.bridge.get_game_save()
        if not actual or save_identity(actual) != expected:
            raise RuntimeError('O save carregado não corresponde ao backup selecionado.')
        if not self.bridge.persist_game_save():
            raise RuntimeError('Não foi possível confirmar a gravação do save restaurado.')

    def restore(self, backup, *, protect_paths=()):
        recovery = None
        previous = None
        touched = False
        try:
            selected = self.manager.load_backup_data(backup)
            save_identity(selected)
            previous = self.bridge.get_game_save()
            if not previous:
                raise RuntimeError('Não foi possível salvar o estado atual antes de carregar.')
            save_identity(previous)
            recovery = self.manager.create_backup(previous, 'antes-da-restauracao', protect_paths=(backup.file_path, *protect_paths))
            touched = True
            self._load_verified(selected)
            return BackupResult(True, f'Backup carregado no jogo: {backup.display_name}', backup, recovery)
        except Exception as error:
            if touched:
                try:
                    self._load_verified(previous)
                    return BackupResult(False, f'{error} O estado anterior foi recuperado.', recovery=recovery)
                except Exception as rollback_error:
                    return BackupResult(False, f'{error} Recuperação pendente: {rollback_error}. Use o backup anterior para recuperar.', recovery=recovery, safe_to_resume=False)
            return BackupResult(False, str(error), recovery=recovery)
