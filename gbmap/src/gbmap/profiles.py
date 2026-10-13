"""Perfis locais de conexão, guardados em SQLite. Senhas não são gravadas."""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class Profile:
    name: str
    server: str
    database: str
    schema: str
    driver: str
    trusted: bool


def store_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    path = Path(base) / "gbmap"
    path.mkdir(parents=True, exist_ok=True)
    return path / "profiles.db"


def _connect(path: Optional[Path] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or store_path()))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS profiles ("
        " name TEXT PRIMARY KEY, server TEXT NOT NULL, database_name TEXT NOT NULL,"
        " schema_name TEXT NOT NULL, driver TEXT NOT NULL, trusted INTEGER NOT NULL)"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    return conn


def save_profile(p: Profile, path: Optional[Path] = None) -> None:
    with _connect(path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO profiles VALUES (?, ?, ?, ?, ?, ?)",
            (p.name, p.server, p.database, p.schema, p.driver, int(p.trusted)),
        )
    conn.close()


def list_profiles(path: Optional[Path] = None) -> List[Profile]:
    conn = _connect(path)
    rows = conn.execute("SELECT name, server, database_name, schema_name, driver, trusted FROM profiles ORDER BY name").fetchall()
    conn.close()
    return [Profile(r[0], r[1], r[2], r[3], r[4], bool(r[5])) for r in rows]


def get_profile(name: str, path: Optional[Path] = None) -> Optional[Profile]:
    for p in list_profiles(path):
        if p.name == name:
            return p
    return None


def set_active(name: str, path: Optional[Path] = None) -> None:
    conn = _connect(path)
    with conn:
        conn.execute("INSERT OR REPLACE INTO settings VALUES ('active_profile', ?)", (name,))
    conn.close()


def active_profile_name(path: Optional[Path] = None) -> Optional[str]:
    conn = _connect(path)
    row = conn.execute("SELECT value FROM settings WHERE key = 'active_profile'").fetchone()
    conn.close()
    return row[0] if row else None
