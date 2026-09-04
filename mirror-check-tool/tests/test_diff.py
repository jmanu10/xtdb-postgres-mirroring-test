from lib.diff import Difference, Rows, differences, paths, without_nulls


def test_null_valued_keys_are_dropped_at_every_depth() -> None:
    value = {"a": None, "b": [{"c": None, "d": 1}], "e": {"f": None}}
    assert without_nulls(value) == {"b": [{"d": 1}], "e": {}}


def test_scalars_and_list_items_survive_normalization() -> None:
    assert without_nulls([1, None, "x"]) == [1, None, "x"]
    assert without_nulls("text") == "text"
    assert without_nulls(None) is None


def test_paths_descend_into_dicts_and_stop_at_lists() -> None:
    source: object = {"a": [{"b": 1}, {"b": 2}], "c": "x"}
    mirror: object = {"a": [{"b": 1}, {"b": 3}], "c": "x", "d": 4}
    assert list(paths(source, mirror, "col")) == [
        ("col/a", "elements", [{"b": 2}], [{"b": 3}]),
        ("col/d", "differs", None, 4),
    ]


def test_lists_report_the_elements_each_side_holds_alone() -> None:
    source = ["information officer", "cio", "a, b"]
    mirror = ['"information officer"', "cio", "a", " b"]
    assert list(paths(source, mirror, "skills")) == [
        (
            "skills",
            "elements",
            ["information officer", "a, b"],
            ['"information officer"', "a", " b"],
        )
    ]


def test_a_reordered_list_is_one_plain_difference() -> None:
    assert list(paths([1, 2], [2, 1], "col")) == [("col", "differs", [1, 2], [2, 1])]


def test_rows_missing_extra_and_differing_are_reported_in_key_order() -> None:
    source: Rows = {
        1: {"_id": 1, "name": "Ada"},
        2: {"_id": 2, "name": "Brivo"},
        3: {"_id": 3, "name": "Cyan"},
    }
    mirror: Rows = {
        2: {"_id": 2, "name": "BRIVO"},
        3: {"_id": 3, "name": "Cyan"},
        4: {"_id": 4, "name": "Dune"},
    }
    assert differences("companies", source, mirror) == [
        Difference("companies", "missing", 1),
        Difference("companies", "differs", 2, "name", "Brivo", "BRIVO"),
        Difference("companies", "extra", 4),
    ]


def test_json_nulls_dropped_by_the_mirror_are_not_differences() -> None:
    source: Rows = {1: {"_id": 1, "revenue": {"a": None, "b": {"c": 1}}}}
    mirror: Rows = {1: {"_id": 1, "revenue": {"b": {"c": 1}}}}
    assert differences("companies", source, mirror) == []


def test_a_column_the_mirror_never_saw_reads_as_null() -> None:
    source: Rows = {1: {"_id": 1, "hq_latitude": None}}
    mirror: Rows = {1: {"_id": 1}}
    assert differences("companies", source, mirror) == []


def test_a_column_only_the_mirror_holds_is_a_difference() -> None:
    source: Rows = {1: {"_id": 1}}
    mirror: Rows = {1: {"_id": 1, "dropped_upstream": "kept"}}
    assert differences("companies", source, mirror) == [
        Difference("companies", "differs", 1, "dropped_upstream", None, "kept")
    ]


def test_an_absent_mirror_table_reports_every_source_row_missing() -> None:
    source: Rows = {"a:b": {"_id": "a:b"}, "a:c": {"_id": "a:c"}}
    assert [d.kind for d in differences("cohorts", source, {})] == [
        "missing",
        "missing",
    ]


def test_the_column_is_the_first_path_segment() -> None:
    assert Difference("t", "differs", 1, "revenue/source_1/amount").column == "revenue"
    assert Difference("t", "missing", 1).column == ""
