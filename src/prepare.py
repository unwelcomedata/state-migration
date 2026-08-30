"""Sellable dataset preparation and export utilities.

Takes a processed DataFrame and packages it for sale/distribution:
  - Drops any PII columns listed in config.yaml
  - Exports to CSV, Excel, and/or Parquet
  - Generates a plain-text codebook (column descriptions)

Usage in a notebook:
    from src.prepare import package_dataset
    package_dataset(df, cfg, name="my_dataset", codebook={"col": "description"})
"""

from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# PII stripping
# ---------------------------------------------------------------------------

def strip_pii(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Drop columns listed under export.strip_pii_columns in config.yaml."""
    cols_to_drop = cfg.get("export", {}).get("strip_pii_columns", [])
    if cols_to_drop:
        existing = [c for c in cols_to_drop if c in df.columns]
        if existing:
            df = df.drop(columns=existing)
            print(f"Stripped PII columns: {existing}")
    return df


# ---------------------------------------------------------------------------
# Codebook
# ---------------------------------------------------------------------------

def build_codebook(
    df: pd.DataFrame,
    descriptions: dict[str, str] | None = None,
    project_name: str = "",
    notes: str = "",
) -> str:
    """Generate a plain-text codebook for the dataset.

    Args:
        df:           The export-ready DataFrame.
        descriptions: Dict mapping column name → human-readable description.
                      Columns not in the dict get a placeholder.
        project_name: Printed in the header.
        notes:        Free-text notes appended at the bottom (source info, license, etc.).

    Returns:
        Codebook as a string (written to a .md file by package_dataset).
    """
    descriptions = descriptions or {}
    today = date.today().isoformat()

    lines = [
        f"# {project_name} — Dataset Codebook",
        f"Generated: {today}",
        "",
        "## Columns",
        "",
    ]

    for col in df.columns:
        dtype = str(df[col].dtype)
        desc = descriptions.get(col, "_No description provided._")
        non_null = df[col].notna().sum()
        total = len(df)
        lines.append(f"### `{col}`")
        lines.append(f"- **Type**: `{dtype}`")
        lines.append(f"- **Non-null**: {non_null:,} / {total:,} ({non_null/total:.1%})")
        lines.append(f"- **Description**: {desc}")
        lines.append("")

    if notes:
        lines += ["## Notes", "", textwrap.dedent(notes).strip(), ""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def package_dataset(
    df: pd.DataFrame,
    cfg: dict[str, Any],
    name: str,
    codebook: dict[str, str] | None = None,
    notes: str = "",
    formats: list[str] | None = None,
) -> dict[str, Path]:
    """Strip PII, export to configured formats, and write a codebook.

    Args:
        df:       Processed DataFrame ready for packaging.
        cfg:      Loaded config dict.
        name:     Base filename (no extension).
        codebook: Column description dict passed to build_codebook().
        notes:    Free-text appended to the codebook (source, license, etc.).
        formats:  Override config export.formats. Supported: csv, xlsx, parquet.

    Returns:
        Dict of {format: Path} for every file written.
    """
    df = strip_pii(df, cfg)

    export_dir = Path(cfg["paths"]["export"])
    export_dir.mkdir(parents=True, exist_ok=True)

    export_cfg = cfg.get("export", {})
    active_formats = formats or export_cfg.get("formats", ["csv"])
    include_codebook = export_cfg.get("include_codebook", True)
    project_name = cfg.get("project_name", name)

    written: dict[str, Path] = {}

    if "csv" in active_formats:
        p = export_dir / f"{name}.csv"
        df.to_csv(p, index=False, encoding=cfg["settings"]["encoding"])
        written["csv"] = p
        print(f"Exported CSV     → {p}")

    if "xlsx" in active_formats:
        p = export_dir / f"{name}.xlsx"
        with pd.ExcelWriter(p, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="data")
        written["xlsx"] = p
        print(f"Exported Excel   → {p}")

    if "parquet" in active_formats:
        p = export_dir / f"{name}.parquet"
        df.to_parquet(p, index=False, engine=cfg["settings"]["parquet_engine"])
        written["parquet"] = p
        print(f"Exported Parquet → {p}")

    if include_codebook:
        cb_text = build_codebook(df, descriptions=codebook, project_name=project_name, notes=notes)
        cb_path = export_dir / f"{name}_codebook.md"
        cb_path.write_text(cb_text, encoding="utf-8")
        written["codebook"] = cb_path
        print(f"Wrote codebook   → {cb_path}")

    print(f"\n✓  Package complete: {len(df):,} rows × {len(df.columns)} columns")
    return written


# ---------------------------------------------------------------------------
# Quick summary helpers (useful before packaging)
# ---------------------------------------------------------------------------

def value_counts_all(df: pd.DataFrame, top_n: int = 10) -> None:
    """Print top-N value counts for every column — quick sanity check."""
    for col in df.columns:
        print(f"\n── {col} ──")
        print(df[col].value_counts(dropna=False).head(top_n).to_string())


def numeric_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Return describe() output for numeric columns only, transposed for readability."""
    return df.select_dtypes("number").describe().T.round(2)


# ===========================================================================
# state-migration specific transforms
# ---------------------------------------------------------------------------
# Build a unified directed-edge migration table (one row per origin x
# destination x year) combining IRS SOI and Census ACS, plus a separate
# non-migrants table. All heavy lifting happens in DuckDB.
# ===========================================================================

import duckdb


# ---------------------------------------------------------------------------
# State reference / crosswalk
# ---------------------------------------------------------------------------
# Maps FIPS <-> 2-letter abbreviation <-> full name so the IRS (FIPS/abbrev)
# and ACS (full name) data can be joined. Includes the non-state locations
# that appear as valid origins/destinations, tagged by `loc_type`:
#   state      = one of the 50 states
#   dc         = District of Columbia
#   territory  = Puerto Rico, U.S. Island Areas
#   foreign    = moved from/to a foreign country
# IRS special summary FIPS (96/97/98) and overseas (59) are intentionally
# NOT in this crosswalk -- they are aggregates, not edges.

STATE_REF: list[tuple[str, str, str, str]] = [
    # (fips, abbrev, full_name, loc_type)
    ("01", "AL", "Alabama", "state"),
    ("02", "AK", "Alaska", "state"),
    ("04", "AZ", "Arizona", "state"),
    ("05", "AR", "Arkansas", "state"),
    ("06", "CA", "California", "state"),
    ("08", "CO", "Colorado", "state"),
    ("09", "CT", "Connecticut", "state"),
    ("10", "DE", "Delaware", "state"),
    ("11", "DC", "District of Columbia", "dc"),
    ("12", "FL", "Florida", "state"),
    ("13", "GA", "Georgia", "state"),
    ("15", "HI", "Hawaii", "state"),
    ("16", "ID", "Idaho", "state"),
    ("17", "IL", "Illinois", "state"),
    ("18", "IN", "Indiana", "state"),
    ("19", "IA", "Iowa", "state"),
    ("20", "KS", "Kansas", "state"),
    ("21", "KY", "Kentucky", "state"),
    ("22", "LA", "Louisiana", "state"),
    ("23", "ME", "Maine", "state"),
    ("24", "MD", "Maryland", "state"),
    ("25", "MA", "Massachusetts", "state"),
    ("26", "MI", "Michigan", "state"),
    ("27", "MN", "Minnesota", "state"),
    ("28", "MS", "Mississippi", "state"),
    ("29", "MO", "Missouri", "state"),
    ("30", "MT", "Montana", "state"),
    ("31", "NE", "Nebraska", "state"),
    ("32", "NV", "Nevada", "state"),
    ("33", "NH", "New Hampshire", "state"),
    ("34", "NJ", "New Jersey", "state"),
    ("35", "NM", "New Mexico", "state"),
    ("36", "NY", "New York", "state"),
    ("37", "NC", "North Carolina", "state"),
    ("38", "ND", "North Dakota", "state"),
    ("39", "OH", "Ohio", "state"),
    ("40", "OK", "Oklahoma", "state"),
    ("41", "OR", "Oregon", "state"),
    ("42", "PA", "Pennsylvania", "state"),
    ("44", "RI", "Rhode Island", "state"),
    ("45", "SC", "South Carolina", "state"),
    ("46", "SD", "South Dakota", "state"),
    ("47", "TN", "Tennessee", "state"),
    ("48", "TX", "Texas", "state"),
    ("49", "UT", "Utah", "state"),
    ("50", "VT", "Vermont", "state"),
    ("51", "VA", "Virginia", "state"),
    ("53", "WA", "Washington", "state"),
    ("54", "WV", "West Virginia", "state"),
    ("55", "WI", "Wisconsin", "state"),
    ("56", "WY", "Wyoming", "state"),
    # non-state locations that are valid migration endpoints
    ("72", "PR", "Puerto Rico", "territory"),
    # U.S. Island Areas: no single FIPS in this dataset; use "US-ISL" sentinel
    ("US-ISL", "ISL", "U.S. Island Areas", "territory"),
    # Foreign country: IRS uses FIPS 57 in inflow files; ACS uses a label
    ("57", "FOR", "Foreign Country", "foreign"),
]


def build_state_ref(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Create/replace the `state_ref` crosswalk table in DuckDB and return it.

    Provides fips <-> abbrev <-> full name <-> loc_type so IRS (FIPS/abbrev)
    and ACS (full name) can be joined on a common key.
    """
    ref = pd.DataFrame(STATE_REF, columns=["fips", "abbrev", "name", "loc_type"])
    con.execute("DROP TABLE IF EXISTS state_ref")
    con.execute("CREATE TABLE state_ref AS SELECT * FROM ref")
    return ref


# ---------------------------------------------------------------------------
# ACS label normalization
# ---------------------------------------------------------------------------
# ACS origin/destination labels have casing/plural inconsistencies and an
# origin-only "United States" aggregate. Normalize to match state_ref.name.
_ACS_LABEL_FIXES = """
    CASE TRIM(%(col)s)
        WHEN 'Foreign country'   THEN 'Foreign Country'
        WHEN 'U.S. Island Area'  THEN 'U.S. Island Areas'
        ELSE TRIM(%(col)s)
    END
"""


def _acs_norm(col: str) -> str:
    """Return a SQL expression that normalizes an ACS location label column."""
    return _ACS_LABEL_FIXES % {"col": col}


# ---------------------------------------------------------------------------
# IRS -> directed edges
# ---------------------------------------------------------------------------

# IRS raw table year-pair codes (YYNN) -> aligned survey year (second year).
IRS_YEAR_PAIRS: dict[str, int] = {
    "1112": 2012, "1213": 2013, "1314": 2014, "1415": 2015,
    "1516": 2016, "1617": 2017, "1718": 2018, "1819": 2019,
    "1920": 2020, "2021": 2021, "2122": 2022, "2223": 2023,
}


def build_irs_edges(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Union all IRS inflow/outflow year tables into one directed-edge table.

    Returns one row per (origin_fips, dest_fips, year) with both the outflow-
    file and inflow-file measurements side by side:
        irs_returns_out/_in, irs_individuals_out/_in, irs_agi_out/_in

    Only TRUE edges are kept: rows where both endpoints resolve to a real
    location in state_ref. Summary rows (FIPS 96/97/98), overseas (59) and
    Non-migrant rows (origin_fips == dest_fips) are excluded here -- the
    Non-migrant rows are handled separately by build_nonmigrants().
    """
    outflow_parts = []
    inflow_parts = []
    for code, yr in IRS_YEAR_PAIRS.items():
        # NULLIF(x, -1): the IRS uses -1 as a disclosure-suppression flag for
        # small cells. Treat it as NULL (suppressed), not a literal count.
        outflow_parts.append(
            f"""SELECT y1_statefips AS origin_fips, y2_statefips AS dest_fips,
                       {yr} AS year,
                       NULLIF(n1, -1) AS returns,
                       NULLIF(n2, -1) AS individuals,
                       NULLIF(AGI, -1) AS agi
                FROM stateoutflow{code}"""
        )
        inflow_parts.append(
            f"""SELECT y1_statefips AS origin_fips, y2_statefips AS dest_fips,
                       {yr} AS year,
                       NULLIF(n1, -1) AS returns,
                       NULLIF(n2, -1) AS individuals,
                       NULLIF(AGI, -1) AS agi
                FROM stateinflow{code}"""
        )

    outflow_union = "\nUNION ALL\n".join(outflow_parts)
    inflow_union = "\nUNION ALL\n".join(inflow_parts)

    sql = f"""
    WITH outflow AS ({outflow_union}),
         inflow  AS ({inflow_union}),
         -- keep only rows whose endpoints are real locations (drop 96/97/98/59
         -- summaries) and drop self-edges (Non-migrant rows)
         out_edges AS (
             SELECT o.origin_fips, o.dest_fips, o.year,
                    o.returns AS irs_returns_out,
                    o.individuals AS irs_individuals_out,
                    o.agi AS irs_agi_out
             FROM outflow o
             WHERE o.origin_fips IN (SELECT fips FROM state_ref)
               AND o.dest_fips   IN (SELECT fips FROM state_ref)
               AND o.origin_fips <> o.dest_fips
         ),
         in_edges AS (
             SELECT i.origin_fips, i.dest_fips, i.year,
                    i.returns AS irs_returns_in,
                    i.individuals AS irs_individuals_in,
                    i.agi AS irs_agi_in
             FROM inflow i
             WHERE i.origin_fips IN (SELECT fips FROM state_ref)
               AND i.dest_fips   IN (SELECT fips FROM state_ref)
               AND i.origin_fips <> i.dest_fips
         )
    SELECT
        COALESCE(o.origin_fips, i.origin_fips) AS origin_fips,
        COALESCE(o.dest_fips,   i.dest_fips)   AS dest_fips,
        COALESCE(o.year,        i.year)        AS year,
        o.irs_returns_out, o.irs_individuals_out, o.irs_agi_out,
        i.irs_returns_in,  i.irs_individuals_in,  i.irs_agi_in
    FROM out_edges o
    FULL OUTER JOIN in_edges i
      ON o.origin_fips = i.origin_fips
     AND o.dest_fips   = i.dest_fips
     AND o.year        = i.year
    """
    return con.execute(sql).df()


# ---------------------------------------------------------------------------
# ACS -> directed edges
# ---------------------------------------------------------------------------

def build_acs_edges(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Normalize the ACS long table into directed edges keyed by FIPS.

    Drops the two aggregate 'Total' rows per origin/year, normalizes label
    quirks, drops the origin-only 'United States' aggregate, and resolves both
    endpoints to state_ref FIPS. Returns one row per (origin_fips, dest_fips,
    year) with acs_migrants and acs_moe.
    """
    sql = f"""
    WITH norm AS (
        SELECT
            {_acs_norm('origin')}      AS origin_name,
            {_acs_norm('destination')} AS dest_name,
            migrants AS acs_migrants,
            moe      AS acs_moe,
            year
        FROM census_acs_migration
        WHERE TRIM(destination) <> 'Total'
          AND TRIM(origin)      <> 'United States'
    )
    SELECT
        so.fips AS origin_fips,
        sd.fips AS dest_fips,
        n.year,
        n.acs_migrants,
        n.acs_moe
    FROM norm n
    JOIN state_ref so ON so.name = n.origin_name
    JOIN state_ref sd ON sd.name = n.dest_name
    """
    return con.execute(sql).df()


# ---------------------------------------------------------------------------
# Merge IRS + ACS into the unified migration_flows edge table
# ---------------------------------------------------------------------------

def build_migration_flows(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Full-outer-join IRS and ACS directed edges into one table.

    Produces one row per (origin, dest, year) with resolved names/abbrevs,
    location types, IRS measures (out/in) and ACS measures side by side.
    Requires state_ref, plus the irs_edges and acs_edges staging tables to
    exist in DuckDB (created by build_irs_edges / build_acs_edges and loaded
    via load_to_duckdb).
    """
    sql = """
    SELECT
        e.year,
        e.origin_fips,
        so.abbrev   AS origin_state,
        so.name     AS origin_state_name,
        so.loc_type AS origin_type,
        e.dest_fips,
        sd.abbrev   AS dest_state,
        sd.name     AS dest_state_name,
        sd.loc_type AS dest_type,
        -- IRS measures
        e.irs_returns_out, e.irs_returns_in,
        e.irs_individuals_out, e.irs_individuals_in,
        e.irs_agi_out, e.irs_agi_in,
        -- ACS measures
        e.acs_migrants, e.acs_moe
    FROM (
        SELECT
            COALESCE(irs.origin_fips, acs.origin_fips) AS origin_fips,
            COALESCE(irs.dest_fips,   acs.dest_fips)   AS dest_fips,
            COALESCE(irs.year,        acs.year)        AS year,
            irs.irs_returns_out, irs.irs_returns_in,
            irs.irs_individuals_out, irs.irs_individuals_in,
            irs.irs_agi_out, irs.irs_agi_in,
            acs.acs_migrants, acs.acs_moe
        FROM irs_edges irs
        FULL OUTER JOIN acs_edges acs
          ON irs.origin_fips = acs.origin_fips
         AND irs.dest_fips   = acs.dest_fips
         AND irs.year        = acs.year
    ) e
    JOIN state_ref so ON so.fips = e.origin_fips
    JOIN state_ref sd ON sd.fips = e.dest_fips
    ORDER BY e.year, so.abbrev, sd.abbrev
    """
    return con.execute(sql).df()


# ---------------------------------------------------------------------------
# Non-migrants (people who stayed in the same state)
# ---------------------------------------------------------------------------

def build_nonmigrants(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Extract IRS Non-migrant rows into a per-state x year table.

    IRS marks non-migrants with origin_fips == dest_fips (both equal the
    state's own FIPS). These are identical in the inflow and outflow files,
    so we read them from the outflow files. One row per state x year, keyed
    to state_ref for a future join to a master states table.
    """
    parts = []
    for code, yr in IRS_YEAR_PAIRS.items():
        parts.append(
            f"""SELECT y1_statefips AS fips, {yr} AS year,
                       NULLIF(n1, -1) AS nonmig_returns,
                       NULLIF(n2, -1) AS nonmig_individuals,
                       NULLIF(AGI, -1) AS nonmig_agi
                FROM stateoutflow{code}
                WHERE y1_statefips = y2_statefips"""
        )
    union = "\nUNION ALL\n".join(parts)
    sql = f"""
    WITH nm AS ({union})
    SELECT
        nm.year,
        nm.fips,
        sr.abbrev AS state,
        sr.name   AS state_name,
        nm.nonmig_returns,
        nm.nonmig_individuals,
        nm.nonmig_agi
    FROM nm
    JOIN state_ref sr ON sr.fips = nm.fips
    ORDER BY nm.year, sr.abbrev
    """
    return con.execute(sql).df()


# ===========================================================================
# County-to-county migration transforms
# ---------------------------------------------------------------------------
# Build a directed county-edge table combining outflow- and inflow-file
# measurements, a per-county income proxy (AGI per return from the county's
# non-migrant row), a national-median income-class flag, and county
# non-migrants. All heavy lifting in DuckDB.
# ===========================================================================


def _fips5(state_col: str, county_col: str) -> str:
    """SQL expression building a zero-padded 5-digit county GEOID from parts."""
    return (
        f"LPAD(CAST({state_col} AS VARCHAR), 2, '0') || "
        f"LPAD(CAST({county_col} AS VARCHAR), 3, '0')"
    )


def build_county_edges(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Collapse the long raw county frame into directed county edges.

    Expects a `county_raw` table in DuckDB (the parsed long frame with columns
    origin_state_fips, origin_county_fips, dest_state_fips, dest_county_fips,
    name, n1, n2, agi, year, direction).

    Keeps only TRUE county-to-county edges:
      - both endpoints are real counties (state_fips 1-56, county_fips > 0)
      - drops self-edges (non-migrants -> handled by build_county_nonmigrants)
      - drops summary rows (dest_state 96/97/98) and non-county aggregates
        (dest_state 57/58/59)

    Outflow and inflow measurements for the same directed edge are placed
    side by side (irs_*_out / irs_*_in), matching the state-level design.
    """
    o = _fips5("origin_state_fips", "origin_county_fips")
    d = _fips5("dest_state_fips", "dest_county_fips")
    sql = f"""
    WITH base AS (
        SELECT
            {o} AS origin_fips,
            {d} AS dest_fips,
            year, direction,
            -- IRS -1 = disclosure-suppression flag -> treat as NULL
            NULLIF(n1, -1) AS n1,
            NULLIF(n2, -1) AS n2,
            NULLIF(agi, -1) AS agi
        FROM county_raw
        WHERE origin_state_fips BETWEEN 1 AND 56
          AND dest_state_fips   BETWEEN 1 AND 56
          AND origin_county_fips > 0
          AND dest_county_fips   > 0
          AND NOT (origin_state_fips = dest_state_fips
                   AND origin_county_fips = dest_county_fips)   -- drop non-migrant self-edges
    ),
    out_e AS (
        SELECT origin_fips, dest_fips, year,
               n1 AS irs_returns_out, n2 AS irs_individuals_out, agi AS irs_agi_out
        FROM base WHERE direction = 'outflow'
    ),
    in_e AS (
        SELECT origin_fips, dest_fips, year,
               n1 AS irs_returns_in, n2 AS irs_individuals_in, agi AS irs_agi_in
        FROM base WHERE direction = 'inflow'
    )
    SELECT
        COALESCE(o.origin_fips, i.origin_fips) AS origin_fips,
        COALESCE(o.dest_fips,   i.dest_fips)   AS dest_fips,
        COALESCE(o.year,        i.year)        AS year,
        o.irs_returns_out, o.irs_individuals_out, o.irs_agi_out,
        i.irs_returns_in,  i.irs_individuals_in,  i.irs_agi_in
    FROM out_e o
    FULL OUTER JOIN in_e i
      ON o.origin_fips = i.origin_fips AND o.dest_fips = i.dest_fips AND o.year = i.year
    """
    return con.execute(sql).df()


def build_county_nonmigrants(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Extract county non-migrant rows and compute an income proxy per county.

    Non-migrant rows have origin == dest (same 5-digit county). They represent
    the county's resident tax base, so AGI-per-return is a stable county income
    proxy. Deduplicated per (fips, year) because the row appears in both the
    outflow and inflow sheets.

    Returns one row per county x year with:
        fips, name, year, nonmig_returns, nonmig_individuals, nonmig_agi,
        agi_per_return  (dollars = agi*1000 / returns)
    """
    f = _fips5("origin_state_fips", "origin_county_fips")
    sql = f"""
    WITH nm AS (
        SELECT
            {f} AS fips,
            year,
            -- strip the ' Non-migrants' suffix for a clean county name
            REGEXP_REPLACE(name, ' Non-migrants$', '') AS name,
            NULLIF(n1, -1) AS nonmig_returns,
            NULLIF(n2, -1) AS nonmig_individuals,
            NULLIF(agi, -1) AS nonmig_agi,
            ROW_NUMBER() OVER (PARTITION BY {f}, year ORDER BY n1 DESC) AS rn
        FROM county_raw
        WHERE origin_state_fips BETWEEN 1 AND 56
          AND origin_county_fips > 0
          AND origin_state_fips = dest_state_fips
          AND origin_county_fips = dest_county_fips
    )
    SELECT fips, name, year, nonmig_returns, nonmig_individuals, nonmig_agi,
           ROUND(nonmig_agi * 1000.0 / NULLIF(nonmig_returns, 0), 0) AS agi_per_return
    FROM nm
    WHERE rn = 1
    ORDER BY year, fips
    """
    return con.execute(sql).df()


def build_county_income_class(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Flag each county above/below the national median AGI-per-return, per year.

    Expects `county_nonmigrants` in DuckDB. The median is computed across all
    counties within each year (equal weight per county, not per return).

    Returns: fips, name, year, agi_per_return, national_median, income_class
    where income_class is 'above_median' or 'below_median'.
    """
    sql = """
    WITH med AS (
        SELECT year, MEDIAN(agi_per_return) AS national_median
        FROM county_nonmigrants
        WHERE agi_per_return IS NOT NULL
        GROUP BY year
    )
    SELECT
        c.fips, c.name, c.year, c.agi_per_return,
        m.national_median,
        CASE WHEN c.agi_per_return >= m.national_median
             THEN 'above_median' ELSE 'below_median' END AS income_class
    FROM county_nonmigrants c
    JOIN med m USING (year)
    ORDER BY c.year, c.fips
    """
    return con.execute(sql).df()


def build_county_migration_flows(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Join county edges to income-class tags on both endpoints.

    Expects `county_edges` and `county_income_class` in DuckDB. Produces the
    final analysis table: one row per origin county x dest county x year, with
    each endpoint's name, AGI-per-return, and above/below-median class, plus a
    `flow_class` combining the two (e.g. 'above_to_below').
    """
    sql = """
    SELECT
        e.year,
        e.origin_fips,
        o.name            AS origin_name,
        o.agi_per_return  AS origin_agi_per_return,
        o.income_class    AS origin_income_class,
        e.dest_fips,
        d.name            AS dest_name,
        d.agi_per_return  AS dest_agi_per_return,
        d.income_class    AS dest_income_class,
        CASE
            WHEN o.income_class = 'above_median' AND d.income_class = 'above_median' THEN 'above_to_above'
            WHEN o.income_class = 'above_median' AND d.income_class = 'below_median' THEN 'above_to_below'
            WHEN o.income_class = 'below_median' AND d.income_class = 'above_median' THEN 'below_to_above'
            WHEN o.income_class = 'below_median' AND d.income_class = 'below_median' THEN 'below_to_below'
        END AS flow_class,
        e.irs_returns_out, e.irs_returns_in,
        e.irs_individuals_out, e.irs_individuals_in,
        e.irs_agi_out, e.irs_agi_in
    FROM county_edges e
    LEFT JOIN county_income_class o ON o.fips = e.origin_fips AND o.year = e.year
    LEFT JOIN county_income_class d ON d.fips = e.dest_fips   AND d.year = e.year
    ORDER BY e.year, e.origin_fips, e.dest_fips
    """
    return con.execute(sql).df()
