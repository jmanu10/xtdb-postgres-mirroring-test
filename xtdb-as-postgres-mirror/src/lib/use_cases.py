from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

USE_CASE_FILES = ("schema.sql", "rows.json")


class UseCaseError(Exception):
    pass


def sql_name(folder: str) -> str:
    return "uc_" + folder.replace("-", "_")


class UseCaseRows(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: dict[str, str]
    rows: list[dict[str, object]]

    @model_validator(mode="after")
    def rows_name_declared_columns(self) -> "UseCaseRows":
        declared = set(self.columns)
        for row in self.rows:
            if not row:
                raise ValueError("a row needs at least one column")
            undeclared = sorted(set(row) - declared)
            if undeclared:
                raise ValueError(f"row keys {undeclared} are not declared columns")
        return self


@dataclass(frozen=True)
class UseCase:
    name: str
    sql_name: str
    path: Path
    statements: tuple[str, ...]
    columns: dict[str, str]
    rows: list[dict[str, object]]


def discover(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    return sorted(
        entry.name
        for entry in root.iterdir()
        if entry.is_dir()
        and all((entry / filename).is_file() for filename in USE_CASE_FILES)
    )


def statements_from_schema(text: str) -> tuple[str, ...]:
    return tuple(
        statement.strip() for statement in text.split(";") if statement.strip()
    )


def load(root: Path, name: str) -> UseCase:
    path = root / name
    if not path.is_dir():
        raise UseCaseError(f"{name} is not a use case under {root}")
    missing = [
        filename for filename in USE_CASE_FILES if not (path / filename).is_file()
    ]
    if missing:
        raise UseCaseError(f"{name} is missing {', '.join(missing)}")
    try:
        rows = UseCaseRows.model_validate_json((path / "rows.json").read_text())
    except ValidationError as error:
        raise UseCaseError(f"{name} has an invalid rows.json: {error}") from error
    return UseCase(
        name=name,
        sql_name=sql_name(name),
        path=path,
        statements=statements_from_schema((path / "schema.sql").read_text()),
        columns=rows.columns,
        rows=rows.rows,
    )
