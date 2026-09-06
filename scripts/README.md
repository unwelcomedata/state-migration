# Scripts — reproducing the published dataset

The published release (`export/state_migration_flows_v1.*`) is rebuildable from
raw sources with a single command.

## `reproduce.py` — raw → export

```bash
python scripts/reproduce.py
```

Runs the full state-level pipeline end to end, using the same logic the project
notebooks use (the reusable code lives in [`../src/`](../src)):

| Stage | What it does | Output |
|-------|--------------|--------|
| 1. Ingest | Ensures the raw IRS SOI state-to-state CSVs and Census ACS Excel files are in `data/raw/` (downloads any that are missing) | `data/raw/` |
| 2. Load | Loads the raw files into DuckDB (`stateoutflow{YYNN}` / `stateinflow{YYNN}`, `census_acs_migration`) | DuckDB raw tables |
| 3. Clean | Builds the directed-edge staging tables (`state_ref`, `irs_edges`, `acs_edges`, `nonmigrants`) | DuckDB staging tables |
| 4. Prepare | Merges IRS + ACS into `migration_flows`, adds the ACS reliability columns, and packages the export | `export/state_migration_flows_v1.*` + codebook |

The output CSV is byte-for-byte identical to the published dataset.

### Prerequisites

- Python 3.11+ with the packages in [`../requirements.txt`](../requirements.txt).
- Network access on the **first** run (to download raw files). Once `data/raw/`
  is populated, subsequent runs are fully offline.
- Source URLs, definitions, and methodology/series-break notes are in
  [`../SOURCES.md`](../SOURCES.md).

### Options

```bash
python scripts/reproduce.py --no-download           # fail (don't fetch) if raw files are missing
python scripts/reproduce.py --formats csv           # write only the CSV (+ codebook)
python scripts/reproduce.py --db /tmp/x.duckdb \
       --export-dir /tmp/exp                         # build into a scratch location (leaves the project DB/export untouched)
```

## Scope

This entrypoint reproduces the **state-level** release, which is what's published.
The county-to-county layer is ingested and validated but held for a later phase,
so it is intentionally not part of `reproduce.py`.
