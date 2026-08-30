# Data Sources — state-migration

All data used in this project is from authoritative sources. Crowd-edited
references (Wikipedia, etc.) are not used as primary sources.

Document every data source here before ingesting it. Include enough detail
that someone else could independently locate and verify the original data.

---

## Source Template

Copy and fill in for each source:

### [Source Name]
- **Publisher:** [Agency, organization, or author]
- **URL:** [Direct link to the file or page]
- **Format:** [CSV | JSON | HTML table | ZIP | PDF | hand-curated]
- **License:** [Public domain | CC0 | CC-BY | proprietary | etc.]
- **Fields used:** [Column names or description of what was extracted]
- **Coverage:** [Geographic scope, date range, or other relevant bounds]
- **Notes:** [Any caveats, known issues, or methodology notes]
- **Retrieved:** [YYYY-MM-DD]

---

## Sources

### IRS Statistics of Income (SOI) — State-to-State Migration Data
- **Publisher:** Internal Revenue Service, Statistics of Income Division
- **URL:** https://www.irs.gov/statistics/soi-tax-stats-migration-data
- **Format:** CSV (state-to-state inflow and outflow files, one pair per year)
- **License:** Public domain (U.S. government work, no copyright)
- **Fields used:**
  - `y1_statefips` / `y2_statefips` — FIPS code for origin/destination state
  - `y1_state` / `y2_state` — two-letter state abbreviation
  - `y1_state_name` / `y2_state_name` — state name or summary row label
  - `n1` — number of returns filed (approximates households)
  - `n2` — number of personal exemptions claimed (approximates individuals)
  - `AGI` — total adjusted gross income (in thousands of dollars)
- **Coverage:** All 50 states + DC, filing years 2011–2012 through 2022–2023 (12 year-pairs)
- **Notes:**
  - Data derived from year-to-year address changes on individual income tax returns.
  - Beginning with 2011–2012, SOI introduced methodology enhancements (new series).
  - Beginning with 2022–2023, SOI enhanced the matching process (another new series).
  - Special FIPS codes: 96 = total (US + foreign), 97 = total US, 98 = foreign, 59 = overseas.
  - Returns filed after late September are excluded; totals may not match other IRS products.
  - n1/n2 represent tax filers, not total population. A single return may cover 1–4+ people.
  - AGI is in thousands of dollars.
- **Retrieved:** 2026-08-25

### IRS Statistics of Income (SOI) — County-to-County Migration Data
- **Publisher:** Internal Revenue Service, Statistics of Income Division
- **URL:** https://www.irs.gov/statistics/soi-tax-stats-migration-data (per-state Excel files, e.g. `https://www.irs.gov/pub/irs-soi/2223ca.xlsx`)
- **Format:** Excel — one file per state (50 + DC), each with 4 sheets: State Outflow/Inflow, County Outflow/Inflow. We use the County sheets.
- **License:** Public domain (U.S. government work, no copyright)
- **Fields used (County sheets):**
  - origin/destination state FIPS + county FIPS (combined into a 5-digit GEOID)
  - `n1` — number of returns (~households)
  - `n2` — number of individuals / exemptions (~people)
  - `AGI` — adjusted gross income (in thousands of dollars)
- **Coverage:** 50 states + DC (Puerto Rico has no county file). Currently ingested: 2022–2023 only. File extension is `.xls` for 2011–2020 pairs and `.xlsx` for 2020–2021 onward.
- **Derived income proxy:** each county's **AGI-per-return** is computed from its
  non-migrant row (residents who filed from the same county both years) as
  `AGI * 1000 / returns`. Counties are flagged **above/below the national median**
  of this proxy (one vote per county, ~3,140 counties).
- **Notes / caveats:**
  - **Disclosure suppression is large and non-random.** The IRS suppresses small
    county-to-county flows (roughly fewer than 10 returns) and bundles them into
    "Other flows" regional aggregate rows (dest state codes 58/59), which we exclude
    from the county edge table. As a result, **identified county-to-county edges
    account for only ~60% of domestic county movement nationally** (and ~80% of a
    large directed state pair like CA→TX). County totals therefore **undercount**
    true movement, and the undercount concentrates in *small* flows. Use county
    data for the *shape* of movement between identified places, not exact totals.
  - Non-migrant rows are used only to derive the income proxy; they are stored in
    `county_nonmigrants`, not in the flow edges.
  - Income class describes the **county** (place), not the income of the specific
    people in each flow. IRS does not publish migration by income bracket.
  - Same FIPS/summary-code conventions as the state files (96/97/98 summaries,
    57 foreign, dropped from edges).
- **Retrieved:** 2026-08-30

### Census Bureau — ACS State-to-State Migration Flows
- **Publisher:** U.S. Census Bureau, American Community Survey
- **URL:** https://www.census.gov/data/tables/time-series/demo/geographic-mobility/state-to-state-migration.html
- **Format:** Excel (.xls / .xlsx) — wide crosstab with estimates and margins of error
- **License:** Public domain (U.S. government work, no copyright)
- **Fields used:**
  - Origin state (row) × Destination state (column) migration flow
  - Estimate (number of people)
  - Margin of error (MOE ±, 90% confidence)
  - Includes: same state, different state, and abroad
- **Coverage:** All 50 states + DC + Puerto Rico, ACS 1-year data, 2011–2024 (no 2020)
- **Notes:**
  - Based on survey question "Where did you live 1 year ago?"
  - Captures all residents regardless of tax filing status (unlike IRS data)
  - Subject to sampling variability — MOE reflects ~3.5M household sample
  - 2020 not released due to COVID-19 response rate issues
  - 2022 Connecticut data has known processing error (corrected in 2023)
  - Universe: population 1 year and over
- **Retrieved:** 2026-08-25

---

## Column Glossary

Definitions for the fields used across the raw sources and the prepared
`migration_flows` / `nonmigrants` tables.

### IRS SOI raw fields
- **`y1_statefips` / `y2_statefips`** — FIPS code of the state in year 1 (origin) / year 2 (destination).
- **`y1_state` / `y2_state`** — two-letter abbreviation of that state.
- **`y1_state_name` / `y2_state_name`** — state name or summary-row label.
- **`n1`** — number of tax returns filed (approximates **households**).
- **`n2`** — number of personal exemptions claimed (approximates **individuals / people**).
- **`AGI`** — total adjusted gross income, in **thousands of dollars**.
- **Special FIPS codes:** `96` = total (US + foreign), `97` = total US, `98` = foreign,
  `57` = foreign country (as an origin), `72` = Puerto Rico, `59` = overseas.
  A row where `y1_statefips == y2_statefips` is a **non-migrant** (stayed-put) row.

### Census ACS raw fields
- **`origin`** — state of residence **1 year ago** (where the person moved *from*).
- **`destination`** — current state of residence (where the person moved *to*).
- **`migrants`** — ACS **estimate** of the number of people who made that move.
- **`moe`** — **margin of error** on the estimate, ± people, at **90% confidence**.
  ACS is a survey (~3.5M households), so every estimate carries sampling uncertainty.
  A large `moe` relative to `migrants` means the flow is statistically unreliable.

### Prepared `migration_flows` fields
- **`year`** — migration year = the later of the two years compared. IRS 2022–23 pair and
  ACS 2023 survey both map to `year = 2023`.
- **`origin_*` / `dest_*`** — `fips`, `state` (abbrev), `state_name` (full), and `type`
  (`state`, `dc`, `territory`, `foreign`) for each endpoint.
- **`irs_returns_out` / `irs_returns_in`** — IRS `n1` (households) as reported by the origin
  outflow file / destination inflow file. Usually equal; differs slightly in later series.
- **`irs_individuals_out` / `irs_individuals_in`** — IRS `n2` (people), from each file.
- **`irs_agi_out` / `irs_agi_in`** — IRS `AGI` (thousands of dollars), from each file.
- **`acs_migrants`** — ACS estimated people who made this move.
- **`acs_moe`** — ACS margin of error (± people, 90% confidence).
- **`acs_moe_pct`** — `acs_moe` as a fraction of `acs_migrants` (higher = less reliable).
- **`acs_reliable`** — `True` when `acs_moe` is under 50% of `acs_migrants` (usability cutoff).

### Prepared `nonmigrants` fields
- **`year`, `fips`, `state`, `state_name`** — the state and migration year.
- **`nonmig_returns` / `nonmig_individuals` / `nonmig_agi`** — IRS `n1` / `n2` / `AGI` for
  filers who stayed in the same state both years (`y1_statefips == y2_statefips`).

### Prepared `county_migration_flows` fields
- **`year`** — migration year (second year of the IRS pair).
- **`origin_fips` / `dest_fips`** — 5-digit county GEOID (state FIPS + county FIPS).
- **`origin_name` / `dest_name`** — county names.
- **`origin_agi_per_return` / `dest_agi_per_return`** — county income proxy in dollars
  (non-migrant AGI per return).
- **`origin_income_class` / `dest_income_class`** — `above_median` / `below_median`
  vs the national median county AGI-per-return.
- **`flow_class`** — combined class of the directed move: `above_to_above`,
  `above_to_below`, `below_to_above`, `below_to_below`.
- **`irs_returns_out/_in`, `irs_individuals_out/_in`, `irs_agi_out/_in`** — same meaning
  as the state flows (out = origin file, in = destination file; AGI in thousands).

### Prepared `county_nonmigrants` / `county_income_class` fields
- **`fips`, `name`, `year`** — county and year.
- **`nonmig_returns` / `nonmig_individuals` / `nonmig_agi`** — IRS `n1` / `n2` / `AGI` for
  county residents who did not move.
- **`agi_per_return`** — income proxy in dollars (`nonmig_agi * 1000 / nonmig_returns`).
- **`national_median`** — the national median of `agi_per_return` across all counties that year.
- **`income_class`** — `above_median` / `below_median`.

---

## Notes on Data Quality

- All source files are saved verbatim to `data/raw/` and never modified.
- Discrepancies between sources should be noted here and resolved explicitly.

---

## Source Provenance in DuckDB

Every table in `data/project.duckdb` has a corresponding entry in the
`_sources` metadata table:

```sql
SELECT * FROM _sources;
```
