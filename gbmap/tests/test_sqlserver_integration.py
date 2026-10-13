"""Testes de integração com SQL Server real.

Rodam só quando GBMAP_TEST_SERVER está definido (ex.: localhost ou localhost\\SQLEXPRESS),
usando autenticação integrada do Windows. GBMAP_TEST_DRIVER opcional
(padrão: ODBC Driver 17 for SQL Server).

Cada execução cria um banco próprio com nome aleatório e o remove ao final;
nenhum banco existente é lido ou alterado.
"""
from __future__ import annotations

import os
import uuid

import pytest

from gbmap.model import FieldMap, TableMap, has_errors, validate
from gbmap import sqlserver as sql

SERVER = os.environ.get("GBMAP_TEST_SERVER")
DRIVER = os.environ.get("GBMAP_TEST_DRIVER", "ODBC Driver 17 for SQL Server")

pytestmark = pytest.mark.skipif(not SERVER, reason="defina GBMAP_TEST_SERVER para rodar")


@pytest.fixture()
def engine():
    db = f"gbmap_itest_{uuid.uuid4().hex[:8]}"
    try:
        master = sql.make_engine(SERVER, "master", DRIVER, True)
        with master.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql(f"CREATE DATABASE [{db}]")
    except Exception as exc:  # servidor inacessível ou sem permissão
        pytest.skip(f"SQL Server indisponível: {exc}")

    eng = sql.make_engine(SERVER, db, DRIVER, True)
    try:
        with eng.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE dbo.XS_STD (QC_TYPE VARCHAR(20) NULL, SAMPLE_ID INT NULL)")
        yield eng
    finally:
        eng.dispose()
        with master.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql(
                f"ALTER DATABASE [{db}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{db}]"
            )
        master.dispose()


def test_create_mapping_tables_is_idempotent(engine):
    created = sql.create_mapping_tables(engine, "dbo")
    assert set(created) == {sql.MAP_TABLE, sql.FIELD_MAP_TABLE}
    assert all(sql.mapping_tables_exist(engine, "dbo").values())
    assert sql.create_mapping_tables(engine, "dbo") == []


def test_table_map_round_trip(engine):
    sql.create_mapping_tables(engine, "dbo")
    sql.save_table_map(engine, "dbo", TableMap("ST_XS_STANDARD", "XS_STD"))
    assert sql.load_table_maps(engine, "dbo") == [TableMap("ST_XS_STANDARD", "XS_STD")]

    sql.save_table_map(engine, "dbo", TableMap("ST_XS_STANDARD", "XS_STD2"))
    assert sql.load_table_maps(engine, "dbo") == [TableMap("ST_XS_STANDARD", "XS_STD2")]

    assert sql.delete_table_map(engine, "dbo", "ST_XS_STANDARD") == 1
    assert sql.load_table_maps(engine, "dbo") == []


def test_field_map_round_trip_and_actual_columns(engine):
    sql.create_mapping_tables(engine, "dbo")
    sql.save_field_map(engine, "dbo", FieldMap("ST_XS_STANDARD", "QAQC_TYPE", "QC_TYPE"))
    assert sql.load_field_maps(engine, "dbo") == [FieldMap("ST_XS_STANDARD", "QAQC_TYPE", "QC_TYPE")]

    columns = sql.load_actual_columns(engine, "dbo")
    assert {"QC_TYPE", "SAMPLE_ID"} <= {c.upper() for c in columns["XS_STD"]}

    assert sql.delete_field_map(engine, "dbo", "ST_XS_STANDARD", "QAQC_TYPE") == 1
    assert sql.load_field_maps(engine, "dbo") == []


def test_validate_against_real_schema(engine):
    sql.create_mapping_tables(engine, "dbo")
    sql.save_table_map(engine, "dbo", TableMap("ST_XS_STANDARD", "XS_STD"))
    sql.save_field_map(engine, "dbo", FieldMap("ST_XS_STANDARD", "SAMPLE_ID", "SAMPLE_ID"))

    issues = validate(
        sql.load_table_maps(engine, "dbo"),
        sql.load_field_maps(engine, "dbo"),
        sql.load_actual_columns(engine, "dbo"),
    )
    assert not has_errors(issues)

    sql.save_field_map(engine, "dbo", FieldMap("ST_XS_STANDARD", "NO_SUCH", "MISSING_COL"))
    issues = validate(
        sql.load_table_maps(engine, "dbo"),
        sql.load_field_maps(engine, "dbo"),
        sql.load_actual_columns(engine, "dbo"),
    )
    assert has_errors(issues)
