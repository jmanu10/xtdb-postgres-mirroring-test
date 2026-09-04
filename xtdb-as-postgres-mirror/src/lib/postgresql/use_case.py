import time
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import psycopg
from psycopg.types.json import Jsonb

from lib.postgresql.replication import drop_publication_statement
from lib.use_cases import UseCase

type SeedOutcome = Literal["seeded", "present"]

SLOT_ACTIVE = "is active"

TABLE_EXISTS = (
    "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tablename = %s"
)
PUBLICATION_EXISTS = "SELECT count(*) FROM pg_publication WHERE pubname = %s"
SLOT_EXISTS = "SELECT count(*) FROM pg_replication_slots WHERE slot_name = %s"
DROP_SLOT = "SELECT pg_drop_replication_slot(%s)"


def insert_statement(table: str, columns: Sequence[str]) -> str:
    names = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join("%s" for _ in columns)
    return f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})'


def publish_table_statement(name: str, table: str, generated: str) -> str:
    return (
        f'CREATE PUBLICATION "{name}" FOR TABLE "{table}"'
        f" WITH (publish_generated_columns = '{generated}')"
    )


def drop_table_statement(table: str) -> str:
    return f'DROP TABLE IF EXISTS "{table}"'


def count_statement(table: str) -> str:
    return f'SELECT count(*) FROM "{table}"'


def row_parameters(
    columns: dict[str, str], row: dict[str, object]
) -> tuple[object, ...]:
    return tuple(
        Jsonb(value) if columns[column] == "jsonb" else value
        for column, value in row.items()
    )


class SourceSession(Protocol):
    def execute(
        self, statement: str, parameters: tuple[object, ...] = ()
    ) -> list[tuple[object, ...]]: ...


def counted(rows: list[tuple[object, ...]]) -> int:
    value = rows[0][0] if rows else None
    if isinstance(value, int):
        return value
    raise TypeError(f"count returned {value!r}")


def exists(session: SourceSession, statement: str, name: str) -> bool:
    return counted(session.execute(statement, (name,))) > 0


def seed(
    session: SourceSession, case: UseCase, generated: str
) -> tuple[SeedOutcome, int]:
    outcome: SeedOutcome = "present"
    if not exists(session, TABLE_EXISTS, case.sql_name):
        for statement in case.statements:
            session.execute(statement)
        for row in case.rows:
            session.execute(
                insert_statement(case.sql_name, tuple(row)),
                row_parameters(case.columns, row),
            )
        outcome = "seeded"
    if not exists(session, PUBLICATION_EXISTS, case.sql_name):
        session.execute(
            publish_table_statement(case.sql_name, case.sql_name, generated)
        )
    return outcome, counted(session.execute(count_statement(case.sql_name)))


def drop_slot(
    session: SourceSession,
    slot: str,
    *,
    attempts: int = 30,
    sleep: Callable[[float], None] = time.sleep,
) -> Literal["dropped", "absent"]:
    attempt = 0
    while True:
        attempt += 1
        if not exists(session, SLOT_EXISTS, slot):
            return "absent"
        try:
            session.execute(DROP_SLOT, (slot,))
            return "dropped"
        except psycopg.Error as error:
            if SLOT_ACTIVE not in str(error) or attempt >= attempts:
                raise
            sleep(1)


def teardown(
    session: SourceSession,
    case: UseCase,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> Literal["dropped", "absent"]:
    session.execute(drop_publication_statement(case.sql_name))
    session.execute(drop_table_statement(case.sql_name))
    return drop_slot(session, case.sql_name, sleep=sleep)


@dataclass(frozen=True)
class PsycopgSource:
    connection: psycopg.Connection[tuple[Any, ...]]

    def execute(
        self, statement: str, parameters: tuple[object, ...] = ()
    ) -> list[tuple[object, ...]]:
        cursor = self.connection.execute(statement, parameters or None)
        if cursor.description is None:
            return []
        return cursor.fetchall()


@contextmanager
def source(url: str) -> Generator[PsycopgSource]:
    with psycopg.connect(url, autocommit=True) as connection:
        yield PsycopgSource(connection)
