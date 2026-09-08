# XTDB as a Postgres mirror

Reproduction kit for XTDB's Postgres external source. Docker Compose runs PostgreSQL 18 (`wal_level=logical`) and XTDB 2.2 side by side; XTDB is attached to Postgres through logical replication with the `DirectMirror` indexer, and each use case under `use-cases/` seeds one small table whose rows either diverge between the two sides or stop the mirror from converging. Everything here is offline except the two containers.

## Setup

Requires Docker and [uv](https://docs.astral.sh/uv/). PostgreSQL listens on :6532, XTDB on :6533 (pgwire) and :6580 (healthz). Data lives in two docker volumes.

```sh
uv sync
cp .env.example .env
docker compose up -d
```

## Use cases

Each folder under `use-cases/` holds a `schema.sql` and a `rows.json`. A use case named `text-array` becomes the table, publication, replication slot, and attached database `uc_text_array`. Run one at a time.

```sh
uv run mirror use-case list                 # discovered cases,
uv run mirror use-case run text-array       # seed, publish, attach, poll the mirror
uv run mirror use-case drop text-array      # detach, drop slot/publication/table, wipe XTDB storage
```

`run` creates the table and publication in Postgres if they are missing, issues `ATTACH DATABASE` on XTDB if the database is not attached yet, then polls the mirror's row count until it matches the source or 120 s pass. A converged run exits 0 and prints the `mirror-diff` invocation that compares the two sides column by column (the diff tool lives in the sibling `../mirror-check-tool` project):

```sh
cd ../mirror-check-tool
SOURCE_URL=postgresql://postgres:postgres@localhost:6532/mirror \
MIRROR_URL=postgresql://xtdb@localhost:6533/xtdb \
MIRROR_DATABASE=uc_text_array \
PUBLICATION_NAME=uc_text_array \
uv run mirror-diff
```

A run that never converges exits 1; that is the expected outcome of a halting case. The reason is in the XTDB log, next to the use case's own `README.md`:

```sh
docker logs mirror-poc-xtdb
```

## The attach statement

This is exactly what the runner sends to XTDB over pgwire (`src/lib/xtdb/attach.py`), for a use case with SQL name `<db>`:

```sql
ATTACH DATABASE <db> WITH $$log: !Local
  path: '/var/lib/xtdb/<db>/log'
storage: !Local
  path: '/var/lib/xtdb/<db>/storage'

externalSource: !Postgres
  remote: mirror_pg
  publicationName: <db>
  slotName: <db>
  indexer: !DirectMirror {}
$$
```

- `<db>` is the use case's SQL name (`uc_` plus the folder name with dashes turned into underscores); the runner uses the same string for the attached database, the publication, and the replication slot.
- `mirror_pg` is the remote declared in `xtdb/config.yaml` (`remotes.mirror_pg`), which points XTDB at the `postgres` compose service using the `POSTGRES_*` variables from `.env`; `XTDB_REMOTE` in `.env` must match that name.
- The publication is created by the runner before the attach as `CREATE PUBLICATION "<db>" FOR TABLE "<db>" WITH (publish_generated_columns = 'stored')`; the slot is created by XTDB itself.

## Reset

`use-case drop` resets one case, including the XTDB storage under `/var/lib/xtdb/<db>` that a `DETACH` alone leaves behind. To reset everything:

```sh
docker compose down -v
docker compose up -d
```

## Tests

The suite is offline: nothing in it needs PostgreSQL or XTDB.

```sh
uv run pytest
uv run mypy
uv run black --check src tests
```
