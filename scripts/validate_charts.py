#!/usr/bin/env python3
"""Pre-publish validation — re-check the chart data before anything goes public.

Re-derives the headline facts the published charts show, straight from the
migration_flows source table, and confirms the social/web chart sets stay in
parity.

Exit code 0 = safe to publish. Non-zero = do NOT publish.

Usage:
    .venv/bin/python scripts/validate_charts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb

PROJECT = Path(__file__).resolve().parent
while not (PROJECT / "config.yaml").exists() and PROJECT != PROJECT.parent:
    PROJECT = PROJECT.parent
sys.path.insert(0, str(PROJECT))
from src.ingest import load_config  # noqa: E402

failures: list[str] = []
checks: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        checks.append(f"  PASS  {name}")
    else:
        failures.append(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


NET_2023 = """
    WITH o AS (SELECT origin_state st, SUM(irs_individuals_out) gone FROM migration_flows
               WHERE year=2023 AND origin_type IN ('state','dc') GROUP BY 1),
         i AS (SELECT dest_state st, SUM(irs_individuals_in) came FROM migration_flows
               WHERE year=2023 AND dest_type IN ('state','dc') GROUP BY 1),
         net AS (SELECT COALESCE(i.st,o.st) st, COALESCE(came,0)-COALESCE(gone,0) net
                 FROM i FULL OUTER JOIN o ON i.st=o.st)
    SELECT sr.name AS state, n.net FROM net n JOIN state_ref sr ON sr.abbrev = n.st
    ORDER BY n.net {order} LIMIT 1
"""


def main() -> int:
    cfg = load_config("config.yaml")
    db = str(PROJECT / cfg["settings"]["duckdb_file"])
    con = duckdb.connect(db, read_only=True)

    # ── Headline facts: 2023 net-migration extremes (charts 1 & 5 framing) ─
    gainer = con.execute(NET_2023.format(order="DESC")).fetchone()
    loser = con.execute(NET_2023.format(order="ASC")).fetchone()
    check("2023 top net gainer is Florida", gainer[0] == "Florida", f"got {gainer[0]!r}")
    check("Florida net gain ~+113,945",
          abs(int(gainer[1]) - 113945) < 500, f"got {int(gainer[1]):,}")
    check("2023 top net loser is California", loser[0] == "California", f"got {loser[0]!r}")
    check("California net loss ~-209,197",
          abs(int(loser[1]) + 209197) < 500, f"got {int(loser[1]):,}")

    # ── Structural: net = arrivals - departures reconciles to a zero sum ───
    total_net = con.execute("""
        WITH o AS (SELECT origin_state st, SUM(irs_individuals_out) gone FROM migration_flows
                   WHERE year=2023 AND origin_type IN ('state','dc') GROUP BY 1),
             i AS (SELECT dest_state st, SUM(irs_individuals_in) came FROM migration_flows
                   WHERE year=2023 AND dest_type IN ('state','dc') GROUP BY 1)
        SELECT SUM(COALESCE(came,0)) - SUM(COALESCE(gone,0))
        FROM i FULL OUTER JOIN o ON i.st=o.st
    """).fetchone()[0]
    # Interstate net flows shouldn't sum to a huge number; allow slack for the
    # inflow/outflow file asymmetry, but it must be far smaller than any one state.
    check("interstate net flows roughly balance (|sum| < 50k)",
          abs(int(total_net)) < 50000, f"sum of net = {int(total_net):,}")

    con.close()

    # ── Social vs web chart parity (when rendered outputs are present) ────
    social = sorted((PROJECT / "outputs" / "social").glob("*.png"))
    web_dir = PROJECT / "outputs" / "web"
    if social and web_dir.exists():
        s_names = {p.name for p in social}
        w_names = {p.name for p in web_dir.glob("*.png")}
        check("social and web sets cover the same filenames", s_names == w_names,
              f"only social: {sorted(s_names - w_names)}; only web: {sorted(w_names - s_names)}")
        try:
            from PIL import Image
            dims = {Image.open(p).size for p in web_dir.glob("*.png")}
            check("every web chart is the web canvas 1664x936", dims == {(1664, 936)},
                  f"unexpected: {sorted(dims)}")
        except ImportError:
            pass

    print("Pre-publish chart-data validation — state-migration")
    print("=" * 60)
    for line in checks:
        print(line)
    for line in failures:
        print(line)
    print("=" * 60)
    if failures:
        print(f"RESULT: {len(failures)} FAILURE(S) — DO NOT PUBLISH.")
        return 1
    print(f"RESULT: all {len(checks)} checks passed — safe to publish.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
