"""DuckDB-backed cleaning and data quality utilities.

Workflow:
  1. Load raw DataFrame into DuckDB (in the project .duckdb file).
  2. Run cleaning operations as SQL — fast, inspectable, reproducible.
  3. Run quality checks and print a report before writing interim output.
  4. Save cleaned table as Parquet to data/interim/.

All functions accept and return pandas DataFrames so notebooks stay readable,
but the heavy lifting happens inside DuckDB.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


# ---------------------------------------------------------------------------
# Source provenance (_sources metadata table)
# ---------------------------------------------------------------------------

_SOURCES_SCHEMA = """
CREATE TABLE IF NOT EXISTS _sources (
    duckdb_table VARCHAR,
    source_name  VARCHAR,
    url          VARCHAR,
    license      VARCHAR,
    notes        VARCHAR,
    retrieved    VARCHAR
)
"""


def register_source(
    con: duckdb.DuckDBPyConnection,
    table: str,
    name: str,
    url: str = "",
    license: str = "",
    notes: str = "",
    retrieved: str = "",
) -> None:
    """Register a data source in the _sources metadata table.

    Call this after loading a new table into DuckDB to maintain full provenance.
    Replaces any existing entry for the same table name.

    Args:
        con:       Open DuckDB connection.
        table:     DuckDB table name this source populates.
        name:      Human-readable source name (e.g., "NHTSA FARS 2024").
        url:       Direct URL to the data file or page.
        license:   License string (e.g., "Public domain", "CC-BY 4.0").
        notes:     Any caveats, methodology notes, or field descriptions.
        retrieved: Date retrieved as ISO string (YYYY-MM-DD). Defaults to today.
    """
    from datetime import date as _date

    if not retrieved:
        retrieved = _date.today().isoformat()

    con.execute(_SOURCES_SCHEMA)
    con.execute("DELETE FROM _sources WHERE duckdb_table = ?", [table])
    con.execute(
        "INSERT INTO _sources VALUES (?, ?, ?, ?, ?, ?)",
        [table, name, url, license, notes, retrieved],
    )


def get_sources(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Return the full _sources provenance table as a DataFrame."""
    con.execute(_SOURCES_SCHEMA)
    return con.execute("SELECT * FROM _sources ORDER BY duckdb_table").df()


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def get_connection(cfg: dict[str, Any]) -> duckdb.DuckDBPyConnection:
    """Open (or create) the project DuckDB file and return a connection."""
    db_path = Path(cfg["settings"]["duckdb_file"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def load_to_duckdb(
    df: pd.DataFrame,
    table_name: str,
    con: duckdb.DuckDBPyConnection,
    replace: bool = True,
) -> None:
    """Register a DataFrame as a DuckDB table.

    Args:
        df:         Source DataFrame.
        table_name: Name for the table inside DuckDB.
        con:        Open DuckDB connection.
        replace:    Drop and recreate if the table already exists.
    """
    if replace:
        con.execute(f"DROP TABLE IF EXISTS {table_name}")
    # DuckDB can read a pandas DataFrame directly via the local variable name
    con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")


# ---------------------------------------------------------------------------
# Cleaning operations
# ---------------------------------------------------------------------------

def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase column names and replace spaces/hyphens with underscores."""
    df.columns = [
        c.strip().lower().replace(" ", "_").replace("-", "_") for c in df.columns
    ]
    return df


def clean_table(
    df: pd.DataFrame,
    table_name: str,
    con: duckdb.DuckDBPyConnection,
    drop_duplicate_subset: list[str] | None = None,
    strip_columns: list[str] | None = None,
    cast_map: dict[str, str] | None = None,
    where_filter: str | None = None,
) -> pd.DataFrame:
    """Run a cleaning pass on a DataFrame inside DuckDB and return the result.

    Args:
        df:                    Raw DataFrame to clean.
        table_name:            Staging table name in DuckDB.
        con:                   Open DuckDB connection.
        drop_duplicate_subset: Column(s) to use for deduplication (None = all cols).
        strip_columns:         String columns to TRIM whitespace from.
        cast_map:              Dict of {column: duckdb_type} to cast, e.g. {"year": "INTEGER"}.
        where_filter:          Optional SQL WHERE clause (no 'WHERE' keyword) to filter rows.

    Returns:
        Cleaned DataFrame.
    """
    load_to_duckdb(df, table_name, con)

    # Build SELECT list with optional casts and trims
    col_exprs = []
    for col in df.columns:
        expr = f'"{col}"'
        if cast_map and col in cast_map:
            expr = f"TRY_CAST({expr} AS {cast_map[col]}) AS \"{col}\""
        elif strip_columns and col in strip_columns:
            expr = f"TRIM({expr}) AS \"{col}\""
        else:
            expr = f"{expr}"
        col_exprs.append(expr)

    select_clause = ", ".join(col_exprs)
    query = f"SELECT {select_clause} FROM {table_name}"
    if where_filter:
        query += f" WHERE {where_filter}"

    cleaned = con.execute(query).df()

    # Deduplication via pandas (easier to express cross-DB)
    if drop_duplicate_subset is not None:
        cleaned = cleaned.drop_duplicates(subset=drop_duplicate_subset)
    else:
        cleaned = cleaned.drop_duplicates()

    return cleaned.reset_index(drop=True)


def run_sql(sql: str, con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Run arbitrary SQL against the open DuckDB connection and return a DataFrame.

    Useful for custom joins, aggregations, and feature engineering in notebooks.

    Example:
        run_sql("SELECT state, AVG(rate) as avg_rate FROM cleaned GROUP BY state", con)
    """
    return con.execute(sql).df()


# ---------------------------------------------------------------------------
# Quality checks
# ---------------------------------------------------------------------------

def quality_report(
    df: pd.DataFrame,
    table_name: str,
    con: duckdb.DuckDBPyConnection,
    required_columns: list[str] | None = None,
    max_null_pct: float = 0.10,
) -> dict[str, Any]:
    """Run quality checks and print a summary report.

    Checks:
      - Row count
      - Null percentage per column (warns if above max_null_pct)
      - Duplicate row count
      - Presence of required columns

    Returns a dict with check results (useful for notebook assertions).
    """
    load_to_duckdb(df, f"_qc_{table_name}", con, replace=True)

    row_count = con.execute(f"SELECT COUNT(*) FROM _qc_{table_name}").fetchone()[0]
    dup_count = row_count - con.execute(
        f"SELECT COUNT(*) FROM (SELECT DISTINCT * FROM _qc_{table_name})"
    ).fetchone()[0]

    null_pcts: dict[str, float] = {}
    warnings: list[str] = []
    for col in df.columns:
        nulls = con.execute(
            f'SELECT COUNT(*) FROM _qc_{table_name} WHERE "{col}" IS NULL'
        ).fetchone()[0]
        pct = nulls / row_count if row_count else 0.0
        null_pcts[col] = round(pct, 4)
        if pct > max_null_pct:
            warnings.append(f"  ⚠  '{col}' is {pct:.1%} null (threshold {max_null_pct:.0%})")

    missing_cols: list[str] = []
    if required_columns:
        missing_cols = [c for c in required_columns if c not in df.columns]
        if missing_cols:
            warnings.append(f"  ✗  Missing required columns: {missing_cols}")

    print(f"\n── Quality report: {table_name} ──────────────────")
    print(f"  Rows       : {row_count:,}")
    print(f"  Duplicates : {dup_count:,}")
    print(f"  Null %     :")
    for col, pct in null_pcts.items():
        flag = " ⚠" if pct > max_null_pct else ""
        print(f"    {col:<30} {pct:.1%}{flag}")
    if warnings:
        print("\n  Warnings:")
        for w in warnings:
            print(w)
    else:
        print("\n  ✓  No issues found.")
    print("─" * 50)

    return {
        "row_count": row_count,
        "duplicate_count": dup_count,
        "null_pcts": null_pcts,
        "missing_required_columns": missing_cols,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Save helpers
# ---------------------------------------------------------------------------

def save_interim(df: pd.DataFrame, cfg: dict[str, Any], filename: str) -> Path:
    """Save a cleaned DataFrame to data/interim/ as Parquet."""
    out = Path(cfg["paths"]["data_interim"]) / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False, engine=cfg["settings"]["parquet_engine"])
    print(f"Saved interim → {out}  ({len(df):,} rows)")
    return out


def save_processed(df: pd.DataFrame, cfg: dict[str, Any], filename: str) -> Path:
    """Save an analysis-ready DataFrame to data/processed/ as Parquet."""
    out = Path(cfg["paths"]["data_processed"]) / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False, engine=cfg["settings"]["parquet_engine"])
    print(f"Saved processed → {out}  ({len(df):,} rows)")
    return out
