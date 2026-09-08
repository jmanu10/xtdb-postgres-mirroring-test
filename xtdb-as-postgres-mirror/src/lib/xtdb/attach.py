import time
from collections.abc import Callable
from typing import Literal

import psycopg

from lib.xtdb.client import Session

DETACHING = "db-being-detached"

ATTACHED = "SELECT count(*) FROM pg_catalog.pg_database WHERE datname = %s"


def storage_path(database: str) -> str:
    return f"/var/lib/xtdb/{database}"


def attach_statement(database: str, remote: str, publication: str, slot: str) -> str:
    return (
        f"ATTACH DATABASE {database} WITH $$log: !Local\n"
        f"  path: '{storage_path(database)}/log'\n"
        "storage: !Local\n"
        f"  path: '{storage_path(database)}/storage'\n"
        "\n"
        "externalSource: !Postgres\n"
        f"  remote: {remote}\n"
        f"  publicationName: {publication}\n"
        f"  slotName: {slot}\n"
        "  indexer: !DirectMirror {}\n"
        "$$"
    )


def detach_statement(database: str) -> str:
    return f"DETACH DATABASE {database}"


def mirror_count_statement(database: str, table: str) -> str:
    return f"SELECT count(*) FROM {database}.public.{table}"


def first_value(rows: list[dict[str, object]]) -> object:
    return next(iter(rows[0].values())) if rows else None


def is_attached(session: Session, database: str) -> bool:
    return first_value(session.rows(ATTACHED, (database,))) == 1


def mirror_count(session: Session, database: str, table: str) -> int | None:
    try:
        rows = session.rows(mirror_count_statement(database, table), ())
    except psycopg.Error:
        return None
    value = first_value(rows)
    if isinstance(value, int):
        return value
    raise TypeError(f"count returned {value!r}")


def attach(
    session: Session,
    database: str,
    statement: str,
    *,
    attempts: int = 30,
    sleep: Callable[[float], None] = time.sleep,
) -> Literal["applied", "present"]:
    if is_attached(session, database):
        return "present"
    attempt = 0
    while True:
        attempt += 1
        try:
            session.execute(statement)
            return "applied"
        except psycopg.Error as error:
            if DETACHING not in str(error) or attempt >= attempts:
                raise
            sleep(1)


def detach(session: Session, database: str) -> Literal["detached", "absent"]:
    if not is_attached(session, database):
        return "absent"
    session.execute(detach_statement(database))
    return "detached"


def wait_for_rows(
    session: Session,
    database: str,
    table: str,
    expected: int,
    *,
    timeout: float = 120.0,
    interval: float = 1.0,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[int | None, bool]:
    deadline = clock() + timeout
    count = mirror_count(session, database, table)
    while count != expected and clock() < deadline:
        sleep(interval)
        count = mirror_count(session, database, table)
    return count, count == expected
