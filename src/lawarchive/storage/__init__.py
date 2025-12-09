"""Storage backends for the law archive."""

from lawarchive.storage.base import StorageBackend
from lawarchive.storage.sqlite import SQLiteStorage

# PostgreSQL is optional - only import if installed
try:
    from lawarchive.storage.postgres import PostgresStorage
    __all__ = ["StorageBackend", "SQLiteStorage", "PostgresStorage"]
except ImportError:
    __all__ = ["StorageBackend", "SQLiteStorage"]
