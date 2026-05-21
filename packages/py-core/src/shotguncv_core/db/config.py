from __future__ import annotations

import os


DEFAULT_DATABASE_URL_ENV = "SHOTGUNCV_DATABASE_URL"


def get_database_url(env_name: str = DEFAULT_DATABASE_URL_ENV) -> str:
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise RuntimeError(f"Missing database URL. Set `{env_name}` before running database-backed commands.")
    return value
