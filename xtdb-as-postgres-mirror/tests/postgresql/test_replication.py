from lib.postgresql.replication import drop_publication_statement


def test_drop_publication_statement_is_idempotent_and_quotes_the_name() -> None:
    assert drop_publication_statement("uc_x") == 'DROP PUBLICATION IF EXISTS "uc_x"'
