"""Armazenamento de backups com nomes seguros e compatibilidade com saves antigos."""
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta, timezone
import re
from app.models.backup import BackupEntry
from app.config.settings import backup_config
from app.utils.logger import logger

class BackupManager:
    def __init__(self):
        self.backup_dir = Path(backup_config.backup_folder)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, save_data: str, name: str = "", *, protect_paths=()) -> BackupEntry:
        if not isinstance(save_data, str) or not save_data.strip():
            raise ValueError("O jogo não forneceu um save válido.")
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', str(name or '').strip()).strip(' .')[:80] or 'Backup'
        timestamp = datetime.now(timezone(timedelta(hours=-3))).replace(tzinfo=None)
        prefix = f"backup_{timestamp.strftime('%Y-%m-%d_%H-%M-%S-%f')}_"
        suffix = 1
        while True:
            display_name = name if suffix == 1 else f"{name} ({suffix})"
            file_path = self.backup_dir / f"{prefix}{display_name}.txt"
            try:
                with file_path.open('x', encoding='utf-8') as stream:
                    stream.write(save_data.strip())
                break
            except FileExistsError:
                suffix += 1
        backup = BackupEntry(display_name, timestamp, file_path)
        logger.info("Backup salvo: %s", backup.display_name)
        self.cleanup_old_backups(protect_paths=(*protect_paths, file_path))
        return backup

    def list_backups(self) -> List[BackupEntry]:
        backups = []
        for file_path in self.backup_dir.glob('backup_*.txt'):
            try:
                backups.append(BackupEntry.from_file(file_path))
            except ValueError:
                logger.warning("Nome de backup inválido ignorado: %s", file_path.name)
        return sorted(backups, key=lambda backup: backup.timestamp, reverse=True)

    def get_backup_by_name(self, name: str) -> Optional[BackupEntry]:
        return next((backup for backup in self.list_backups() if backup.name == name), None)

    def _checked_path(self, backup):
        path = Path(backup.file_path).resolve()
        if path.parent != self.backup_dir.resolve():
            raise ValueError("O arquivo não pertence à pasta de backups.")
        return path

    def load_backup_data(self, backup: BackupEntry) -> str:
        return self._checked_path(backup).read_text(encoding='utf-8').strip()

    def delete_backup(self, backup: BackupEntry) -> bool:
        try:
            self._checked_path(backup).unlink()
            return True
        except (OSError, ValueError) as error:
            logger.warning("Não foi possível excluir backup: %s", error)
            return False

    def cleanup_old_backups(self, max_backups=None, *, protect_paths=()):
        maximum = max(1, int(backup_config.max_backups if max_backups is None else max_backups))
        backups = self.list_backups()
        protected = {Path(p).resolve() for p in protect_paths}
        remaining = len(backups)
        for backup in reversed(backups):
            if remaining <= maximum:
                break
            if backup.file_path.resolve() not in protected and self.delete_backup(backup):
                remaining -= 1
