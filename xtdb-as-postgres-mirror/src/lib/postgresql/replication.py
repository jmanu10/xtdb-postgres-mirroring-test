def drop_publication_statement(name: str) -> str:
    return f'DROP PUBLICATION IF EXISTS "{name}"'
