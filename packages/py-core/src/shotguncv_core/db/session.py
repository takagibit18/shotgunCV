from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def connect(database_url: str) -> Iterator[object]:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - exercised only without optional deps
        raise RuntimeError("Install ShotgunCV with the `rag` extra to use PostgreSQL-backed commands.") from exc

    with psycopg.connect(database_url) as conn:
        yield conn
