import datetime

from lib.xtdb.client import decoded


def test_timestamps_decode_to_isoformat_and_structs_are_left_alone() -> None:
    stamp = datetime.datetime(2026, 9, 2, 1, 54, 35, tzinfo=datetime.UTC)
    assert decoded(stamp) == "2026-09-02T01:54:35+00:00"
    assert decoded(datetime.date(2026, 9, 2)) == "2026-09-02"
    payload = [{"n": 1}]
    assert decoded(payload) is payload
    assert decoded(None) is None
