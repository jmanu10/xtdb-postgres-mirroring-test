# mirror-diff

mirror-diff compares a PostgreSQL database against the XTDB mirror built by logical replication and DirectMirror. It joins rows on `_id`, reporting rows missing from the mirror, rows the mirror still holds that the source doesn't, and columns that differ, down to paths inside JSON. It writes nothing to either database.

## Setup

```sh
uv sync
cp .env.example .env
```

`.env` names the two connections and the two names the comparison needs: `SOURCE_URL` and `MIRROR_URL` are the PostgreSQL and XTDB connection strings, `MIRROR_DATABASE` is the name given to `ATTACH DATABASE`, and `PUBLICATION_NAME` is the publication whose tables are compared. The defaults in `.env.example` point at the compose stack in `../xtdb-as-postgres-mirror`, which runs PostgreSQL on :6532 and XTDB on :6533, with the `text-array` use case attached; its `uv run mirror use-case run <name>` prints the exact `mirror-diff` invocation for the use case it just attached.

## Use

```sh
uv run mirror-diff                      # every table in the publication
uv run mirror-diff companies cohorts    # only the named tables
uv run mirror-diff --summary            # one line per table, column, and kind
uv run mirror-diff --save               # also write differences.md
uv run mirror-diff --output report.md   # or a file of your choosing
```

Each table gets one progress line showing its source row count, its number of differences, and the elapsed time. When anything differs, a table follows, listing the first fifty differences with a title naming the total. The exit code is 0 when nothing differs, 1 when something does, and 2 when the run could not compare.
