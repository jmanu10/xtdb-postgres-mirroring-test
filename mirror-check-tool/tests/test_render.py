import datetime

from app.cli import SHOWN, differences_table, styled, summary_table
from lib.diff import Difference
from lib.render import difference_cells, group_cells, markdown_document, shown
from lib.summary import Group, summarize


def test_cells_carry_detail_only_when_values_differ_and_cut_long_values() -> None:
    assert difference_cells(Difference("people", "missing", 7)) == (
        "people",
        "missing",
        "7",
        "",
        "",
        "",
    )
    long = Difference("people", "differs", 7, "bio", "x" * 100, "y")
    assert difference_cells(long) == (
        "people",
        "differs",
        "7",
        "bio",
        f"'{'x' * 58}…",
        "'y'",
    )
    assert shown("x" * 300, 200).endswith("…")


def test_the_summary_counts_distinct_rows_per_table_column_and_kind() -> None:
    found = [
        Difference("people", "elements", 1, "skills", ["a"], ['"a"']),
        Difference("people", "elements", 1, "skills/inner", ["b"], ['"b"']),
        Difference("people", "elements", 2, "skills", ["c"], ['"c"']),
        Difference("people", "differs", 2, "name", "x", "y"),
        Difference("people", "missing", 3),
        Difference("companies", "extra", 4),
    ]
    assert summarize(found) == [
        Group("companies", "", "extra", 1, found[5]),
        Group("people", "skills", "elements", 2, found[0]),
        Group("people", "", "missing", 1, found[4]),
        Group("people", "name", "differs", 1, found[3]),
    ]
    assert group_cells(summarize(found)[1]) == (
        "people",
        "skills",
        "elements",
        "2",
        "1",
        "['a']",
        "['\"a\"']",
    )


def test_the_terminal_table_shows_the_first_differences_and_names_the_total() -> None:
    found = [Difference("people", "missing", key) for key in range(SHOWN + 5)]
    table = differences_table(found)
    assert table.title == f"differences ({SHOWN} of {SHOWN + 5})"
    assert table.row_count == SHOWN
    assert differences_table(found[:3]).title == "differences"
    assert summary_table(found).row_count == 1


def test_the_markdown_document_holds_both_views_and_escapes_pipes() -> None:
    found = [Difference("people", "differs", 1, "name", "a|b", "c")]
    when = datetime.datetime(2026, 9, 3, 12, 0, tzinfo=datetime.UTC)
    text = markdown_document(found, summarize(found), [("people", 71)], when)
    assert text.startswith("# mirror-diff\n\nRun at 2026-09-03T12:00:00+00:00")
    assert "over people (71 rows): 1 differences." in text
    assert "## Summary" in text and "## Differences" in text
    assert "| people | differs | 1 | name | 'a\\|b' | 'c' |" in text


def test_data_cells_are_escaped_so_brackets_are_not_markup() -> None:
    cells = ("people", "differs", "7", "bio", "'see [link] here [/]'", "'x'")
    assert styled(cells, 1) == [
        "people",
        "[cyan]differs[/]",
        "7",
        "bio",
        "'see \\[link] here \\[/]'",
        "'x'",
    ]
