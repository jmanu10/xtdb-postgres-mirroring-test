import argparse
import subprocess
import time

import psycopg
from rich.console import Console
from rich.table import Table as RenderTable

from lib.postgresql import seed, source, teardown
from lib.settings import Settings
from lib.use_cases import UseCaseError, discover, load
from lib.xtdb import attach, attach_statement, detach, storage_path, wait_for_rows
from lib.xtdb.client import session as xtdb_session

MIRROR_DIFF_DIR = "../mirror-check-tool"


def unknown_case(console: Console, settings: Settings, error: UseCaseError) -> int:
    console.print(f"[red]{error}[/red]")
    known = ", ".join(discover(settings.use_cases_path))
    console.print(f"known use cases: {known}")
    return 2


def mirror_diff_command(settings: Settings, sql_name: str) -> str:
    environment = (
        f"SOURCE_URL={settings.postgres_url}",
        f"MIRROR_URL={settings.xtdb_url}",
        f"MIRROR_DATABASE={sql_name}",
        f"PUBLICATION_NAME={sql_name}",
    )
    return "\n".join(
        (
            f"cd {MIRROR_DIFF_DIR}",
            *(f"{entry} \\" for entry in environment),
            "uv run mirror-diff",
        )
    )


def run_list(args: argparse.Namespace, settings: Settings, console: Console) -> int:
    table = RenderTable(title="use cases")
    table.add_column("name")
    table.add_column("sql name")
    table.add_column("rows", justify="right")
    try:
        for name in discover(settings.use_cases_path):
            case = load(settings.use_cases_path, name)
            table.add_row(name, case.sql_name, str(len(case.rows)))
    except UseCaseError as error:
        console.print(f"[red]{error}[/red]")
        return 2
    console.print(table)
    return 0


def run_run(args: argparse.Namespace, settings: Settings, console: Console) -> int:
    try:
        case = load(settings.use_cases_path, args.name)
    except UseCaseError as error:
        return unknown_case(console, settings, error)

    started = time.monotonic()
    try:
        with source(settings.postgres_url) as pg:
            seeded, source_rows = seed(pg, case, settings.publish_generated_columns)
        with xtdb_session(settings.xtdb_url) as xtdb:
            attached = attach(
                xtdb,
                case.sql_name,
                attach_statement(
                    case.sql_name, settings.xtdb_remote, case.sql_name, case.sql_name
                ),
            )
            mirror_rows, converged = wait_for_rows(
                xtdb, case.sql_name, case.sql_name, source_rows
            )
    except psycopg.Error as error:
        console.print(f"[red]{error}[/red]")
        return 2
    elapsed = time.monotonic() - started

    table = RenderTable(title=case.name)
    table.add_column("postgres")
    table.add_column("attach")
    table.add_column("source rows", justify="right")
    table.add_column("mirror rows", justify="right")
    table.add_column("converged")
    table.add_column("elapsed", justify="right")
    table.add_row(
        seeded,
        attached,
        str(source_rows),
        "-" if mirror_rows is None else str(mirror_rows),
        "yes" if converged else "no",
        f"{elapsed:.1f}s",
    )
    console.print(table)

    if converged:
        console.print(
            mirror_diff_command(settings, case.sql_name),
            highlight=False,
            soft_wrap=True,
        )
        return 0

    console.print(
        "the mirror did not converge, which is the expected outcome of a halting"
        f" case; check docker logs {settings.xtdb_container}"
    )
    return 1


def run_drop(args: argparse.Namespace, settings: Settings, console: Console) -> int:
    try:
        case = load(settings.use_cases_path, args.name)
    except UseCaseError as error:
        return unknown_case(console, settings, error)

    try:
        with xtdb_session(settings.xtdb_url) as xtdb:
            detached = detach(xtdb, case.sql_name)
        with source(settings.postgres_url) as pg:
            slot = teardown(pg, case)
    except psycopg.Error as error:
        console.print(f"[red]{error}[/red]")
        return 2

    try:
        cleanup = subprocess.run(
            [
                "docker",
                "exec",
                settings.xtdb_container,
                "rm",
                "-rf",
                storage_path(case.sql_name),
            ],
            check=False,
        )
    except OSError as error:
        console.print(f"[red]cannot run docker: {error}[/red]")
        return 2

    console.print(
        f"xtdb {detached}, postgres slot {slot}, publication and table dropped"
    )
    if cleanup.returncode != 0:
        console.print(
            f"[red]storage cleanup of {storage_path(case.sql_name)} exited"
            f" {cleanup.returncode}[/red]"
        )
        return 2
    return 0


def configure(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    use_case = subparsers.add_parser(
        "use-case", help="seed, publish, and attach one divergence use case"
    )
    nested = use_case.add_subparsers(dest="use_case_command", required=True)

    listing = nested.add_parser("list", help="list the discovered use cases")
    listing.set_defaults(run=run_list)

    running = nested.add_parser(
        "run", help="seed one use case, attach it, and poll the mirror"
    )
    running.add_argument("name")
    running.set_defaults(run=run_run)

    dropping = nested.add_parser("drop", help="detach and reset one use case")
    dropping.add_argument("name")
    dropping.set_defaults(run=run_drop)
