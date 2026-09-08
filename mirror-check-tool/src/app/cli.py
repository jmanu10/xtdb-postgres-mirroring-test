import argparse
import datetime
import sys
from pathlib import Path
from typing import Any

import psycopg
from rich.console import Console
from rich.markup import escape
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from lib.diff import KEY, Difference, Rows, differences
from lib.render import (
    DIFFERENCE_HEADERS,
    GROUP_HEADERS,
    difference_cells,
    group_cells,
    markdown_document,
)
from lib.settings import Settings
from lib.summary import summarize

type Connection = psycopg.Connection[tuple[Any, ...]]

PUBLISHED = (
    "SELECT tablename FROM pg_publication_tables WHERE pubname = %s ORDER BY tablename"
)
MIRRORED = (
    "SELECT table_name FROM {database}.information_schema.tables"
    " WHERE table_schema = 'public'"
)
STEPS = 3
SHOWN = 50
DEFAULT_OUTPUT = Path("differences.md")
KIND_STYLES = {
    "missing": "red",
    "extra": "yellow",
    "differs": "cyan",
    "elements": "cyan",
}


class CheckError(Exception): ...


def names(
    connection: Connection, statement: str, parameters: tuple[object, ...]
) -> list[str]:
    return [str(row[0]) for row in connection.execute(statement, parameters).fetchall()]


def fetch(connection: Connection, statement: str) -> Rows:
    cursor = connection.execute(statement)
    columns = [column.name for column in cursor.description or []]
    if KEY not in columns:
        raise CheckError(
            f"{statement}: no {KEY} column, so the table cannot be mirrored"
        )
    key = columns.index(KEY)
    return {row[key]: dict(zip(columns, row)) for row in cursor.fetchall()}


def styled(cells: tuple[str, ...], kind_index: int) -> list[str]:
    kind = cells[kind_index]
    return [
        f"[{KIND_STYLES[kind]}]{kind}[/]" if index == kind_index else escape(cell)
        for index, cell in enumerate(cells)
    ]


def differences_table(found: list[Difference]) -> Table:
    shown = found[:SHOWN]
    title = f"differences ({len(shown)} of {len(found)})"
    table = Table(title=title if len(found) > SHOWN else "differences")
    for header in DIFFERENCE_HEADERS:
        table.add_column(header)
    for difference in shown:
        table.add_row(*styled(difference_cells(difference), 1))
    return table


def summary_table(found: list[Difference]) -> Table:
    table = Table(title="summary")
    for header in GROUP_HEADERS:
        table.add_column(header, justify="right" if header == "rows" else "left")
    for group in summarize(found):
        table.add_row(*styled(group_cells(group), 2))
    return table


def build_progress(console: Console) -> Progress:
    return Progress(
        TextColumn("[bold]{task.description}"),
        BarColumn(),
        TextColumn("{task.fields[rows]:>6} rows"),
        TextColumn("{task.fields[found]:>4} differences"),
        TimeElapsedColumn(),
        console=console,
    )


def compare_table(
    source: Connection,
    mirror: Connection,
    table: str,
    present: list[str],
    settings: Settings,
    progress: Progress,
) -> tuple[int, list[Difference]]:
    task = progress.add_task(table, total=STEPS, rows=0, found=0)
    source_rows = fetch(source, f'SELECT * FROM "{table}"')
    progress.update(task, advance=1, rows=len(source_rows))
    mirror_rows: Rows = {}
    if table in present:
        mirror_rows = fetch(
            mirror, f'SELECT * FROM "{settings.mirror_database}"."public"."{table}"'
        )
    progress.update(task, advance=1)
    found = differences(table, source_rows, mirror_rows)
    progress.update(task, advance=1, found=len(found))
    return len(source_rows), found


def save(path: Path, found: list[Difference], counts: list[tuple[str, int]]) -> None:
    now = datetime.datetime.now(datetime.UTC)
    path.write_text(markdown_document(found, summarize(found), counts, now))


def run(args: argparse.Namespace, settings: Settings, console: Console) -> int:
    found: list[Difference] = []
    counts: list[tuple[str, int]] = []
    with (
        psycopg.connect(settings.source_url, autocommit=True) as source,
        psycopg.connect(settings.mirror_url, autocommit=True) as mirror,
    ):
        wanted = args.table or names(source, PUBLISHED, (settings.publication_name,))
        if not wanted:
            raise CheckError(f"publication {settings.publication_name} has no tables")
        present = names(mirror, MIRRORED.format(database=settings.mirror_database), ())
        with build_progress(console) as progress:
            for table in wanted:
                rows, table_found = compare_table(
                    source, mirror, table, present, settings, progress
                )
                counts.append((table, rows))
                found.extend(table_found)
    if found:
        console.print(
            summary_table(found) if args.summary else differences_table(found)
        )
    if args.save or args.output is not None:
        output = args.output or DEFAULT_OUTPUT
        save(output, found, counts)
        console.print(f"saved {len(found)} differences to {output}")
    return 1 if found else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mirror-diff",
        description="Data differences between a PostgreSQL database and its XTDB mirror",
    )
    parser.add_argument(
        "table", nargs="*", help="tables to compare (default: every published table)"
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="aggregate the differences by table, column, and kind",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help=f"write the summary and every difference as markdown to {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        metavar="PATH",
        help="write the markdown to this path instead (implies --save)",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        raise SystemExit(run(args, Settings(), Console()))
    except (psycopg.Error, CheckError) as error:
        print(f"mirror-diff: {error}".rstrip(), file=sys.stderr)
        raise SystemExit(2) from error
