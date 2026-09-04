from pathlib import Path

import pytest
from lib.settings import load_settings
from lib.use_cases import (
    UseCaseError,
    UseCaseRows,
    discover,
    load,
    sql_name,
)


def write_case(
    root: Path,
    name: str,
    columns: dict[str, str],
    rows: list[dict[str, object]],
) -> Path:
    folder = root / name
    folder.mkdir()
    table = sql_name(name)
    (folder / "schema.sql").write_text(
        f'CREATE TABLE IF NOT EXISTS "{table}" ("id" BIGINT PRIMARY KEY);\n'
        f'ALTER TABLE "{table}" REPLICA IDENTITY FULL;\n'
    )
    (folder / "rows.json").write_text(
        UseCaseRows(columns=columns, rows=rows).model_dump_json()
    )
    return folder


def test_sql_name_replaces_dashes_and_prefixes_uc() -> None:
    assert sql_name("text-array") == "uc_text_array"
    assert sql_name("double-all-null") == "uc_double_all_null"
    assert sql_name("single") == "uc_single"


def test_use_case_rows_rejects_a_row_with_an_undeclared_column() -> None:
    with pytest.raises(ValueError, match="extra"):
        UseCaseRows(columns={"id": "bigint"}, rows=[{"id": 1, "extra": "nope"}])


def test_use_case_rows_accepts_a_subset_of_declared_columns() -> None:
    rows = UseCaseRows(columns={"id": "bigint", "value": "text"}, rows=[{"id": 1}])
    assert rows.rows == [{"id": 1}]


def test_discover_finds_only_folders_with_all_three_files(tmp_path: Path) -> None:
    write_case(tmp_path, "sample-case", {"id": "bigint"}, [{"id": 1}])
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    (incomplete / "schema.sql").write_text("")
    assert discover(tmp_path) == ["sample-case"]


def test_discover_is_sorted(tmp_path: Path) -> None:
    write_case(tmp_path, "zebra", {"id": "bigint"}, [{"id": 1}])
    write_case(tmp_path, "aardvark", {"id": "bigint"}, [{"id": 1}])
    assert discover(tmp_path) == ["aardvark", "zebra"]


def test_discover_on_a_missing_root_is_empty(tmp_path: Path) -> None:
    assert discover(tmp_path / "nowhere") == []


def test_load_parses_statements_columns_and_rows(tmp_path: Path) -> None:
    write_case(tmp_path, "sample-case", {"id": "bigint"}, [{"id": 1}, {"id": 2}])
    case = load(tmp_path, "sample-case")
    assert case.name == "sample-case"
    assert case.sql_name == "uc_sample_case"
    assert case.path == tmp_path / "sample-case"
    assert case.statements == (
        'CREATE TABLE IF NOT EXISTS "uc_sample_case" ("id" BIGINT PRIMARY KEY)',
        'ALTER TABLE "uc_sample_case" REPLICA IDENTITY FULL',
    )
    assert case.columns == {"id": "bigint"}
    assert case.rows == [{"id": 1}, {"id": 2}]


def test_load_raises_for_a_missing_folder(tmp_path: Path) -> None:
    with pytest.raises(UseCaseError, match="not a use case"):
        load(tmp_path, "not-there")


def test_load_raises_naming_the_missing_files(tmp_path: Path) -> None:
    folder = tmp_path / "half-a-case"
    folder.mkdir()
    (folder / "schema.sql").write_text("SELECT 1;")
    with pytest.raises(UseCaseError, match="rows.json"):
        load(tmp_path, "half-a-case")


def test_use_case_rows_rejects_an_empty_row() -> None:
    with pytest.raises(ValueError, match="at least one column"):
        UseCaseRows(columns={"id": "bigint"}, rows=[{}])


def test_load_wraps_an_invalid_rows_json_in_a_use_case_error(tmp_path: Path) -> None:
    folder = write_case(tmp_path, "broken-json", {"id": "bigint"}, [{"id": 1}])
    (folder / "rows.json").write_text('{"columns": {"id": "bigint"}, "rows": [')
    with pytest.raises(UseCaseError, match="invalid rows.json"):
        load(tmp_path, "broken-json")


def test_the_committed_use_cases_all_discover_and_load() -> None:
    root = load_settings().use_cases_path
    names = discover(root)
    assert names == [
        "bigint-array-null",
        "double-all-null",
        "jsonb-big-integers",
        "jsonb-null-values",
        "jsonb-top-level-null",
        "text-array",
    ]
    for name in names:
        case = load(root, name)
        assert case.sql_name == sql_name(name)
        assert case.statements
        assert case.rows
        assert "id" in case.columns
