"""Storage backends for the law archive."""

from atlas.storage.base import StorageBackend
from atlas.storage.sqlite import SQLiteStorage

# PostgreSQL is optional - only import if installed
try:
    from atlas.storage.postgres import PostgresStorage

    __all__ = ["StorageBackend", "SQLiteStorage", "PostgresStorage"]
except ImportError:
    __all__ = ["StorageBackend", "SQLiteStorage"]
