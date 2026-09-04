from collections.abc import Iterator
from dataclasses import dataclass

type Row = dict[str, object]
type Rows = dict[object, Row]
type Leaf = tuple[str, str, object, object]

KEY = "_id"


@dataclass(frozen=True)
class Difference:
    table: str
    kind: str
    key: object
    path: str = ""
    source: object = None
    mirror: object = None

    @property
    def column(self) -> str:
        return self.path.partition("/")[0]


def without_nulls(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: without_nulls(item) for key, item in value.items() if item is not None
        }
    if isinstance(value, list):
        return [without_nulls(item) for item in value]
    return value


def only(left: list[object], right: list[object]) -> list[object]:
    return [item for item in left if item not in right]


def paths(source: object, mirror: object, path: str) -> Iterator[Leaf]:
    if isinstance(source, dict) and isinstance(mirror, dict):
        for key in sorted(set(source) | set(mirror)):
            yield from paths(source.get(key), mirror.get(key), f"{path}/{key}")
    elif isinstance(source, list) and isinstance(mirror, list):
        if source == mirror:
            return
        source_only, mirror_only = only(source, mirror), only(mirror, source)
        if source_only or mirror_only:
            yield path, "elements", source_only, mirror_only
        else:
            yield path, "differs", source, mirror
    elif source != mirror:
        yield path, "differs", source, mirror


def differences(table: str, source: Rows, mirror: Rows) -> list[Difference]:
    found: list[Difference] = []
    for key in sorted(set(source) | set(mirror), key=str):
        if key not in mirror:
            found.append(Difference(table, "missing", key))
        elif key not in source:
            found.append(Difference(table, "extra", key))
        else:
            found.extend(row_differences(table, key, source[key], mirror[key]))
    return found


def row_differences(
    table: str, key: object, source: Row, mirror: Row
) -> list[Difference]:
    return [
        Difference(table, kind, key, path, left, right)
        for column in sorted((set(source) | set(mirror)) - {KEY})
        for path, kind, left, right in paths(
            without_nulls(source.get(column)), mirror.get(column), column
        )
    ]
