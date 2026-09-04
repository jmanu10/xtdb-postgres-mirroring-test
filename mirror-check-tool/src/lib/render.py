import datetime

from lib.diff import Difference
from lib.summary import Group

WIDTH = 60
FILE_WIDTH = 200
DIFFERENCE_HEADERS = ("table", "kind", "key", "path", "source", "mirror")
GROUP_HEADERS = ("table", "column", "kind", "rows", "example key", "source", "mirror")


def shown(value: object, width: int = WIDTH) -> str:
    text = repr(value)
    return text if len(text) <= width else f"{text[: width - 1]}…"


def difference_cells(difference: Difference, width: int = WIDTH) -> tuple[str, ...]:
    detail = difference.kind in ("differs", "elements")
    return (
        difference.table,
        difference.kind,
        str(difference.key),
        difference.path if detail else "",
        shown(difference.source, width) if detail else "",
        shown(difference.mirror, width) if detail else "",
    )


def group_cells(group: Group, width: int = WIDTH) -> tuple[str, ...]:
    _, _, key, _, source, mirror = difference_cells(group.example, width)
    return (group.table, group.column, group.kind, str(group.rows), key, source, mirror)


def markdown_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def markdown_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(map(markdown_cell, row)) + " |" for row in rows)
    return "\n".join(lines)


def markdown_document(
    found: list[Difference],
    groups: list[Group],
    counts: list[tuple[str, int]],
    when: datetime.datetime,
) -> str:
    tables = ", ".join(f"{table} ({rows} rows)" for table, rows in counts)
    return (
        "\n\n".join(
            [
                "# mirror-diff",
                f"Run at {when.isoformat(timespec='seconds')} over {tables}:"
                f" {len(found)} differences.",
                "## Summary",
                markdown_table(
                    GROUP_HEADERS, [group_cells(group, FILE_WIDTH) for group in groups]
                ),
                "## Differences",
                markdown_table(
                    DIFFERENCE_HEADERS,
                    [difference_cells(difference, FILE_WIDTH) for difference in found],
                ),
            ]
        )
        + "\n"
    )
