#!/usr/bin/env python
"""Reproduce the state-migration published dataset from raw sources.

This is the serious-tier reproducibility entrypoint: a single command that goes
from the raw IRS SOI + Census ACS files in ``data/raw/`` all the way to the
published export in ``export/`` — the same ``state_migration_flows_v1`` CSV +
codebook that the release is built on. It runs the exact same ``src/`` logic the
notebooks use, in the documented pipeline order (ingest → clean → prepare).

What it does, in order:
  1. INGEST  — ensure the raw IRS state-to-state CSVs and Census ACS Excel files
               are present in ``data/raw/`` (downloads any that are missing).
  2. LOAD    — load the raw files into DuckDB as the raw tables
               (``stateoutflow{YYNN}`` / ``stateinflow{YYNN}`` and
               ``census_acs_migration``).
  3. CLEAN   — build the directed-edge staging tables in DuckDB
               (``state_ref``, ``irs_edges``, ``acs_edges``, ``nonmigrants``).
  4. PREPARE — merge IRS + ACS into ``migration_flows``, add the ACS reliability
               columns, and package the export (CSV + Excel + Parquet + codebook).

Scope: this reproduces the STATE-LEVEL release (what is published). The
county-to-county layer is ingested and validated but held for a later phase, so
it is intentionally not part of this entrypoint.

Usage:
    python scripts/reproduce.py                 # full run: raw → export
    python scripts/reproduce.py --no-download    # fail instead of fetching missing raw files
    python scripts/reproduce.py --db /tmp/x.duckdb --export-dir /tmp/exp   # dry run to a scratch location
    python scripts/reproduce.py --formats csv    # only write the CSV (+ codebook)

Prerequisites:
  - Python 3.11+ with the packages in ``requirements.txt``.
  - Network access on the first run (to download raw files). Subsequent runs are
    offline once ``data/raw/`` is populated.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

# --- make the project importable regardless of where this is invoked from ----
PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from src.ingest import (  # noqa: E402
    load_config,
    ingest_irs_soi_migration,
    ingest_census_acs_migration,
    parse_census_acs_migration,
)
from src.clean_quality import (  # noqa: E402
    get_connection,
    load_to_duckdb,
    run_sql,
    register_source,
)
from src.prepare import (  # noqa: E402
    build_state_ref,
    build_irs_edges,
    build_acs_edges,
    build_nonmigrants,
    build_migration_flows,
    package_dataset,
)

IRS_URL = "https://www.irs.gov/statistics/soi-tax-stats-migration-data"
ACS_URL = (
    "https://www.census.gov/data/tables/time-series/demo/geographic-mobility/"
    "state-to-state-migration.html"
)

# Export identity — matches the published release (03-prepare.ipynb).
EXPORT_NAME = "state_migration_flows_v1"

CODEBOOK = {
    "year": "Migration year = the later of the two years compared (IRS 2022–23 pair and ACS 2023 survey both map to 2023).",
    "origin_fips": "FIPS code of the origin (state people moved FROM). Non-state codes: 72=Puerto Rico, 57=Foreign Country; U.S. Island Areas uses sentinel US-ISL.",
    "origin_state": "Two-letter abbreviation of the origin.",
    "origin_state_name": "Full name of the origin.",
    "origin_type": "Origin location type: state, dc, territory (PR / U.S. Island Areas), or foreign.",
    "dest_fips": "FIPS code of the destination (state people moved TO). Same coding as origin_fips.",
    "dest_state": "Two-letter abbreviation of the destination.",
    "dest_state_name": "Full name of the destination.",
    "dest_type": "Destination location type: state, dc, territory, or foreign.",
    "irs_returns_out": "IRS: number of tax returns (~households) for this origin→dest move, as reported in the ORIGIN state outflow file. Raw counts (not thousands).",
    "irs_returns_in": "IRS: number of tax returns (~households) for this origin→dest move, as reported in the DESTINATION state inflow file. Usually equals irs_returns_out; differs slightly in later series.",
    "irs_individuals_out": "IRS: number of personal exemptions (~people) for this move, from the origin outflow file.",
    "irs_individuals_in": "IRS: number of personal exemptions (~people) for this move, from the destination inflow file.",
    "irs_agi_out": "IRS: total adjusted gross income for this move (in THOUSANDS of dollars), from the origin outflow file.",
    "irs_agi_in": "IRS: total adjusted gross income for this move (in THOUSANDS of dollars), from the destination inflow file.",
    "acs_migrants": "Census ACS: estimated number of people who made this origin→dest move (survey estimate).",
    "acs_moe": "Census ACS: margin of error (± people) on acs_migrants at 90% confidence.",
    "acs_moe_pct": "acs_moe as a fraction of acs_migrants. Higher = less reliable.",
    "acs_reliable": "True when acs_moe is less than 50% of acs_migrants (a usability cutoff for small survey flows).",
}

NOTES = """
Sources:
  - IRS Statistics of Income (SOI) State-to-State Migration Data — https://www.irs.gov/statistics/soi-tax-stats-migration-data (public domain)
  - U.S. Census Bureau, American Community Survey (ACS) State-to-State Migration Flows — https://www.census.gov/data/tables/time-series/demo/geographic-mobility/state-to-state-migration.html (public domain)

Grain: one row per origin x destination x year (directed edge). True state-to-state moves only;
IRS summary rows (FIPS 96/97/98), overseas (59), and non-migrant (stayed-put) rows are excluded
(non-migrants live in a separate nonmigrants table).

Coverage: IRS 2012–2023 (year = second year of the pair); ACS 2011–2019, 2021–2024 (no 2020, ACS 1-year
suspended for COVID). Rows carry nulls where only one source covers that year.

Caveats:
  - IRS counts tax filers, not total population; ACS counts all residents 1 year and older.
  - IRS AGI is in THOUSANDS of dollars.
  - ACS flows are survey estimates; use acs_reliable / acs_moe_pct before headlining small numbers.
  - 2022 ACS Connecticut data has a known processing error (corrected in 2023).
"""


def _rule(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


# ---------------------------------------------------------------------------
# 1. INGEST — ensure raw files exist
# ---------------------------------------------------------------------------

def step_ingest(cfg: dict, allow_download: bool) -> None:
    """Ensure the raw IRS + ACS state-level files are present in data/raw/."""
    raw_dir = Path(cfg["paths"]["data_raw"])
    have_irs = sorted(raw_dir.glob("state*flow*.csv"))
    have_acs = sorted(raw_dir.glob("census_acs_migration_*"))

    if have_irs and have_acs:
        print(f"Raw files present: {len(have_irs)} IRS CSVs, {len(have_acs)} ACS files.")
        return

    if not allow_download:
        raise SystemExit(
            "Missing raw files and --no-download was set. Populate data/raw/ from the "
            "URLs in SOURCES.md (IRS state{in,out}flow{YYNN}.csv, Census ACS "
            "state-to-state Excel), or re-run without --no-download."
        )

    print("Downloading missing raw files (polite rate limit applies)…")
    ingest_irs_soi_migration(cfg, skip_existing=True)
    ingest_census_acs_migration(cfg, skip_existing=True)


# ---------------------------------------------------------------------------
# 2. LOAD — raw files into DuckDB
# ---------------------------------------------------------------------------

def step_load_raw(cfg, con) -> None:
    """Load raw IRS CSVs and the parsed ACS long table into DuckDB."""
    raw_dir = Path(cfg["paths"]["data_raw"])

    # IRS state-to-state CSVs -> one table per file (stateoutflow{YYNN} etc.)
    irs_files = sorted(raw_dir.glob("state*flow*.csv"))
    if not irs_files:
        raise SystemExit("No IRS state*flow*.csv files found in data/raw/.")
    for csv_file in irs_files:
        table_name = csv_file.stem
        con.execute(f"DROP TABLE IF EXISTS {table_name}")
        con.execute(
            f"CREATE TABLE {table_name} AS "
            f"SELECT * FROM read_csv_auto('{csv_file.as_posix()}', header=true, all_varchar=false)"
        )
    print(f"Loaded {len(irs_files)} IRS raw tables.")

    # Census ACS -> single long-format table across all years
    source_cfg = cfg["sources"]["census_acs_migration"]
    frames = []
    for entry in source_cfg["years"]:
        year = entry["year"]
        ext = "xlsx" if entry["filename"].endswith(".xlsx") else "xls"
        filepath = raw_dir / f"census_acs_migration_{year}.{ext}"
        if not filepath.exists():
            print(f"  ⚠ missing ACS file (skip): {filepath.name}")
            continue
        frames.append(parse_census_acs_migration(filepath, year))
    if not frames:
        raise SystemExit("No Census ACS files found in data/raw/.")
    df_census = pd.concat(frames, ignore_index=True)
    con.execute("DROP TABLE IF EXISTS census_acs_migration")
    con.register("df_census", df_census)
    con.execute("CREATE TABLE census_acs_migration AS SELECT * FROM df_census")
    con.unregister("df_census")
    print(f"Loaded census_acs_migration: {len(df_census):,} rows.")


# ---------------------------------------------------------------------------
# 3. CLEAN — build directed-edge staging tables
# ---------------------------------------------------------------------------

def step_clean(con) -> None:
    """Build state_ref, irs_edges, acs_edges, nonmigrants staging tables."""
    ref = build_state_ref(con)  # creates the state_ref table itself
    print(f"state_ref: {len(ref)} locations")

    irs_edges = build_irs_edges(con)
    load_to_duckdb(irs_edges, "irs_edges", con)
    print(f"irs_edges: {len(irs_edges):,} rows")

    acs_edges = build_acs_edges(con)
    load_to_duckdb(acs_edges, "acs_edges", con)
    print(f"acs_edges: {len(acs_edges):,} rows")

    nonmigrants = build_nonmigrants(con)
    load_to_duckdb(nonmigrants, "nonmigrants", con)
    print(f"nonmigrants: {len(nonmigrants):,} rows")


# ---------------------------------------------------------------------------
# 4. PREPARE — merge + reliability columns + package export
# ---------------------------------------------------------------------------

def step_prepare(cfg, con, formats: list[str]) -> pd.DataFrame:
    """Merge IRS+ACS into migration_flows, add reliability columns, package export."""
    flows = build_migration_flows(con)
    load_to_duckdb(flows, "migration_flows", con)

    # Derived ACS reliability columns (same SQL as 03-prepare).
    load_to_duckdb(flows, "_flows_stage", con)
    flows = run_sql(
        """
        SELECT *,
            CASE WHEN acs_migrants IS NULL OR acs_migrants = 0 THEN NULL
                 ELSE ROUND(acs_moe * 1.0 / acs_migrants, 4) END AS acs_moe_pct,
            CASE WHEN acs_migrants IS NULL OR acs_migrants = 0 THEN NULL
                 ELSE (acs_moe * 1.0 / acs_migrants) < 0.50 END AS acs_reliable
        FROM _flows_stage
        """,
        con,
    )
    con.execute("DROP TABLE IF EXISTS _flows_stage")
    print(f"migration_flows: {len(flows):,} rows × {len(flows.columns)} cols")

    written = package_dataset(
        flows, cfg, name=EXPORT_NAME, codebook=CODEBOOK, notes=NOTES, formats=formats
    )

    # Record provenance for the export in _sources (idempotent; creates the
    # canonical _sources schema if this DB doesn't have one yet).
    register_source(
        con,
        EXPORT_NAME,
        name="IRS SOI + Census ACS (merged, derived)",
        url=IRS_URL,
        license="Public domain",
        notes=(
            "Published state-to-state migration export: IRS out/in + ACS measures side "
            "by side, one directed edge per origin x dest x year, with ACS reliability "
            f"flags. {int(len(flows)):,} rows."
        ),
        retrieved=date.today().isoformat(),
    )

    for kind, path in written.items():
        print(f"  {kind:9s} → {path}")
    return flows


def main() -> None:
    ap = argparse.ArgumentParser(description="Reproduce the state-migration published export from raw sources.")
    ap.add_argument("--no-download", action="store_true",
                    help="Do not fetch missing raw files; fail instead.")
    ap.add_argument("--db", default=None,
                    help="DuckDB file to build into (default: config duckdb_file).")
    ap.add_argument("--export-dir", default=None,
                    help="Directory to write the export into (default: config export path).")
    ap.add_argument("--formats", nargs="+", default=None,
                    help="Export formats to write (default: config export.formats).")
    args = ap.parse_args()

    cfg = load_config(str(PROJECT / "config.yaml"))
    if args.db:
        cfg["settings"]["duckdb_file"] = args.db
    if args.export_dir:
        cfg["paths"]["export"] = args.export_dir
    formats = args.formats or cfg.get("export", {}).get("formats", ["csv"])

    _rule("state-migration · reproduce  (raw → export)")
    print(f"DuckDB : {cfg['settings']['duckdb_file']}")
    print(f"Export : {cfg['paths']['export']}  (formats: {', '.join(formats)})")

    _rule("1/4  INGEST — ensure raw files present")
    step_ingest(cfg, allow_download=not args.no_download)

    con = get_connection(cfg)
    try:
        _rule("2/4  LOAD — raw files → DuckDB")
        step_load_raw(cfg, con)

        _rule("3/4  CLEAN — build staging tables")
        step_clean(con)

        _rule("4/4  PREPARE — merge + package export")
        flows = step_prepare(cfg, con, formats)
    finally:
        con.close()

    _rule("DONE")
    print(f"Reproduced {EXPORT_NAME}: {len(flows):,} rows → {cfg['paths']['export']}/")


if __name__ == "__main__":
    main()
