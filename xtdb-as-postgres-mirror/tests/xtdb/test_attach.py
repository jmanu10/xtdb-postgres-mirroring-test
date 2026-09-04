from collections.abc import Sequence
from dataclasses import dataclass, field

import psycopg
import pytest
from lib.xtdb.attach import (
    ATTACHED,
    DETACHING,
    attach,
    attach_statement,
    detach,
    detach_statement,
    is_attached,
    mirror_count_statement,
    storage_path,
    wait_for_rows,
)
from lib.xtdb.client import Row


@dataclass
class FakeSession:
    attached_databases: set[str] = field(default_factory=set)
    counts: dict[str, int] = field(default_factory=dict)
    execute_errors: list[Exception] = field(default_factory=list)
    executed: list[str] = field(default_factory=list)

    def execute(self, statement: str) -> None:
        self.executed.append(statement)
        if self.execute_errors:
            raise self.execute_errors.pop(0)

    def scalar(self, statement: str) -> object:
        return None

    def rows(self, statement: str, parameters: Sequence[object]) -> list[Row]:
        if statement == ATTACHED:
            (database,) = parameters
            present = 1 if database in self.attached_databases else 0
            return [{"count": present}]
        return [{"count": self.counts.get(statement, 0)}]


def test_attach_statement_matches_the_documented_shape() -> None:
    statement = attach_statement(
        "uc_text_array", "mirror_pg", "uc_text_array", "uc_text_array"
    )
    assert statement == (
        "ATTACH DATABASE uc_text_array WITH $$log: !Local\n"
        "  path: '/var/lib/xtdb/uc_text_array/log'\n"
        "storage: !Local\n"
        "  path: '/var/lib/xtdb/uc_text_array/storage'\n"
        "\n"
        "externalSource: !Postgres\n"
        "  remote: mirror_pg\n"
        "  publicationName: uc_text_array\n"
        "  slotName: uc_text_array\n"
        "  indexer: !DirectMirror {}\n"
        "$$"
    )


def test_detach_statement_names_the_database() -> None:
    assert detach_statement("uc_x") == "DETACH DATABASE uc_x"


def test_mirror_count_statement_names_the_secondary_database_and_table() -> None:
    assert (
        mirror_count_statement("uc_x", "uc_x")
        == "SELECT count(*) FROM uc_x.public.uc_x"
    )


def test_storage_path_is_scoped_to_the_database() -> None:
    assert storage_path("uc_x") == "/var/lib/xtdb/uc_x"


def test_attached_probe_and_detaching_conflict_constants() -> None:
    assert ATTACHED == "SELECT count(*) FROM pg_catalog.pg_database WHERE datname = %s"
    assert DETACHING == "db-being-detached"


def test_is_attached_reflects_the_probe_result() -> None:
    session = FakeSession(attached_databases={"uc_x"})
    assert is_attached(session, "uc_x") is True
    assert is_attached(session, "uc_y") is False


def test_attach_returns_present_without_executing_when_already_attached() -> None:
    session = FakeSession(attached_databases={"uc_x"})
    result = attach(session, "uc_x", "ATTACH DATABASE uc_x ...", sleep=lambda _: None)
    assert result == "present"
    assert session.executed == []


def test_attach_executes_and_returns_applied_when_not_yet_attached() -> None:
    session = FakeSession()
    result = attach(session, "uc_x", "ATTACH DATABASE uc_x ...", sleep=lambda _: None)
    assert result == "applied"
    assert session.executed == ["ATTACH DATABASE uc_x ..."]


def test_attach_retries_while_the_conflict_is_detaching() -> None:
    session = FakeSession(
        execute_errors=[
            psycopg.Error(f"conflict: {DETACHING}"),
            psycopg.Error(f"conflict: {DETACHING}"),
        ]
    )
    sleeps: list[float] = []
    result = attach(session, "uc_x", "ATTACH ...", attempts=5, sleep=sleeps.append)
    assert result == "applied"
    assert sleeps == [1, 1]
    assert len(session.executed) == 3


def test_attach_raises_after_exhausting_attempts() -> None:
    session = FakeSession(execute_errors=[psycopg.Error(DETACHING) for _ in range(3)])
    with pytest.raises(psycopg.Error, match=DETACHING):
        attach(session, "uc_x", "ATTACH ...", attempts=3, sleep=lambda _: None)


def test_attach_raises_immediately_on_an_unrelated_error() -> None:
    session = FakeSession(execute_errors=[psycopg.Error("permission denied")])

    def must_not_sleep(seconds: float) -> None:
        raise AssertionError("must not sleep on a non-detaching error")

    with pytest.raises(psycopg.Error, match="permission denied"):
        attach(session, "uc_x", "ATTACH ...", sleep=must_not_sleep)


def test_detach_reports_absent_when_not_attached() -> None:
    session = FakeSession()
    assert detach(session, "uc_x") == "absent"
    assert session.executed == []


def test_detach_executes_and_reports_detached_when_attached() -> None:
    session = FakeSession(attached_databases={"uc_x"})
    assert detach(session, "uc_x") == "detached"
    assert session.executed == [detach_statement("uc_x")]


def test_wait_for_rows_converges_once_the_count_matches() -> None:
    statement = mirror_count_statement("uc_x", "uc_x")
    session = FakeSession(counts={statement: 0})
    clock_values = iter([0.0, 0.0, 1.0])
    sleeps: list[float] = []

    def bump_count(seconds: float) -> None:
        sleeps.append(seconds)
        session.counts[statement] = 2

    count, converged = wait_for_rows(
        session,
        "uc_x",
        "uc_x",
        2,
        timeout=10.0,
        interval=1.0,
        clock=lambda: next(clock_values),
        sleep=bump_count,
    )
    assert converged is True
    assert count == 2
    assert sleeps == [1.0]


def test_wait_for_rows_times_out_when_the_count_never_matches() -> None:
    statement = mirror_count_statement("uc_x", "uc_x")
    session = FakeSession(counts={statement: 0})
    clock_values = iter([0.0, 0.0, 5.0, 11.0])

    count, converged = wait_for_rows(
        session,
        "uc_x",
        "uc_x",
        2,
        timeout=10.0,
        interval=1.0,
        clock=lambda: next(clock_values),
        sleep=lambda _: None,
    )
    assert converged is False
    assert count == 0


def test_wait_for_rows_never_converges_on_an_unanswerable_mirror() -> None:
    class ErroringSession:
        def execute(self, statement: str) -> None: ...

        def scalar(self, statement: str) -> object:
            return None

        def rows(self, statement: str, parameters: Sequence[object]) -> list[Row]:
            raise psycopg.Error("table does not exist yet")

    count, converged = wait_for_rows(
        ErroringSession(),
        "uc_x",
        "uc_x",
        0,
        timeout=0.0,
        interval=0.0,
        clock=lambda: 0.0,
        sleep=lambda _: None,
    )
    assert count is None
    assert converged is False


def test_wait_for_rows_rejects_a_non_integer_count() -> None:
    statement = mirror_count_statement("uc_x", "uc_x")

    class OddSession(FakeSession):
        def rows(self, statement: str, parameters: Sequence[object]) -> list[Row]:
            return [{"count": "2"}]

    with pytest.raises(TypeError):
        wait_for_rows(OddSession(), "uc_x", "uc_x", 2, timeout=0.0, clock=lambda: 0.0)
