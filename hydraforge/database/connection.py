"""Database Connection Manager for HYDRAFORGE.
Supports both PostgreSQL (Neon, RDS, Docker Postgres) and SQLite with WAL mode.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

DEFAULT_DB_PATH = Path("data/hydraforge.db")


class PostgresCursorWrapper:
    """Wraps a psycopg2 cursor to provide a sqlite3-compatible interface."""

    def __init__(self, raw_cursor: Any) -> None:
        self.cursor = raw_cursor

    def _convert_query(self, query: str) -> str:
        q = query.strip()
        # Drop PRAGMA statements (SQLite specific)
        if q.upper().startswith("PRAGMA"):
            return ""
        # Convert parameter placeholders from ? to %s
        return q.replace("?", "%s")

    def execute(self, query: str, params: Optional[Union[Tuple, List, Dict]] = None) -> PostgresCursorWrapper:
        converted = self._convert_query(query)
        if not converted:
            return self
        if params is not None:
            self.cursor.execute(converted, params)
        else:
            self.cursor.execute(converted)
        return self

    def executemany(self, query: str, seq_of_params: Any) -> PostgresCursorWrapper:
        converted = self._convert_query(query)
        if not converted:
            return self
        self.cursor.executemany(converted, seq_of_params)
        return self

    def fetchone(self) -> Optional[Dict[str, Any]]:
        row = self.cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self) -> List[Dict[str, Any]]:
        rows = self.cursor.fetchall()
        return [dict(r) for r in rows]

    @property
    def rowcount(self) -> int:
        return self.cursor.rowcount

    def close(self) -> None:
        self.cursor.close()


class PostgresConnectionWrapper:
    """Wraps a psycopg2 connection to provide sqlite3-compatible interface."""

    def __init__(self, raw_conn: Any) -> None:
        self.conn = raw_conn

    def cursor(self) -> PostgresCursorWrapper:
        import psycopg2.extras
        return PostgresCursorWrapper(self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor))

    def execute(self, query: str, params: Optional[Union[Tuple, List, Dict]] = None) -> PostgresCursorWrapper:
        cur = self.cursor()
        cur.execute(query, params)
        return cur

    def executescript(self, script: str) -> None:
        with self.conn.cursor() as cur:
            for statement in script.strip().split(";"):
                stmt = statement.strip()
                if stmt and not stmt.upper().startswith("PRAGMA"):
                    cur.execute(stmt)

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def close(self) -> None:
        self.conn.close()


class DatabaseManager:
    """Manages database connections for SQLite or PostgreSQL."""

    _default_db_path: Optional[Path] = None
    _default_db_url: Optional[str] = None

    @classmethod
    def set_default_path(cls, path: Optional[Path]) -> None:
        """Set a process-wide default database path (useful for testing and environments)."""
        cls._default_db_path = Path(path).resolve() if path else None

    @classmethod
    def set_default_url(cls, url: Optional[str]) -> None:
        """Set a process-wide database connection URL."""
        cls._default_db_url = url

    def __init__(
        self,
        db_path: Optional[Path] = None,
        db_url: Optional[str] = None
    ) -> None:
        # If db_path is explicitly provided, prefer SQLite for that instance (e.g. tests)
        if db_path is not None:
            self.is_postgres = False
            self.db_url = None
            self.db_path = Path(db_path).resolve()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            return

        raw_url = db_url or self._default_db_url or os.environ.get("DATABASE_URL")
        self.db_url = raw_url.strip() if raw_url else None

        if self.db_url and (self.db_url.startswith("postgresql://") or self.db_url.startswith("postgres://")):
            self.is_postgres = True
            self.db_path = None
        else:
            self.is_postgres = False
            self.db_path = Path(self._default_db_path or DEFAULT_DB_PATH).resolve()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> Any:
        """Create a new database connection."""
        if self.is_postgres:
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(self.db_url)
            return PostgresConnectionWrapper(conn)

        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    @contextmanager
    def connect(self) -> Generator[Any, None, None]:
        """Context manager providing an auto-closing database connection."""
        conn = self.get_connection()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Generator[Any, None, None]:
        """Context manager providing transactional execution."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
