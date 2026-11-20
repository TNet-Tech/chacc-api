"""
ChaCC Database Backup and Restore.

Provides backup and restore functionality for database migrations.
"""

import asyncio
import contextlib
import os
import shutil
import sqlite3
import subprocess
from contextlib import closing
from datetime import datetime, timezone

from src.constants import (
    DATABASE_ENGINE,
    DATABASE_HOST,
    DATABASE_NAME,
    DATABASE_PASSWORD,
    DATABASE_PORT,
    DATABASE_USER,
    MIGRATION_BACKUP_DIR,
    SQLITE_DB_PATH,
)
from src.logger import configure_logging, get_default_log_level

chacc_logger = configure_logging(log_level=get_default_log_level())

DEFAULT_BACKUP_DIR = MIGRATION_BACKUP_DIR

# Backups hold all of the application's data: readable by the server's user only.
_BACKUP_FILE_MODE = 0o600


def _copy_sqlite(source_path: str, target_path: str) -> None:
    """
    Copy with SQLite's online backup API: consistent even while the server has
    the database open, unlike copying the file.
    """
    with (
        closing(sqlite3.connect(source_path)) as source,
        closing(sqlite3.connect(target_path)) as target,
    ):
        source.backup(target)


class DatabaseBackup:
    """
    Handles database backup and restore operations.
    Supports both SQLite and PostgreSQL databases.
    """

    def __init__(self, backup_dir: str | None = None):
        self.backup_dir = backup_dir or DEFAULT_BACKUP_DIR
        os.makedirs(self.backup_dir, exist_ok=True)

    @property
    def is_sqlite(self) -> bool:
        return "postgres" not in DATABASE_ENGINE.lower()

    def _reserve_backup_file(self) -> str:
        """
        Create an empty, private chacc_backup_<UTC timestamp>.<db|sql> and return
        its path. Created exclusively, so an existing backup is never overwritten
        and the data is never readable by other users, even briefly.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        extension = "db" if self.is_sqlite else "sql"
        counter = 0
        while True:
            suffix = f"_{counter}" if counter else ""
            path = os.path.join(self.backup_dir, f"chacc_backup_{timestamp}{suffix}.{extension}")
            try:
                os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, _BACKUP_FILE_MODE))
                return path
            except FileExistsError:
                counter += 1

    async def create_backup(self) -> str:
        """
        Create a database backup.

        Returns:
            Path to backup file

        Raises:
            RuntimeError: If backup fails
        """
        backup_path = None
        try:
            backup_path = self._reserve_backup_file()
            chacc_logger.info(f"Creating database backup: {backup_path}")

            if self.is_sqlite:
                await asyncio.to_thread(self._backup_sqlite, backup_path)
            else:
                await self._backup_postgresql(backup_path)

            if self.is_sqlite:
                latest_path = os.path.join(self.backup_dir, "chacc_backup_latest.db")
                await asyncio.to_thread(shutil.copy2, backup_path, latest_path)

            chacc_logger.info(f"Backup created successfully: {backup_path}")
            return backup_path

        except Exception as e:
            chacc_logger.error(f"Backup failed: {e}")
            if backup_path:
                # Don't leave an empty or partial file that looks like a backup.
                with contextlib.suppress(OSError):
                    os.remove(backup_path)
            raise RuntimeError(f"Database backup failed: {e}") from e

    def _backup_sqlite(self, backup_path: str) -> None:
        if not os.path.exists(SQLITE_DB_PATH):
            raise RuntimeError(f"Database file not found: {SQLITE_DB_PATH}")
        _copy_sqlite(SQLITE_DB_PATH, backup_path)
        chacc_logger.info(f"SQLite database copied to {backup_path}")

    def _postgres_env(self) -> dict:
        env = os.environ.copy()
        env["PGPASSWORD"] = DATABASE_PASSWORD
        return env

    def _postgres_connection_args(self) -> list[str]:
        return ["-h", DATABASE_HOST, "-p", str(DATABASE_PORT), "-U", DATABASE_USER]

    async def _backup_postgresql(self, backup_path: str):
        """Create PostgreSQL backup using pg_dump."""
        cmd = [
            "pg_dump",
            *self._postgres_connection_args(),
            "-F",
            "p",
            "-f",
            backup_path,
            DATABASE_NAME,
        ]
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            env=self._postgres_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {result.stderr}")

        chacc_logger.info(f"PostgreSQL database dumped to {backup_path}")

    async def restore(self, backup_path: str) -> bool:
        """
        Restore database from backup.

        PostgreSQL restores drop and recreate the database, so the server must
        not be connected to it.

        Args:
            backup_path: Path to backup file

        Returns:
            True if successful

        Raises:
            RuntimeError: If restore fails
        """
        if not os.path.exists(backup_path):
            raise RuntimeError(f"Backup file not found: {backup_path}")

        chacc_logger.warning(f"Restoring database from: {backup_path}")

        try:
            if self.is_sqlite:
                await asyncio.to_thread(_copy_sqlite, backup_path, SQLITE_DB_PATH)
            else:
                await asyncio.to_thread(self._restore_postgresql, backup_path)

            chacc_logger.info("Database restored successfully")
            return True

        except Exception as e:
            chacc_logger.error(f"Restore failed: {e}")
            raise RuntimeError(f"Database restore failed: {e}") from e

    def _restore_postgresql(self, backup_path: str) -> None:
        """Drop, recreate and reload the database with psql; stop at the first failure."""
        connection = self._postgres_connection_args()
        database = '"' + DATABASE_NAME.replace('"', '""') + '"'
        steps = [
            ("drop", [*connection, "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {database}"]),
            ("create", [*connection, "-d", "postgres", "-c", f"CREATE DATABASE {database}"]),
            (
                "load",
                [*connection, "-d", DATABASE_NAME, "-v", "ON_ERROR_STOP=1", "-f", backup_path],
            ),
        ]
        env = self._postgres_env()
        for step, args in steps:
            result = subprocess.run(
                ["psql", *args], env=env, capture_output=True, text=True, check=False
            )
            if result.returncode != 0:
                raise RuntimeError(f"psql {step} step failed: {result.stderr.strip()}")

        chacc_logger.info(f"PostgreSQL database restored from {backup_path}")

    def list_backups(self) -> list:
        """
        List available backups.

        Returns:
            List of backup file info dicts
        """
        backups = []

        if not os.path.exists(self.backup_dir):
            return backups

        for filename in os.listdir(self.backup_dir):
            if filename.startswith("chacc_backup_"):
                filepath = os.path.join(self.backup_dir, filename)
                stat = os.stat(filepath)
                backups.append(
                    {
                        "name": filename,
                        "path": filepath,
                        "size": stat.st_size,
                        "created": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    }
                )

        backups.sort(key=lambda x: x["created"], reverse=True)
        return backups

    def cleanup_old_backups(self, keep_count: int = 5):
        """
        Remove old backups, keeping only the most recent ones.

        Args:
            keep_count: Number of backups to keep
        """
        backups = self.list_backups()

        if len(backups) <= keep_count:
            return

        for backup in backups[keep_count:]:
            try:
                os.remove(backup["path"])
                chacc_logger.info(f"Removed old backup: {backup['name']}")
            except OSError as e:
                chacc_logger.warning(f"Failed to remove {backup['name']}: {e}")


def create_backup(backup_dir: str | None = None) -> DatabaseBackup:
    """Factory function to create a DatabaseBackup instance."""
    return DatabaseBackup(backup_dir)
