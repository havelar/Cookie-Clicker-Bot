import os
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from app.models.backup import BackupEntry
from app.config.settings import backup_config
from app.utils.logger import logger


class BackupManager:
    """Manages save backups for Cookie Clicker."""

    def __init__(self):
        self.backup_dir = Path(backup_config.backup_folder)
        self.backup_dir.mkdir(exist_ok=True)

    def create_backup(self, save_data: str, name: str) -> BackupEntry:
        """Create a new backup with the given save data and name."""
        timestamp = datetime.now()
        filename = f"backup_{timestamp.strftime('%Y-%m-%d_%H-%M-%S')}_{name}.txt"
        file_path = self.backup_dir / filename

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(save_data)

        backup = BackupEntry(name=name, timestamp=timestamp, file_path=file_path)
        logger.info(f"Created backup: {backup.display_name}")

        # Cleanup old backups after creating new one
        self.cleanup_old_backups()

        return backup

    def list_backups(self) -> List[BackupEntry]:
        """List all available backups, sorted by timestamp descending."""
        backups = []
        for file_path in self.backup_dir.glob("backup_*.txt"):
            try:
                backup = BackupEntry.from_file(file_path)
                backups.append(backup)
            except ValueError as e:
                logger.warning(f"Skipping invalid backup file {file_path}: {e}")

        # Sort by timestamp descending (newest first)
        backups.sort(key=lambda b: b.timestamp, reverse=True)
        return backups

    def get_backup_by_name(self, name: str) -> Optional[BackupEntry]:
        """Get a backup by its name."""
        backups = self.list_backups()
        for backup in backups:
            if backup.name == name:
                return backup
        return None

    def load_backup_data(self, backup: BackupEntry) -> str:
        """Load the save data from a backup file."""
        with open(backup.file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def delete_backup(self, backup: BackupEntry) -> bool:
        """Delete a backup file."""
        try:
            backup.file_path.unlink()
            logger.info(f"Deleted backup: {backup.display_name}")
            return True
        except OSError as e:
            logger.error(f"Failed to delete backup {backup.display_name}: {e}")
            return False

    def cleanup_old_backups(self, max_backups: int = None):
        """Remove oldest backups if exceeding max_backups."""
        if max_backups is None:
            max_backups = backup_config.max_backups
        backups = self.list_backups()
        if len(backups) > max_backups:
            to_delete = backups[max_backups:]
            for backup in to_delete:
                self.delete_backup(backup)
            logger.info(f"Cleaned up {len(to_delete)} old backups")