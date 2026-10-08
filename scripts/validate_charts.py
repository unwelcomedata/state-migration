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

    # ── County charts (phase-2): headline facts from prepared tables ──────
    have = {r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables").fetchall()}
    if "chart_county_net" in have:
        # Chart 06: biggest county net loser is Los Angeles County (CA)
        c_loser = con.execute(
            "SELECT label, net_people FROM chart_county_net "
            "ORDER BY net_people ASC LIMIT 1").fetchone()
        check("county top net loser is Los Angeles County (CA)",
              c_loser[0] == "Los Angeles County (CA)", f"got {c_loser[0]!r}")
        check("LA County net ~-81,742",
              abs(int(c_loser[1]) + 81742) < 50, f"got {int(c_loser[1]):,}")
        c_gainer = con.execute(
            "SELECT label, net_people FROM chart_county_net "
            "ORDER BY net_people DESC LIMIT 1").fetchone()
        check("county top net gainer is Polk County (FL)",
              c_gainer[0] == "Polk County (FL)", f"got {c_gainer[0]!r}")
        check("Polk County net ~+19,407",
              abs(int(c_gainer[1]) - 19407) < 50, f"got {int(c_gainer[1]):,}")
        check("chart_county_net has 3143 county rows",
              con.execute("SELECT COUNT(*) FROM chart_county_net").fetchone()[0] == 3143)
    else:
        check("chart_county_net prepared table present", False,
              "run 03-prepare to build the county chart tables")

    if "chart_la_destinations" in have:
        # Chart 07 left panel: LA's top destination by people is San Bernardino
        la_ppl = con.execute(
            "SELECT dest_label, people FROM chart_la_destinations "
            "ORDER BY people DESC LIMIT 1").fetchone()
        check("LA top destination by people is San Bernardino County (CA)",
              la_ppl[0] == "San Bernardino County (CA)", f"got {la_ppl[0]!r}")
        check("LA->San Bernardino ~34,872",
              abs(int(la_ppl[1]) - 34872) < 20, f"got {int(la_ppl[1]):,}")
        # Chart 07 right panel: top AGI-per-person among >=500-mover destinations
        la_agi = con.execute(
            "SELECT dest_label, agi_per_person FROM chart_la_destinations "
            "WHERE people >= 500 ORDER BY agi_per_person DESC LIMIT 1").fetchone()
        check("LA top AGI/person dest (>=500 movers) is New York County (NY)",
              la_agi[0] == "New York County (NY)", f"got {la_agi[0]!r}")
        check("New York County AGI/person ~$186,987",
              abs(int(la_agi[1]) - 186987) < 100, f"got ${int(la_agi[1]):,}")
        # the >=500 floor must exclude tiny-sample resort counties
        resort = con.execute(
            "SELECT COUNT(*) FROM chart_la_destinations "
            "WHERE people >= 500 AND dest_label IN "
            "('Pitkin County (CO)','Teton County (WY)','Summit County (UT)',"
            "'Blaine County (ID)')").fetchone()[0]
        check("resort counties excluded by the >=500-mover floor", resort == 0,
              f"{resort} resort county(ies) still above the floor")
    else:
        check("chart_la_destinations prepared table present", False,
              "run 03-prepare to build the LA detail table")

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
