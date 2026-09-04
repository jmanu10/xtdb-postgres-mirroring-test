from collections import defaultdict
from dataclasses import dataclass

from lib.diff import Difference

type GroupKey = tuple[str, str, str]


@dataclass(frozen=True)
class Group:
    table: str
    column: str
    kind: str
    rows: int
    example: Difference


def summarize(found: list[Difference]) -> list[Group]:
    keys: dict[GroupKey, set[str]] = defaultdict(set)
    first: dict[GroupKey, Difference] = {}
    for difference in found:
        group = (difference.table, difference.column, difference.kind)
        keys[group].add(str(difference.key))
        first.setdefault(group, difference)
    groups = [
        Group(table, column, kind, len(keys[group]), first[group])
        for group in keys
        for table, column, kind in [group]
    ]
    return sorted(groups, key=lambda group: (group.table, -group.rows, group.column))
