"""Acesso ao SQL Server via SQLAlchemy + pyodbc para as tabelas de mapeamento."""
from __future__ import annotations

import os
from typing import Dict, List, Set
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .model import FieldMap, TableMap

MAP_TABLE = "GB_SYS_TABMAP"
FIELD_MAP_TABLE = "GB_SYS_FLDMAP"

# Nomes de colunas conforme o help. O cabeçalho da tabela de referência diz
# USR_FLD_NAME, enquanto o exemplo diz USR_FIELD_NAME. Usamos USR_FIELD_NAME (ver README).
DDL_TABLE_MAP = """
CREATE TABLE {schema}.GB_SYS_TABMAP (
    SYS_TABLE_NAME VARCHAR(128) NOT NULL PRIMARY KEY,
    USR_TABLE_NAME VARCHAR(128) NOT NULL
)"""
DDL_FIELD_MAP = """
CREATE TABLE {schema}.GB_SYS_FLDMAP (
    SYS_TABLE_NAME VARCHAR(128) NOT NULL,
    SYS_FIELD_NAME VARCHAR(128) NOT NULL,
    USR_FIELD_NAME VARCHAR(128) NOT NULL,
    CONSTRAINT PK_GB_SYS_FLDMAP PRIMARY KEY (SYS_TABLE_NAME, SYS_FIELD_NAME)
)"""


def build_odbc_string(server: str, database: str, driver: str, trusted: bool) -> str:
    parts = [f"DRIVER={{{driver}}}", f"SERVER={server}", f"DATABASE={database}"]
    if trusted:
        parts.append("Trusted_Connection=yes")
    else:
        user = os.environ.get("GBMAP_USER", "")
        password = os.environ.get("GBMAP_PASSWORD", "")
        parts += [f"UID={user}", f"PWD={password}"]
    parts.append("TrustServerCertificate=yes")
    return ";".join(parts)


def make_engine(server: str, database: str, driver: str, trusted: bool) -> Engine:
    odbc = build_odbc_string(server, database, driver, trusted)
    return create_engine(f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc)}")


def mapping_tables_exist(engine: Engine, schema: str) -> Dict[str, bool]:
    sql = text(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA = :s AND TABLE_NAME IN (:t1, :t2)"
    )
    with engine.connect() as conn:
        found = {r[0].upper() for r in conn.execute(sql, {"s": schema, "t1": MAP_TABLE, "t2": FIELD_MAP_TABLE})}
    return {MAP_TABLE: MAP_TABLE in found, FIELD_MAP_TABLE: FIELD_MAP_TABLE in found}


def create_mapping_tables(engine: Engine, schema: str) -> List[str]:
    """Cria as tabelas de mapeamento que não existem. Retorna as criadas."""
    existing = mapping_tables_exist(engine, schema)
    created: List[str] = []
    with engine.begin() as conn:
        if not existing[MAP_TABLE]:
            conn.execute(text(DDL_TABLE_MAP.format(schema=schema)))
            created.append(MAP_TABLE)
        if not existing[FIELD_MAP_TABLE]:
            conn.execute(text(DDL_FIELD_MAP.format(schema=schema)))
            created.append(FIELD_MAP_TABLE)
    return created


def load_table_maps(engine: Engine, schema: str) -> List[TableMap]:
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT SYS_TABLE_NAME, USR_TABLE_NAME FROM {schema}.{MAP_TABLE} ORDER BY SYS_TABLE_NAME"
        ))
        return [TableMap(r[0], r[1]) for r in rows]


def load_field_maps(engine: Engine, schema: str) -> List[FieldMap]:
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT SYS_TABLE_NAME, SYS_FIELD_NAME, USR_FIELD_NAME FROM {schema}.{FIELD_MAP_TABLE} "
            "ORDER BY SYS_TABLE_NAME, SYS_FIELD_NAME"
        ))
        return [FieldMap(r[0], r[1], r[2]) for r in rows]


def save_table_map(engine: Engine, schema: str, m: TableMap) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {schema}.{MAP_TABLE} WHERE SYS_TABLE_NAME = :s"), {"s": m.sys_table})
        conn.execute(
            text(f"INSERT INTO {schema}.{MAP_TABLE} (SYS_TABLE_NAME, USR_TABLE_NAME) VALUES (:s, :u)"),
            {"s": m.sys_table, "u": m.usr_table},
        )


def delete_table_map(engine: Engine, schema: str, sys_table: str) -> int:
    with engine.begin() as conn:
        res = conn.execute(text(f"DELETE FROM {schema}.{MAP_TABLE} WHERE SYS_TABLE_NAME = :s"), {"s": sys_table})
        return res.rowcount


def save_field_map(engine: Engine, schema: str, m: FieldMap) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(f"DELETE FROM {schema}.{FIELD_MAP_TABLE} WHERE SYS_TABLE_NAME = :t AND SYS_FIELD_NAME = :f"),
            {"t": m.sys_table, "f": m.sys_field},
        )
        conn.execute(
            text(f"INSERT INTO {schema}.{FIELD_MAP_TABLE} (SYS_TABLE_NAME, SYS_FIELD_NAME, USR_FIELD_NAME) "
                 "VALUES (:t, :f, :u)"),
            {"t": m.sys_table, "f": m.sys_field, "u": m.usr_field},
        )


def delete_field_map(engine: Engine, schema: str, sys_table: str, sys_field: str) -> int:
    with engine.begin() as conn:
        res = conn.execute(
            text(f"DELETE FROM {schema}.{FIELD_MAP_TABLE} WHERE SYS_TABLE_NAME = :t AND SYS_FIELD_NAME = :f"),
            {"t": sys_table, "f": sys_field},
        )
        return res.rowcount


def load_actual_columns(engine: Engine, schema: str) -> Dict[str, Set[str]]:
    """Mapa tabela -> colunas, lido de INFORMATION_SCHEMA.COLUMNS."""
    result: Dict[str, Set[str]] = {}
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = :s"
        ), {"s": schema})
        for t, c in rows:
            result.setdefault(t, set()).add(c)
    return result
