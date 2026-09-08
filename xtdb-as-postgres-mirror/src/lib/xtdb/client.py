import datetime
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol

import psycopg

type Row = dict[str, object]


def decoded(value: object) -> object:
    if isinstance(value, datetime.date | datetime.time):
        return value.isoformat()
    return value


class Session(Protocol):
    def execute(self, statement: str) -> None: ...

    def scalar(self, statement: str) -> object: ...

    def rows(self, statement: str, parameters: Sequence[object]) -> list[Row]: ...


@dataclass(frozen=True)
class PsycopgSession:
    connection: psycopg.Connection[tuple[Any, ...]]

    def execute(self, statement: str) -> None:
        self.connection.execute(statement)

    def scalar(self, statement: str) -> object:
        row = self.connection.execute(statement).fetchone()
        return None if row is None else row[0]

    def rows(self, statement: str, parameters: Sequence[object]) -> list[Row]:
        cursor = self.connection.execute(statement, tuple(parameters))
        description = cursor.description
        columns = [column.name for column in description] if description else []
        return [
            {column: decoded(value) for column, value in zip(columns, row)}
            for row in cursor.fetchall()
        ]


@contextmanager
def session(url: str) -> Generator[PsycopgSession]:
    with psycopg.connect(url, autocommit=True) as connection:
        yield PsycopgSession(connection)
