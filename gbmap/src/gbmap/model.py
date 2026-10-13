"""Regras de mapeamento de tabelas e campos (GB_SYS_TABMAP / GB_SYS_FLDMAP).

Funções puras, sem acesso ao banco, para facilitar testes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set

ERROR = "error"
WARNING = "warning"

# Correção de mapeamento exigida pela atualização para v11 (2018 -> 2026).
QAQC_CORRECTION = (("ST_XS_STANDARD", "QAQC_TYPE", "QC_TYPE"),)


@dataclass(frozen=True)
class TableMap:
    sys_table: str
    usr_table: str


@dataclass(frozen=True)
class FieldMap:
    sys_table: str
    sys_field: str
    usr_field: str


@dataclass(frozen=True)
class Issue:
    level: str
    subject: str
    message: str


def resolve_table(sys_table: str, table_maps: Iterable[TableMap]) -> str:
    """Retorna o nome do usuário; sem mapeamento usa o nome padrão."""
    for m in table_maps:
        if m.sys_table.upper() == sys_table.upper():
            return m.usr_table
    return sys_table


def resolve_field(sys_table: str, sys_field: str, field_maps: Iterable[FieldMap]) -> str:
    """Retorna o nome do campo do usuário; sem mapeamento usa o nome padrão."""
    for m in field_maps:
        if m.sys_table.upper() == sys_table.upper() and m.sys_field.upper() == sys_field.upper():
            return m.usr_field
    return sys_field


def validate(
    table_maps: List[TableMap],
    field_maps: List[FieldMap],
    actual_columns: Dict[str, Set[str]],
) -> List[Issue]:
    """Valida mapeamentos contra o esquema real.

    actual_columns: nome da tabela do usuário -> colunas existentes. Comparação sem diferenciar maiúsculas.
    """
    issues: List[Issue] = []
    cols = {t.lower(): {c.lower() for c in cs} for t, cs in actual_columns.items()}
    mapped_sys_tables = {m.sys_table.upper() for m in table_maps}

    seen_t: Set[str] = set()
    for t in table_maps:
        key = t.sys_table.upper()
        if key in seen_t:
            issues.append(Issue(ERROR, t.sys_table, "mapeamento de tabela duplicado"))
        seen_t.add(key)
        if t.usr_table.lower() not in cols:
            issues.append(Issue(ERROR, t.sys_table,
                                f"tabela '{t.usr_table}' não existe no esquema"))
        if t.usr_table.upper() == t.sys_table.upper():
            issues.append(Issue(WARNING, t.sys_table,
                                "mapeamento redundante (nome igual ao padrão)"))

    seen_f: Set[tuple] = set()
    for f in field_maps:
        label = f"{f.sys_table}.{f.sys_field}"
        key = (f.sys_table.upper(), f.sys_field.upper())
        if key in seen_f:
            issues.append(Issue(ERROR, label, "mapeamento de campo duplicado"))
        seen_f.add(key)

        if f.sys_table.upper() not in mapped_sys_tables:
            issues.append(Issue(ERROR, label,
                                "campo mapeado exige mapeamento da tabela correspondente"))
        usr_table = resolve_table(f.sys_table, table_maps)
        table_cols = cols.get(usr_table.lower())
        if table_cols is None:
            issues.append(Issue(ERROR, label,
                                f"tabela '{usr_table}' não encontrada; campo não validado"))
        elif f.usr_field.lower() not in table_cols:
            issues.append(Issue(ERROR, label,
                                f"coluna '{f.usr_field}' não existe em '{usr_table}'"))

        if f.usr_field.upper() == f.sys_field.upper():
            issues.append(Issue(WARNING, label,
                                "mapeamento redundante (nome igual ao padrão)"))

        for tab, old, new in QAQC_CORRECTION:
            if f.sys_table.upper() == tab and f.sys_field.upper() == old:
                issues.append(Issue(WARNING, label,
                                    f"v11 usa {tab}.{new}; atualize o mapeamento de {old}"))
    return issues


def has_errors(issues: Iterable[Issue]) -> bool:
    return any(i.level == ERROR for i in issues)


def find_field_map(field_maps: List[FieldMap], sys_table: str, sys_field: str) -> Optional[FieldMap]:
    for m in field_maps:
        if m.sys_table.upper() == sys_table.upper() and m.sys_field.upper() == sys_field.upper():
            return m
    return None
