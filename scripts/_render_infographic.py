"""Build the state-migration infographic (tall + social SVG -> PNG) and validate every
data mark back to DuckDB + the published export.

Every bar, segment and big number is COMPUTED from data/project.duckdb (opened READ-ONLY
and closed). The tall and social renders are fed identical queried values; only the
canvas mapping (px per unit) differs. Each mark carries data-* attributes so validate()
parses it back out of the SVG, inverts the mapping, and compares with a FRESH query and
with the export parquet files.

Usage (from project root):  .venv/bin/python scripts/_render_infographic.py
Writes docs/infographic_state_migration{,_social}.{svg,png}
       artifacts/INFOGRAPHIC-VALIDATION.md  (gitignored)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import duckdb

PROJECT = Path(__file__).resolve().parents[1]
DOCS, ART = PROJECT / "docs", PROJECT / "artifacts"
DOCS.mkdir(exist_ok=True)
ART.mkdir(exist_ok=True)
DB = str(PROJECT / "data" / "project.duckdb")
EXPORT = PROJECT / "export"

NAVY, TEAL, AQUA, VANILLA, GREY, BG = "#003049", "#005F73", "#94D2BD", "#E9D8A6", "#6B7280", "#FBF8F0"
RED, GOLD, INK = "#AE2012", "#EE9B00", "#1F2937"   # RED = the project's chart loss colour

# ───────────────────────── SQL (same definitions as 06-viz-social) ─────────────────────────
NET_CTE = """
WITH o AS (SELECT origin_state st, SUM(irs_individuals_out) gone, SUM(irs_agi_out) ao FROM migration_flows
           WHERE year=2023 AND origin_type IN ('state','dc') GROUP BY 1),
     i AS (SELECT dest_state st, SUM(irs_individuals_in) came, SUM(irs_agi_in) ai FROM migration_flows
           WHERE year=2023 AND dest_type IN ('state','dc') GROUP BY 1),
     net AS (SELECT COALESCE(i.st,o.st) st,
                    CAST(COALESCE(came,0)-COALESCE(gone,0) AS BIGINT) net_people,
                    (COALESCE(ai,0)-COALESCE(ao,0))/1e6 net_agi_b,
                    (COALESCE(ai,0)-COALESCE(ao,0))*1000.0 net_agi
             FROM i FULL OUTER JOIN o ON i.st=o.st)
"""
PAIRS_CTE = """
WITH s AS (SELECT origin_state a, dest_state b, irs_individuals_out n FROM migration_flows
           WHERE year=2023 AND origin_type IN ('state','dc') AND dest_type IN ('state','dc')
             AND irs_individuals_out IS NOT NULL),
paired AS (SELECT f.a, f.b, f.n a_to_b, COALESCE(r.n,0) b_to_a FROM s f
           LEFT JOIN s r ON r.a=f.b AND r.b=f.a WHERE f.a<f.b),
pr AS (SELECT CASE WHEN a_to_b>=b_to_a THEN a ELSE b END loser,
              CASE WHEN a_to_b>=b_to_a THEN b ELSE a END winner,
              CAST(GREATEST(a_to_b,b_to_a) AS BIGINT) big,
              CAST(LEAST(a_to_b,b_to_a) AS BIGINT) small,
              CAST(ABS(a_to_b-b_to_a) AS BIGINT) net_flow,
              CAST(a_to_b+b_to_a AS BIGINT) gross FROM paired)
"""


def load() -> dict:
    con = duckdb.connect(DB, read_only=True)
    try:
        q = lambda s: con.execute(s).fetchall()
        names = dict(q("SELECT abbrev, name FROM state_ref"))
        d: dict = {"names": names}
        d["net_people"] = q(NET_CTE + "SELECT st, CAST(net_people AS BIGINT) FROM net ORDER BY net_people DESC, st")
        d["net_agi"] = q(NET_CTE + "SELECT st, CAST(net_agi_b AS DOUBLE) FROM net ORDER BY net_agi_b DESC, st")
        d["net_all"] = q(NET_CTE + "SELECT st, CAST(net_people AS BIGINT), CAST(net_agi AS DOUBLE) FROM net")
        d["pairs_top"] = q(PAIRS_CTE + "SELECT loser, winner, big, small, net_flow, gross FROM pr ORDER BY net_flow DESC, loser LIMIT 10")
        d["pairs_stats"] = q(PAIRS_CTE + "SELECT COUNT(*), CAST(MEDIAN(net_flow*1.0/gross) AS DOUBLE), CAST(SUM(net_flow)*1.0/SUM(gross) AS DOUBLE), CAST(SUM(gross) AS BIGINT), CAST(SUM(net_flow) AS BIGINT) FROM pr")[0]
        d["county_top"] = q("SELECT label, net_people FROM chart_county_net WHERE net_people IS NOT NULL ORDER BY net_people DESC, label LIMIT 5")
        d["county_bot"] = q("SELECT label, net_people FROM chart_county_net WHERE net_people IS NOT NULL ORDER BY net_people ASC, label LIMIT 5")
        d["la_people"] = q("SELECT dest_label, people FROM chart_la_destinations WHERE people IS NOT NULL ORDER BY people DESC, dest_label LIMIT 10")
        d["la_agi"] = q("SELECT dest_label, agi_per_person, people FROM chart_la_destinations WHERE people>=500 AND agi_per_person IS NOT NULL ORDER BY agi_per_person DESC, dest_label LIMIT 10")
    finally:
        con.close()
    return d


def derive(d: dict) -> dict:
    """Rows ready for drawing + facts used in text. Everything numeric comes from d."""
    nm = d["names"]
    npl = d["net_people"]
    people = [(s, nm[s], v) for s, v in npl[:5]] + [(s, nm[s], v) for s, v in npl[-5:]]
    na = d["net_agi"]
    agi = [(s, nm[s], v) for s, v in na[:5]] + [(s, nm[s], v) for s, v in na[-5:]]
    per = []
    for s, p, a in d["net_all"]:
        if abs(p) >= 20000:
            per.append((s, nm[s], (abs(a) / abs(p)) * (1 if p > 0 else -1) / 1000.0))
    per.sort(key=lambda r: (-r[2], r[0]))
    F = dict(
        people=people, agi=agi, per=per,
        net_sum=sum(v for _, v in npl), n_jur=len(npl),
        pairs=d["pairs_top"], n_pairs=d["pairs_stats"][0], med_share=d["pairs_stats"][1],
        agg_share=d["pairs_stats"][2], gross_all=d["pairs_stats"][3], net_all_pairs=d["pairs_stats"][4],
        county=list(d["county_top"]) + list(d["county_bot"]),
        la_people=d["la_people"], la_agi=d["la_agi"],
    )
    F["fl_per"] = next(v for s, _, v in per if s == "FL")
    F["ma_per"] = next(v for s, _, v in per if s == "MA")
    F["per_min"] = per[-1]
    return F


# ───────────────────────── svg helpers ─────────────────────────
def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def f1(x): return f"{x:.1f}"
def f2(x): return f"{x:.2f}"


def t(x, y, s, size, fill, weight="", anchor=""):
    w = f' font-weight="{weight}"' if weight else ""
    a = f' text-anchor="{anchor}"' if anchor else ""
    return f'<text x="{f1(x)}" y="{f1(y)}" fill="{fill}" font-size="{size}"{w}{a}>{esc(s)}</text>'


def sgn(v, fmt):
    return ("+" if v >= 0 else "\u2212") + fmt(abs(v))


def people_fmt(v): return f"{v:,.0f}"
def b_fmt(v): return f"${v:.1f}B"
def k_fmt(v): return f"${v:,.0f}k"
def usd_fmt(v): return f"${v:,.0f}"


REG: dict = {}   # REG[(canvas, chart)] = dict(kind, zero/x0, k)


def lw(s, fs):  # rough text width estimate (bold)
    return len(s) * 0.6 * fs + 12


def diverge(canvas, cid, rows, xL, xR, y0, pitch, bh, fs, fmt, name_fs=None):
    """Diverging bars from a common zero. rows = (key, name, value). Labels outside bar ends,
    names on the empty side of the zero line. k = px per unit is recorded for validation."""
    name_fs = name_fs or fs
    vals = [v for _, _, v in rows]
    vmin, vmax = min(0, min(vals)), max(0, max(vals))
    lab_l = max([lw(sgn(v, fmt), fs) for v in vals if v < 0] or [0])
    lab_r = max([lw(sgn(v, fmt), fs) for v in vals if v > 0] or [0])
    k = (xR - xL - lab_l - lab_r) / (vmax - vmin)
    zero = xL + lab_l + (-vmin) * k
    REG[(canvas, cid)] = dict(kind="div", zero=zero, k=k)
    out = [f'<line x1="{f1(zero)}" y1="{f1(y0)}" x2="{f1(zero)}" y2="{f1(y0 + len(rows) * pitch)}" stroke="{GREY}" stroke-width="1.5"/>']
    for i, (key, name, v) in enumerate(rows):
        y = y0 + i * pitch
        by = y + (pitch - bh) / 2
        base = y + pitch / 2 + fs * 0.35
        w = abs(v) * k
        col = TEAL if v >= 0 else RED
        x = zero if v >= 0 else zero - w
        out.append(f'<rect class="bar" data-c="{cid}" data-k="{esc(key)}" data-s="{1 if v >= 0 else -1}" '
                   f'x="{f2(x)}" y="{f1(by)}" width="{f2(w)}" height="{f1(bh)}" fill="{col}"/>'
                   f'<!-- {key} {v:,.3f} -> {w:.2f}px -->')
        if v >= 0:
            out.append(t(zero + w + 8, base, sgn(v, fmt), fs, col, "bold"))
            out.append(t(zero - 10, y + pitch / 2 + name_fs * 0.35, name, name_fs, INK, anchor="end"))
        else:
            out.append(t(zero - w - 8, base, sgn(v, fmt), fs, col, "bold", "end"))
            out.append(t(zero + 10, y + pitch / 2 + name_fs * 0.35, name, name_fs, INK))
    return "\n  ".join(out)


def hbars(canvas, cid, rows, x_name, x0, x1, y0, pitch, bh, fs, fmt, color):
    """Horizontal bars from x0. rows = (key, name, value)."""
    vmax = max(v for _, _, v in rows)
    lab = max(lw(fmt(v), fs) for _, _, v in rows)
    k = (x1 - x0 - lab) / vmax
    REG[(canvas, cid)] = dict(kind="h", zero=x0, k=k)
    out = []
    for i, (key, name, v) in enumerate(rows):
        y = y0 + i * pitch
        w = v * k
        out.append(f'<rect class="bar" data-c="{cid}" data-k="{esc(key)}" data-s="1" x="{f2(x0)}" y="{f1(y + (pitch - bh) / 2)}" '
                   f'width="{f2(w)}" height="{f1(bh)}" fill="{color}"/><!-- {key} {v:,.3f} -> {w:.2f}px -->')
        out.append(t(x_name, y + pitch / 2 + fs * 0.35, name, fs, INK, anchor="end"))
        out.append(t(x0 + w + 8, y + pitch / 2 + fs * 0.35, fmt(v), fs, color, "bold"))
    return "\n  ".join(out)


def tug(canvas, cid, pairs, nm, x_name, x0, x1, y0, pitch, bh, fs, net_fs, chip_w):
    """Gross two-way movement per state pair: teal = larger direction, gold = the flow back.
    The gap between the two segments' lengths is the net."""
    gmax = max(p[5] for p in pairs)
    k = (x1 - x0 - chip_w) / gmax
    REG[(canvas, cid)] = dict(kind="tug", zero=x0, k=k)
    out = []
    for i, (lo, wi, big, small, net, gross) in enumerate(pairs):
        y = y0 + i * pitch
        by = y + (pitch - bh) / 2
        wa, wb = big * k, small * k
        key = f"{lo}-{wi}"
        out.append(f'<rect class="tga" data-c="{cid}" data-k="{key}" x="{f2(x0)}" y="{f1(by)}" width="{f2(wa)}" height="{f1(bh)}" fill="{TEAL}"/>'
                   f'<rect class="tgb" data-c="{cid}" data-k="{key}" x="{f2(x0 + wa)}" y="{f1(by)}" width="{f2(wb)}" height="{f1(bh)}" fill="{GOLD}"/>'
                   f'<!-- {key} larger {big:,} -> {wa:.2f}px; back {small:,} -> {wb:.2f}px; net {net:,}; gross {gross:,} -->')
        out.append(t(x_name, y + pitch / 2 + fs * 0.35, f"{nm[lo]} \u2192 {nm[wi]}", fs, INK, anchor="end"))
        out.append(t(x0 + wa + wb + 10, y + pitch / 2 + net_fs * 0.1 - 2, f"net {net:,}", net_fs, NAVY, "bold"))
        out.append(t(x0 + wa + wb + 10, y + pitch / 2 + net_fs * 0.1 + net_fs * 0.95 - 2, f"{net / gross:.0%} of {gross:,}", net_fs - 3, GREY))
    return "\n  ".join(out)


# ───────────────────────── TALL ─────────────────────────
def build_tall(d, F):
    nm = d["names"]
    W = 1200
    parts: list[str] = []
    y = 372

    def head(title, sub):
        nonlocal y
        parts.append(t(80, y, title, 34, NAVY, "bold"))
        parts.append(t(80, y + 34, sub, 22, GREY))
        y += 34

    def divider():
        nonlocal y
        parts.append(f'<line x1="80" y1="{y}" x2="1120" y2="{y}" stroke="{VANILLA}" stroke-width="3"/>')
        y += 72

    pp = F["people"]
    # S1 — net people
    head("Net migration by state, 2023", "Arrivals minus departures. The 5 states with the largest net gain and the 5 with the largest net loss.")
    y += 96
    parts.append(t(80, y, sgn(pp[0][2], people_fmt), 80, TEAL, "bold"))
    parts.append(t(80, y + 32, f"{pp[0][1]}, net gain", 22, GREY))
    parts.append(t(1120, y, sgn(pp[-1][2], people_fmt), 80, RED, "bold", "end"))
    parts.append(t(1120, y + 32, f"{pp[-1][1]}, net loss", 22, GREY, anchor="end"))
    y += 70
    parts.append(diverge("tall", "S1", pp, 80, 1120, y, 38, 26, 21, people_fmt))
    y += 10 * 38 + 36
    parts.append(t(80, y, f"Net totals across all 50 states and DC sum to {sgn(F['net_sum'], people_fmt)}, not zero (see how to read this, below).", 20, GREY))
    y += 40
    divider()

    # S2 — net AGI
    ag = F["agi"]
    head("Net adjusted gross income moved by migration, 2023", "Income arriving minus income leaving with movers, in billions of dollars. Top 5 and bottom 5 states.")
    y += 96
    parts.append(t(80, y, sgn(ag[0][2], b_fmt), 80, TEAL, "bold"))
    parts.append(t(80, y + 32, f"{ag[0][1]}, net AGI gain", 22, GREY))
    parts.append(t(1120, y, sgn(ag[-1][2], b_fmt), 80, RED, "bold", "end"))
    parts.append(t(1120, y + 32, f"{ag[-1][1]}, net AGI loss", 22, GREY, anchor="end"))
    y += 70
    parts.append(diverge("tall", "S2", ag, 80, 1120, y, 38, 26, 21, b_fmt))
    y += 10 * 38 + 36
    parts.append(t(80, y, "AGI is income at the origin, in origin-year dollars (IRS reports it in thousands).", 20, GREY))
    y += 40
    divider()

    # S3 — per migrant
    pm = F["per"]
    head("AGI per net migrant, 2023", f"Net AGI per net person, in thousands of dollars. States with net migration of 20,000+ either way ({len(pm)}).")
    y += 96
    parts.append(t(80, y, k_fmt(F["fl_per"]), 80, TEAL, "bold"))
    parts.append(t(80, y + 32, "per net newcomer, Florida", 22, GREY))
    parts.append(t(1120, y, k_fmt(abs(F["ma_per"])), 80, RED, "bold", "end"))
    parts.append(t(1120, y + 32, "per net departure, Massachusetts", 22, GREY, anchor="end"))
    y += 70
    parts.append(diverge("tall", "S3", pm, 80, 1120, y, 36, 24, 20, k_fmt))
    y += len(pm) * 36 + 36
    parts.append(t(80, y, "Right of the line: income arriving per net newcomer. Left: income leaving per net departure.", 20, GREY))
    y += 40
    divider()

    # S4 — net vs gross
    pr = F["pairs"][:6]
    head("Net vs gross movement between state pairs, 2023", "Each bar is total movement between two states. Teal: larger direction. Gold: the flow back.")
    y += 96
    parts.append(t(80, y, f"{F['med_share']:.0%}", 80, NAVY, "bold"))
    parts.append(t(80, y + 32, "median state pair: net as a share of gross", 22, GREY))
    parts.append(t(80, y + 58, f"({F['n_pairs']:,} pairs with data)", 22, GREY))
    parts.append(t(1120, y, f"{F['agg_share']:.0%}", 80, TEAL, "bold", "end"))
    parts.append(t(1120, y + 32, "all pairs combined:", 22, GREY, anchor="end"))
    parts.append(t(1120, y + 58, f"{F['net_all_pairs']:,} net of {F['gross_all']:,}", 22, GREY, anchor="end"))
    y += 96
    parts.append(tug("tall", "S4", pr, nm, 300, 320, 1120, y, 66, 34, 21, 21, 190))
    y += len(pr) * 66 + 24
    parts.append(t(80, y, "Largest net pairs, by net flow. Pair flows use the outflow-file count in each direction.", 20, GREY))
    y += 40
    divider()

    # S5 — county net
    cn = F["county"]
    head("Net county migration, 2023", "Net people between counties: the 5 counties with the largest gain and the 5 with the largest loss.")
    y += 96
    parts.append(t(80, y, sgn(cn[0][1], people_fmt), 80, TEAL, "bold"))
    parts.append(t(80, y + 32, f"{cn[0][0]}, net gain", 22, GREY))
    parts.append(t(1120, y, sgn(cn[-5][1], people_fmt), 80, RED, "bold", "end"))
    parts.append(t(1120, y + 32, f"{cn[-5][0]}, net loss", 22, GREY, anchor="end"))
    y += 70
    parts.append(diverge("tall", "S5", [(lb, lb, v) for lb, v in cn], 80, 1120, y, 38, 26, 21, people_fmt))
    y += 10 * 38 + 36
    parts.append(t(80, y, "Identified county-to-county flows only; the IRS suppresses small flows, so counties undercount.", 20, GREY))
    y += 40
    divider()

    # S6 — LA
    lp, la = F["la_people"], F["la_agi"]
    head("Where Los Angeles County\u2019s movers went, 2023", "Top 10 destination counties, ranked two ways.")
    y += 100
    parts.append(t(80, y, f"{lp[0][1]:,.0f}", 80, TEAL, "bold"))
    parts.append(t(80, y + 32, f"people to {lp[0][0]}", 22, GREY))
    parts.append(t(1120, y, usd_fmt(la[0][1]), 80, RED, "bold", "end"))
    parts.append(t(1120, y + 32, f"AGI per person to {la[0][0]}", 22, GREY, anchor="end"))
    y += 74
    parts.append(t(80, y, "By number of people", 24, NAVY, "bold"))
    y += 14
    parts.append(hbars("tall", "S6a", [(lb, lb, v) for lb, v in lp], 400, 420, 1120, y, 34, 22, 20, people_fmt, TEAL))
    y += 10 * 34 + 44
    parts.append(t(80, y, "By AGI per person (destinations with at least 500 movers)", 24, NAVY, "bold"))
    y += 14
    parts.append(hbars("tall", "S6b", [(lb, lb, v) for lb, v, _ in la], 400, 420, 1120, y, 34, 22, 20, usd_fmt, RED))
    y += 10 * 34 + 36
    parts.append(t(80, y, "The 500-mover floor excludes small-sample destinations.", 20, GREY))
    y += 40
    divider()

    # How to read
    parts.append(t(80, y, "How to read this", 30, NAVY, "bold"))
    notes = [
        "Net = arrivals counted in the IRS inflow file minus departures counted in the outflow file.",
        "This mixed method does not reconcile to zero across states.",
        "The IRS counts tax filers and their dependents, not the whole population. AGI is income at the origin, in origin-year dollars.",
        "All figures are 2023 (the IRS 2022\u201323 filing-year pair), a single year that does not cross an IRS series break.",
    ]
    for i, n in enumerate(notes):
        parts.append(t(80, y + 38 + i * 30, n, 19, GREY))
    y += 38 + len(notes) * 30 + 30
    H = y + 90
    body = "\n  ".join(parts)
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<!--
  @unwelcomedata - PROJECT INFOGRAPHIC (tall portrait poster). Project: state-migration.
  Generated by scripts/_render_infographic.py; every mark computed from data/project.duckdb
  (migration_flows, state_ref, chart_county_net, chart_la_destinations). Canvas 1200 x {H}.
-->
<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Helvetica, Arial, sans-serif">
  <rect width="{W}" height="{H}" fill="{BG}"/>
  <rect x="0" y="0" width="{W}" height="300" fill="{NAVY}"/>
  {t(80, 126, "State-to-State Migration", 72, "#FFFFFF", "bold")}
  {t(80, 190, "Who moved in 2023, and the income that went with them", 34, AQUA, "bold")}
  {t(80, 242, "IRS tax-return data: net totals, income, and the two-way flows underneath.", 24, VANILLA)}
  {body}
  <rect x="0" y="{H - 90}" width="{W}" height="90" fill="{NAVY}"/>
  {t(80, H - 45, "@unwelcomedata", 24, "#FFFFFF", "bold")}
  {t(80, H - 15, "IRS Statistics of Income migration data, 2022\u201323 filing years \u00b7 tax filers and dependents \u00b7 AGI in origin-year dollars", 18, AQUA)}
</svg>
'''
    return svg, H


# ───────────────────────── SOCIAL ─────────────────────────
def build_social(d, F):
    nm = d["names"]
    W, H = 1600, 900
    pp, ag, pr = F["people"], F["agi"], F["pairs"][:5]
    lp, la = F["la_people"][:5], F["la_agi"][:5]
    parts: list[str] = []
    LX0, LX1, RX0, RX1 = 80, 760, 840, 1520
    parts.append(f'<line x1="800" y1="204" x2="800" y2="808" stroke="{VANILLA}" stroke-width="3"/>')
    # top-left: net people
    parts.append(t(LX0, 240, "Net migration by state, 2023", 26, NAVY, "bold"))
    parts.append(t(LX0, 264, f"Arrivals minus departures: {pp[0][1]} {sgn(pp[0][2], people_fmt)}, {pp[-1][1]} {sgn(pp[-1][2], people_fmt)}.", 17, GREY))
    parts.append(diverge("social", "S1", pp, LX0, LX1, 276, 22.5, 16, 15, people_fmt))
    parts.append(f'<line x1="{LX0}" y1="520" x2="{LX1}" y2="520" stroke="{VANILLA}" stroke-width="3"/>')
    # top-right: net AGI
    parts.append(t(RX0, 240, "Net AGI moved by migration, 2023", 26, NAVY, "bold"))
    parts.append(t(RX0, 264, f"Billions of dollars. {ag[0][1]}: {k_fmt(F['fl_per'])} of AGI per net newcomer.", 17, GREY))
    parts.append(diverge("social", "S2", ag, RX0, RX1, 276, 22.5, 16, 15, b_fmt))
    parts.append(f'<line x1="{RX0}" y1="520" x2="{RX1}" y2="520" stroke="{VANILLA}" stroke-width="3"/>')
    # bottom-left: net vs gross
    parts.append(t(LX0, 550, "Net vs gross movement between state pairs", 26, NAVY, "bold"))
    parts.append(t(LX0, 574, f"Median pair: net is {F['med_share']:.0%} of gross. Teal = larger direction, gold = flow back.", 17, GREY))
    parts.append(tug("social", "S4", pr, nm, 262, 275, LX1, 586, 40, 22, 16, 16, 150))
    # bottom-right: LA
    parts.append(t(RX0, 550, "Where Los Angeles County\u2019s movers went", 26, NAVY, "bold"))
    parts.append(t(RX0, 574, "Top 5 destination counties, ranked two ways, 2023.", 17, GREY))
    parts.append(t(RX0, 594, "By number of people", 16, NAVY, "bold"))
    parts.append(hbars("social", "S6a", [(lb, lb, v) for lb, v in lp], 1090, 1105, RX1, 599, 19, 13, 15, people_fmt, TEAL))
    parts.append(t(RX0, 714, "By AGI per person (at least 500 movers)", 16, NAVY, "bold"))
    parts.append(hbars("social", "S6b", [(lb, lb, v) for lb, v, _ in la], 1090, 1105, RX1, 720, 19, 13, 15, usd_fmt, RED))
    body = "\n  ".join(parts)
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<!--
  @unwelcomedata - PROJECT INFOGRAPHIC (landscape social render). Project: state-migration.
  1600x900 feed render; same FRAME, two columns; generated by scripts/_render_infographic.py
  from the SAME queried values as the tall poster.
-->
<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Helvetica, Arial, sans-serif">
  <rect width="{W}" height="{H}" fill="{BG}"/>
  <rect x="0" y="0" width="{W}" height="180" fill="{NAVY}"/>
  {t(80, 86, "State-to-State Migration", 56, "#FFFFFF", "bold")}
  {t(80, 132, "Who moved in 2023, and the income that went with them", 30, AQUA, "bold")}
  {t(80, 164, "IRS tax-return data: net totals, income, and the two-way flows underneath.", 20, VANILLA)}
  {body}
  <rect x="0" y="{H - 70}" width="{W}" height="70" fill="{NAVY}"/>
  {t(80, H - 36, "@unwelcomedata", 22, "#FFFFFF", "bold")}
  {t(80, H - 13, "IRS SOI 2023 \u00b7 net = inflow-file arrivals minus outflow-file departures (does not sum to zero) \u00b7 tax filers + dependents, not total population \u00b7 AGI in origin-year dollars", 15, AQUA)}
</svg>
'''
    return svg, H


# ───────────────────────── validation ─────────────────────────
def parse_bars(svg, cid):
    pat = (r'<rect class="bar" data-c="%s" data-k="([^"]+)" data-s="(-?1)" x="([\d.]+)" y="[\d.]+" width="([\d.]+)"' % cid)
    return [(m[0], int(m[1]), float(m[2]), float(m[3])) for m in re.findall(pat, svg)]


def parse_tug(svg, cid):
    a = {m[0]: (float(m[1]), float(m[2])) for m in re.findall(r'class="tga" data-c="%s" data-k="([^"]+)" x="([\d.]+)" y="[\d.]+" width="([\d.]+)"' % cid, svg)}
    b = {m[0]: (float(m[1]), float(m[2])) for m in re.findall(r'class="tgb" data-c="%s" data-k="([^"]+)" x="([\d.]+)" y="[\d.]+" width="([\d.]+)"' % cid, svg)}
    return a, b


def validate(d, F, tall, social):
    lines, ok = [], True

    def chk(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        lines.append(f"- {'PASS' if cond else 'FAIL'} \u2014 {name}" + (f" ({detail})" if detail else ""))

    # fresh, independent read of the source + the published export parquet
    fresh = load()
    F2 = derive(fresh)
    chk("fresh DuckDB re-query reproduces every drawn series (people, AGI, per-migrant, pairs, county, LA)",
        all(F[k] == F2[k] for k in ("people", "agi", "per", "pairs", "county", "la_people", "la_agi")))

    ex = duckdb.connect(":memory:")
    sp = str(EXPORT / "state_migration_flows_v1.parquet")
    cp = str(EXPORT / "county_migration_flows_v1.parquet")
    ex_net = dict((s, (p, a)) for s, p, a in ex.execute(f"""
        WITH o AS (SELECT origin_state st, SUM(irs_individuals_out) g, SUM(irs_agi_out) a FROM read_parquet('{sp}')
                   WHERE year=2023 AND origin_type IN ('state','dc') GROUP BY 1),
             i AS (SELECT dest_state st, SUM(irs_individuals_in) g, SUM(irs_agi_in) a FROM read_parquet('{sp}')
                   WHERE year=2023 AND dest_type IN ('state','dc') GROUP BY 1)
        SELECT COALESCE(i.st,o.st), CAST(COALESCE(i.g,0)-COALESCE(o.g,0) AS BIGINT), CAST((COALESCE(i.a,0)-COALESCE(o.a,0))*1000.0 AS DOUBLE)
        FROM i FULL OUTER JOIN o ON i.st=o.st""").fetchall())
    db_net = {s: (p, a) for s, p, a in d["net_all"]}
    chk("export parquet: state net people + net AGI (51 jurisdictions) equal DuckDB exactly",
        len(ex_net) == len(db_net) == 51 and all(int(ex_net[s][0]) == int(db_net[s][0]) and abs(ex_net[s][1] - db_net[s][1]) < 1 for s in db_net))
    ex_pairs = ex.execute(f"""
        WITH s AS (SELECT origin_state a, dest_state b, irs_individuals_out n FROM read_parquet('{sp}')
                   WHERE year=2023 AND origin_type IN ('state','dc') AND dest_type IN ('state','dc') AND irs_individuals_out IS NOT NULL),
        paired AS (SELECT f.n x, COALESCE(r.n,0) y FROM s f LEFT JOIN s r ON r.a=f.b AND r.b=f.a WHERE f.a<f.b)
        SELECT COUNT(*), CAST(MEDIAN(ABS(x-y)*1.0/(x+y)) AS DOUBLE), CAST(SUM(ABS(x-y))*1.0/SUM(x+y) AS DOUBLE), CAST(SUM(x+y) AS BIGINT), CAST(SUM(ABS(x-y)) AS BIGINT) FROM paired""").fetchone()
    chk("export parquet: pair stats (count, median share, aggregate share, gross, net) equal DuckDB",
        ex_pairs[0] == F["n_pairs"] and abs(ex_pairs[1] - F["med_share"]) < 1e-9 and abs(ex_pairs[2] - F["agg_share"]) < 1e-9
        and ex_pairs[3] == F["gross_all"] and ex_pairs[4] == F["net_all_pairs"])
    ex_cty = {r[0]: r[1] for r in ex.execute(f"""
        WITH i AS (SELECT dest_fips f, SUM(irs_individuals_in) v FROM read_parquet('{cp}') WHERE year=2023 GROUP BY 1),
             o AS (SELECT origin_fips f, SUM(irs_individuals_out) v FROM read_parquet('{cp}') WHERE year=2023 GROUP BY 1)
        SELECT COALESCE(i.f,o.f), CAST(COALESCE(i.v,0)-COALESCE(o.v,0) AS DOUBLE) FROM i FULL OUTER JOIN o ON i.f=o.f""").fetchall()}
    con = duckdb.connect(DB, read_only=True)
    fips = {lb: fp for fp, lb in con.execute("SELECT fips, label FROM chart_county_net").fetchall()}
    con.close()
    chk("export parquet: all 10 charted county nets equal the export-derived nets",
        all(abs(ex_cty[fips[lb]] - v) < 0.5 for lb, v in F["county"]),
        "; ".join(f"{lb} {ex_cty[fips[lb]]:+,.0f}" for lb, _ in F["county"][:1] + F["county"][-5:-4]))
    ex_la = {r[0]: (r[1], r[2]) for r in ex.execute(f"""
        SELECT dest_fips, CAST(SUM(irs_individuals_out) AS DOUBLE), CAST(SUM(irs_agi_out) AS DOUBLE) FROM read_parquet('{cp}')
        WHERE year=2023 AND origin_fips='06037' GROUP BY 1""").fetchall()}
    la_ok = all(abs(ex_la[fips[lb]][0] - v) < 0.5 for lb, v in F["la_people"]) and \
        all(abs(ex_la[fips[lb]][1] * 1000.0 / ex_la[fips[lb]][0] - v) < 0.5 and ex_la[fips[lb]][0] == pe for lb, v, pe in F["la_agi"])
    chk("export parquet: all 20 LA destination values (people; AGI per person = AGI x1000 / people) equal the export-derived values",
        la_ok, f"San Bernardino {ex_la[fips['San Bernardino County (CA)']][0]:,.0f}; NY County ${ex_la[fips['New York County (NY)']][1]*1000.0/ex_la[fips['New York County (NY)']][0]:,.0f}")

    # mark-level checks
    for canvas, svg in (("tall", tall), ("social", social)):
        for cid, rows in (("S1", F["people"]), ("S2", F["agi"]), ("S3", F["per"]), ("S5", [(lb, lb, v) for lb, v in F["county"]])):
            if canvas == "social" and cid in ("S3", "S5"):
                continue
            reg = REG[(canvas, cid)]
            bars = parse_bars(svg, cid)
            want = {k: v for k, _, v in rows}
            ratios = [(w / abs(want[k])) for k, s, x, w in bars if abs(want[k]) > 0]
            prop = max(ratios) - min(ratios)
            vals = {k: s * w / reg["k"] for k, s, x, w in bars}
            err = max(abs(vals[k] - want[k]) / max(abs(want[k]), 1e-9) for k in want)
            edge = max(abs((x if s > 0 else x + w) - reg["zero"]) for k, s, x, w in bars)
            chk(f"{canvas} {cid}: {len(bars)} bars match DB values (max rel err {err:.4%}); px/unit constant (spread {prop:.2e}); common zero edge (max {edge:.2f}px)",
                len(bars) == len(want) and err < 0.003 and prop < reg["k"] * 0.003 and edge < 0.05)
            order_ok = [k for k, *_ in bars] == [k for k, _, _ in rows]
            chk(f"{canvas} {cid}: bar order = descending value order", order_ok)
        for cid, rows in (("S6a", [(lb, lb, v) for lb, v in F["la_people"]]), ("S6b", [(lb, lb, v) for lb, v, _ in F["la_agi"]])):
            n = 10 if canvas == "tall" else 5
            rows = rows[:n]
            reg = REG[(canvas, cid)]
            bars = parse_bars(svg, cid)
            want = {k: v for k, _, v in rows}
            err = max(abs(w / reg["k"] - want[k]) / want[k] for k, s, x, w in bars)
            chk(f"{canvas} {cid}: {len(bars)} bars match DB values (max rel err {err:.4%}); common baseline",
                len(bars) == n and err < 0.003 and all(abs(x - reg["zero"]) < 0.05 for _, _, x, _ in bars))
        n = 6 if canvas == "tall" else 5
        a, b = parse_tug(svg, "S4")
        reg = REG[(canvas, "S4")]
        errs = []
        for lo, wi, big, small, net, gross in F["pairs"][:n]:
            key = f"{lo}-{wi}"
            errs.append(abs(a[key][1] / reg["k"] - big) / big)
            errs.append(abs(b[key][1] / reg["k"] - small) / small)
            assert abs(b[key][0] - (a[key][0] + a[key][1])) < 0.05 and abs(a[key][0] - reg["zero"]) < 0.05
        chk(f"{canvas} S4: {len(a)} pair bars (larger + return segments) match DB, segments contiguous from one baseline (max rel err {max(errs):.4%})",
            len(a) == len(b) == n and max(errs) < 0.003)

    # text claims
    pp = dict((s, v) for s, _, v in F["people"])
    chk("text: FL +113,945 and CA \u2212209,197 (matches scripts/validate_charts.py facts)", pp["FL"] == 113945 and pp["CA"] == -209197)
    chk("text: top-5 gainers FL, TX, NC, SC, TN; top-5 losers (smallest to largest loss) MA, NJ, IL, NY, CA",
        [s for s, _, _ in F["people"]] == ["FL", "TX", "NC", "SC", "TN", "MA", "NJ", "IL", "NY", "CA"], str([s for s, _, _ in F["people"]]))
    chk(f"text: state nets sum to {F['net_sum']:,} over {F['n_jur']} jurisdictions (non-zero, as the caveat says)", F["n_jur"] == 51 and F["net_sum"] == -28113)
    ag = dict((s, v) for s, _, v in F["agi"])
    chk("text: FL +$20.6B and CA \u2212$12.9B net AGI", round(ag["FL"], 1) == 20.6 and round(ag["CA"], 1) == -12.9, f"{ag['FL']:.3f} / {ag['CA']:.3f}")
    chk("text: FL per net newcomer $181k; MA per net departure $137k (largest departure value among the 13)",
        round(F["fl_per"]) == 181 and round(F["ma_per"]) == -137 and F["per_min"][0] == "MA", f"{F['fl_per']:.1f} / {F['ma_per']:.1f}")
    chk("text: 13 states clear the 20,000 net-migration floor; FL is the top per-migrant value", len(F["per"]) == 13 and F["per"][0][0] == "FL")
    chk("text: median pair 9% (9.06%), all pairs combined 14% (14.20%), 1,273 pairs",
        f"{F['med_share']:.0%}" == "9%" and f"{F['agg_share']:.0%}" == "14%" and F["n_pairs"] == 1273, f"{F['med_share']:.4f} / {F['agg_share']:.4f}")
    p0 = F["pairs"][0]
    chk("text: largest net pair is California\u2192Texas, net 41,249 (README fact)", (p0[0], p0[1], p0[4]) == ("CA", "TX", 41249))
    chk("text: every charted pair's larger direction exceeds its return (larger = teal)", all(p[2] >= p[3] for p in F["pairs"]))
    chk("text: county extremes \u2014 Polk County (FL) +19,407 and Los Angeles County (CA) \u221281,742", F["county"][0] == ("Polk County (FL)", 19407.0) and F["county"][-5] == ("Los Angeles County (CA)", -81742.0))
    chk("text: LA top destination by people is San Bernardino County (CA), 34,872", F["la_people"][0] == ("San Bernardino County (CA)", 34872.0))
    chk("text: LA top AGI/person (\u2265500 movers) is New York County (NY), $186,987; floor holds for all 10", F["la_agi"][0][0] == "New York County (NY)" and round(F["la_agi"][0][1]) == 186987 and all(p >= 500 for _, _, p in F["la_agi"]))
    for s in ("+113,945", "\u2212209,197", "+$20.6B", "\u2212$12.9B", "$181k", "$137k", "34,872", "$186,987", "+19,407", "\u221281,742"):
        chk(f"text present in tall render: {s}", s in tall)
    for s in ("+113,945", "\u2212209,197", "$181k", "34,872", "$186,987"):
        chk(f"text present in social render: {s}", s in social)

    # the project's own gate must still pass
    r = subprocess.run([sys.executable, str(PROJECT / "scripts" / "validate_charts.py")], capture_output=True, text=True, cwd=PROJECT)
    chk("scripts/validate_charts.py exits 0 (17 checks)", r.returncode == 0, r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-120:])
    return ok, lines, ex_la


def render(h_tall):
    from playwright.sync_api import sync_playwright
    jobs = [("infographic_state_migration.svg", "infographic_state_migration.png", 1200, h_tall),
            ("infographic_state_migration_social.svg", "infographic_state_migration_social.png", 1600, 900)]
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for sv, pn, w, h in jobs:
            html = f"<!doctype html><html><head><style>*{{margin:0;padding:0}}</style></head><body>{(DOCS / sv).read_text(encoding='utf-8')}</body></html>"
            pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            pg.set_content(html)
            pg.wait_for_timeout(300)
            pg.screenshot(path=str(DOCS / pn), clip={"x": 0, "y": 0, "width": w, "height": h})
            pg.close()
            print("rendered", pn, w, h)
        b.close()


def main():
    d = load()
    F = derive(d)
    (tall, H), (social, _) = build_tall(d, F), build_social(d, F)
    (DOCS / "infographic_state_migration.svg").write_text(tall, encoding="utf-8")
    (DOCS / "infographic_state_migration_social.svg").write_text(social, encoding="utf-8")
    ok, lines, ex_la = validate(d, F, tall, social)
    (ART / "INFOGRAPHIC-VALIDATION.md").write_text(
        "# Infographic data-mark validation \u2014 state-migration\n\n"
        "Every data mark in both renders is parsed back out of the SVG, inverted through its recorded px-per-unit scale, "
        "and compared with a FRESH DuckDB query and with the export parquet files; every number stated in text is asserted.\n\n"
        + "\n".join(lines) + f"\n\n**Result: {'PASS' if ok else 'FAIL'}**\n", encoding="utf-8")
    print("\n".join(lines))
    print("VALIDATION", "PASS" if ok else "FAIL")
    render(H)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
