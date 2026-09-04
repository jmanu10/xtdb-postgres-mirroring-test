from app.cli.use_case import MIRROR_DIFF_DIR, mirror_diff_command
from lib.settings import Settings


def test_mirror_diff_command_is_a_pasteable_multi_line_block() -> None:
    settings = Settings()
    lines = mirror_diff_command(settings, "uc_text_array").splitlines()
    assert lines == [
        f"cd {MIRROR_DIFF_DIR}",
        f"SOURCE_URL={settings.postgres_url} \\",
        f"MIRROR_URL={settings.xtdb_url} \\",
        "MIRROR_DATABASE=uc_text_array \\",
        "PUBLICATION_NAME=uc_text_array \\",
        "uv run mirror-diff",
    ]


def test_every_line_but_the_last_two_ends_with_a_continuation() -> None:
    lines = mirror_diff_command(Settings(), "uc_x").splitlines()
    assert all(line.endswith(" \\") for line in lines[1:-1])
    assert not lines[0].endswith("\\")
    assert not lines[-1].endswith("\\")
