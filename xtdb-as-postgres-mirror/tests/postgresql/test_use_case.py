from dataclasses import dataclass, field
from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Jsonb

from lib.postgresql.replication import drop_publication_statement
from lib.postgresql.use_case import (
    DROP_SLOT,
    PUBLICATION_EXISTS,
    SLOT_ACTIVE,
    SLOT_EXISTS,
    TABLE_EXISTS,
    count_statement,
    counted,
    drop_slot,
    drop_table_statement,
    insert_statement,
    publish_table_statement,
    row_parameters,
    seed,
    teardown,
)
from lib.use_cases import UseCase


@dataclass
class FakeSource:
    answers: dict[str, list[tuple[object, ...]]] = field(default_factory=dict)
    errors: dict[str, list[Exception]] = field(default_factory=dict)
    calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    def execute(
        self, statement: str, parameters: tuple[object, ...] = ()
    ) -> list[tuple[object, ...]]:
        self.calls.append((statement, parameters))
        pending = self.errors.get(statement)
        if pending:
            raise pending.pop(0)
        return self.answers.get(statement, [(0,)])

    def statements(self) -> list[str]:
        return [statement for statement, _ in self.calls]


def sample_case(
    columns: dict[str, str] | None = None, rows: list[dict[str, object]] | None = None
) -> UseCase:
    return UseCase(
        name="sample",
        sql_name="uc_sample",
        path=Path("/dev/null"),
        statements=('CREATE TABLE "uc_sample" ("id" BIGINT PRIMARY KEY)',),
        columns=columns if columns is not None else {"id": "bigint"},
        rows=rows if rows is not None else [{"id": 1}, {"id": 2}],
    )


def test_insert_statement_quotes_identifiers_and_binds_positionally() -> None:
    assert insert_statement("uc_x", ["id", "values"]) == (
        'INSERT INTO "uc_x" ("id", "values") VALUES (%s, %s)'
    )


def test_publish_table_statement_names_the_table_and_generated_columns() -> None:
    assert publish_table_statement("uc_x", "uc_x", "stored") == (
        'CREATE PUBLICATION "uc_x" FOR TABLE "uc_x"'
        " WITH (publish_generated_columns = 'stored')"
    )


def test_drop_table_statement_is_idempotent() -> None:
    assert drop_table_statement("uc_x") == 'DROP TABLE IF EXISTS "uc_x"'


def test_catalog_probes_bind_the_name_as_a_parameter() -> None:
    assert TABLE_EXISTS.endswith("tablename = %s")
    assert PUBLICATION_EXISTS.endswith("pubname = %s")
    assert SLOT_EXISTS.endswith("slot_name = %s")
    assert DROP_SLOT == "SELECT pg_drop_replication_slot(%s)"


def test_count_statement_counts_the_use_case_table() -> None:
    assert count_statement("uc_x") == 'SELECT count(*) FROM "uc_x"'


def test_counted_rejects_anything_but_an_integer() -> None:
    assert counted([(3,)]) == 3
    with pytest.raises(TypeError):
        counted([("3",)])
    with pytest.raises(TypeError):
        counted([])


def test_row_parameters_wraps_jsonb_including_none() -> None:
    columns = {"id": "bigint", "payload": "jsonb"}
    parameters = row_parameters(columns, {"id": 1, "payload": None})
    assert parameters[0] == 1
    assert isinstance(parameters[1], Jsonb)
    assert parameters[1].obj is None


def test_row_parameters_passes_arrays_and_scalars_through() -> None:
    columns = {"id": "bigint", "values": "text[]"}
    assert row_parameters(columns, {"id": 2, "values": ["a", None]}) == (
        2,
        ["a", None],
    )


def test_seed_creates_inserts_and_publishes_when_nothing_exists() -> None:
    case = sample_case()
    source = FakeSource(answers={count_statement("uc_sample"): [(2,)]})
    assert seed(source, case, "stored") == ("seeded", 2)
    assert source.calls == [
        (TABLE_EXISTS, ("uc_sample",)),
        (case.statements[0], ()),
        (insert_statement("uc_sample", ("id",)), (1,)),
        (insert_statement("uc_sample", ("id",)), (2,)),
        (PUBLICATION_EXISTS, ("uc_sample",)),
        (publish_table_statement("uc_sample", "uc_sample", "stored"), ()),
        (count_statement("uc_sample"), ()),
    ]


def test_seed_leaves_an_existing_table_alone_and_reports_present() -> None:
    case = sample_case()
    source = FakeSource(
        answers={
            TABLE_EXISTS: [(1,)],
            PUBLICATION_EXISTS: [(1,)],
            count_statement("uc_sample"): [(2,)],
        }
    )
    assert seed(source, case, "stored") == ("present", 2)
    assert source.statements() == [
        TABLE_EXISTS,
        PUBLICATION_EXISTS,
        count_statement("uc_sample"),
    ]


def test_seed_recreates_a_missing_publication_over_an_existing_table() -> None:
    case = sample_case()
    source = FakeSource(
        answers={TABLE_EXISTS: [(1,)], count_statement("uc_sample"): [(2,)]}
    )
    assert seed(source, case, "stored") == ("present", 2)
    assert publish_table_statement("uc_sample", "uc_sample", "stored") in (
        source.statements()
    )


def test_drop_slot_reports_absent_without_dropping() -> None:
    source = FakeSource()
    assert drop_slot(source, "uc_x", sleep=lambda _: None) == "absent"
    assert source.statements() == [SLOT_EXISTS]


def test_drop_slot_retries_while_xtdb_still_holds_the_slot() -> None:
    source = FakeSource(
        answers={SLOT_EXISTS: [(1,)]},
        errors={DROP_SLOT: [psycopg.Error(f'slot "uc_x" {SLOT_ACTIVE} for PID 7')]},
    )
    sleeps: list[float] = []
    assert drop_slot(source, "uc_x", sleep=sleeps.append) == "dropped"
    assert sleeps == [1]
    assert source.statements().count(DROP_SLOT) == 2


def test_drop_slot_gives_up_after_the_attempts() -> None:
    source = FakeSource(
        answers={SLOT_EXISTS: [(1,)]},
        errors={DROP_SLOT: [psycopg.Error(SLOT_ACTIVE) for _ in range(2)]},
    )
    with pytest.raises(psycopg.Error, match=SLOT_ACTIVE):
        drop_slot(source, "uc_x", attempts=2, sleep=lambda _: None)


def test_drop_slot_raises_immediately_on_an_unrelated_error() -> None:
    source = FakeSource(
        answers={SLOT_EXISTS: [(1,)]},
        errors={DROP_SLOT: [psycopg.Error("permission denied")]},
    )

    def must_not_sleep(seconds: float) -> None:
        raise AssertionError("must not sleep on an unrelated error")

    with pytest.raises(psycopg.Error, match="permission denied"):
        drop_slot(source, "uc_x", sleep=must_not_sleep)


def test_teardown_drops_publication_and_table_before_the_slot() -> None:
    case = sample_case()
    source = FakeSource(answers={SLOT_EXISTS: [(1,)]})
    assert teardown(source, case, sleep=lambda _: None) == "dropped"
    assert source.calls == [
        (drop_publication_statement("uc_sample"), ()),
        (drop_table_statement("uc_sample"), ()),
        (SLOT_EXISTS, ("uc_sample",)),
        (DROP_SLOT, ("uc_sample",)),
    ]
