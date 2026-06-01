from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class BackupEntry:
    """Represents a single save backup entry."""
    name: str
    timestamp: datetime
    file_path: Path

    @property
    def display_name(self) -> str:
        """Format name with timestamp for display."""
        return f"{self.name} ({self.timestamp.strftime('%Y-%m-%d %H:%M:%S')})"

    @classmethod
    def from_file(cls, file_path: Path) -> 'BackupEntry':
        """Create BackupEntry from a backup file."""
        # Expected format:
        # backup_YYYY-MM-DD_HH-MM-SS_name.ext

        stem = file_path.stem

        if not stem.startswith("backup_"):
            raise ValueError(f"Invalid backup filename: {file_path}")

        # Remove prefix
        rest = stem[len("backup_"):]

        # Split only the first 2 underscores:
        # YYYY-MM-DD
        # HH-MM-SS
        # remaining name
        parts = rest.split('_', 2)

        if len(parts) != 3:
            raise ValueError(f"Invalid backup filename: {file_path}")

        date_str, time_str, name = parts

        timestamp_str = f"{date_str} {time_str.replace('-', ':')}"
        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')

        return cls(
            name=name,
            timestamp=timestamp,
            file_path=file_path
        )