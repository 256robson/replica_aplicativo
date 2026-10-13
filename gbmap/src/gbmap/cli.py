"""CLI gbmap: gerencia GB_SYS_TABMAP e GB_SYS_FLDMAP no SQL Server."""
from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import model, presets, profiles, sqlserver
from .model import FieldMap, TableMap

app = typer.Typer(help="Mapeamentos de tabelas e campos do Geobank (SQL Server).", no_args_is_help=True)
profile_app = typer.Typer(help="Perfis de conexão locais.")
table_app = typer.Typer(help="Mapeamento de tabelas (GB_SYS_TABMAP).")
field_app = typer.Typer(help="Mapeamento de campos (GB_SYS_FLDMAP).")
app.add_typer(profile_app, name="profile")
app.add_typer(table_app, name="table")
app.add_typer(field_app, name="field")

console = Console()


def _current(profile_name: Optional[str]):
    name = profile_name or profiles.active_profile_name()
    if not name:
        console.print("[red]Nenhum perfil ativo. Use 'gbmap profile add' e 'gbmap profile use'.[/red]")
        raise typer.Exit(2)
    p = profiles.get_profile(name)
    if p is None:
        console.print(f"[red]Perfil '{name}' não encontrado.[/red]")
        raise typer.Exit(2)
    engine = sqlserver.make_engine(p.server, p.database, p.driver, p.trusted)
    return p, engine


@profile_app.command("add")
def profile_add(
    name: str,
    server: str = typer.Option(..., help="Servidor SQL, ex.: localhost\\SQLEXPRESS"),
    database: str = typer.Option(..., help="Banco de conteúdo ou SYSTEM"),
    schema: str = typer.Option("dbo", help="Schema das tabelas"),
    driver: str = typer.Option("ODBC Driver 18 for SQL Server"),
    trusted: bool = typer.Option(True, help="Autenticação integrada do Windows"),
):
    """Cria ou atualiza um perfil. Senha: variáveis GBMAP_USER / GBMAP_PASSWORD."""
    profiles.save_profile(profiles.Profile(name, server, database, schema, driver, trusted))
    console.print(f"Perfil [bold]{name}[/bold] salvo.")


@profile_app.command("list")
def profile_list():
    active = profiles.active_profile_name()
    t = Table("Ativo", "Nome", "Servidor", "Banco", "Schema", "Auth")
    for p in profiles.list_profiles():
        t.add_row("*" if p.name == active else "", p.name, p.server, p.database, p.schema,
                  "integrada" if p.trusted else "usuário")
    console.print(t)


@profile_app.command("use")
def profile_use(name: str):
    if profiles.get_profile(name) is None:
        console.print(f"[red]Perfil '{name}' não encontrado.[/red]")
        raise typer.Exit(2)
    profiles.set_active(name)
    console.print(f"Perfil ativo: [bold]{name}[/bold]")


@app.command("init")
def init(profile: Optional[str] = typer.Option(None, "--profile", "-p")):
    """Cria GB_SYS_TABMAP e GB_SYS_FLDMAP se não existirem."""
    p, engine = _current(profile)
    created = sqlserver.create_mapping_tables(engine, p.schema)
    if created:
        console.print(f"Criadas: {', '.join(created)}")
    else:
        console.print("Tabelas de mapeamento já existem.")


@table_app.command("set")
def table_set(sys_table: str, usr_table: str, profile: Optional[str] = typer.Option(None, "--profile", "-p")):
    """Mapeia uma tabela padrão para o nome do usuário."""
    p, engine = _current(profile)
    sqlserver.save_table_map(engine, p.schema, TableMap(sys_table.upper(), usr_table))
    console.print(f"{sys_table.upper()} -> {usr_table}")


@table_app.command("remove")
def table_remove(sys_table: str, profile: Optional[str] = typer.Option(None, "--profile", "-p")):
    p, engine = _current(profile)
    n = sqlserver.delete_table_map(engine, p.schema, sys_table.upper())
    console.print(f"{n} mapeamento(s) removido(s).")


@table_app.command("list")
def table_list(profile: Optional[str] = typer.Option(None, "--profile", "-p")):
    p, engine = _current(profile)
    t = Table("Tabela padrão", "Tabela do usuário")
    for m in sqlserver.load_table_maps(engine, p.schema):
        t.add_row(m.sys_table, m.usr_table)
    console.print(t)


@field_app.command("set")
def field_set(sys_table: str, sys_field: str, usr_field: str,
              profile: Optional[str] = typer.Option(None, "--profile", "-p")):
    """Mapeia um campo padrão para a coluna do usuário (exige mapeamento da tabela)."""
    p, engine = _current(profile)
    sqlserver.save_field_map(engine, p.schema, FieldMap(sys_table.upper(), sys_field.upper(), usr_field))
    console.print(f"{sys_table.upper()}.{sys_field.upper()} -> {usr_field}")


@field_app.command("remove")
def field_remove(sys_table: str, sys_field: str, profile: Optional[str] = typer.Option(None, "--profile", "-p")):
    p, engine = _current(profile)
    n = sqlserver.delete_field_map(engine, p.schema, sys_table.upper(), sys_field.upper())
    console.print(f"{n} mapeamento(s) removido(s).")


@field_app.command("list")
def field_list(profile: Optional[str] = typer.Option(None, "--profile", "-p")):
    p, engine = _current(profile)
    t = Table("Tabela padrão", "Campo padrão", "Campo do usuário")
    for m in sqlserver.load_field_maps(engine, p.schema):
        t.add_row(m.sys_table, m.sys_field, m.usr_field)
    console.print(t)


@app.command("validate")
def validate_cmd(profile: Optional[str] = typer.Option(None, "--profile", "-p")):
    """Valida mapeamentos contra o esquema real. Sai com código 1 se houver erros."""
    p, engine = _current(profile)
    exists = sqlserver.mapping_tables_exist(engine, p.schema)
    if not all(exists.values()):
        missing = [k for k, v in exists.items() if not v]
        console.print(f"[red]Tabelas ausentes: {', '.join(missing)}. Rode 'gbmap init'.[/red]")
        raise typer.Exit(1)
    issues = model.validate(
        sqlserver.load_table_maps(engine, p.schema),
        sqlserver.load_field_maps(engine, p.schema),
        sqlserver.load_actual_columns(engine, p.schema),
    )
    if not issues:
        console.print("[green]Nenhum problema encontrado.[/green]")
        return
    t = Table("Nível", "Item", "Mensagem")
    for i in issues:
        color = "red" if i.level == model.ERROR else "yellow"
        t.add_row(f"[{color}]{i.level}[/{color}]", i.subject, i.message)
    console.print(t)
    if model.has_errors(issues):
        raise typer.Exit(1)


@app.command("reference")
def reference():
    """Mostra a referência de campos do Sample Tracker (v10/v11)."""
    t = Table("Tabela", "v7", "v10", "Implantado")
    for row in presets.V10_REFERENCE:
        t.add_row(*row)
    console.print(t)


def main() -> None:
    app()
