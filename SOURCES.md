# Data Sources — state-migration

All data used in this project is from authoritative sources. Crowd-edited
references (Wikipedia, etc.) are not used as primary sources.

Document every data source here before ingesting it. Include enough detail
that someone else could independently locate and verify the original data.

---

## Source Template

Copy and fill in for each source. The **How the source collects the data**,
**How the source defines the data**, and **Methodology changes / series breaks**
sections are required — they are what keep our analysis honest and prevent
apples-to-oranges comparisons.

### [Source Name]
- **Publisher:** [Agency, organization, or author]
- **URL:** [Direct link to the file or page]
- **Format:** [CSV | JSON | HTML table | ZIP | PDF | hand-curated]
- **License:** [Public domain | CC0 | CC-BY | proprietary | etc.]
- **Fields used:** [Column names or description of what was extracted]
- **Coverage:** [Geographic scope, date range, or other relevant bounds]
- **How the source collects the data:** [Survey / administrative record / registration /
  model estimate; sampling frame; universe & denominator; who is in/out of the raw collection]
- **How the source defines the data:** [How the counted thing is defined; judgment calls
  in what's included/excluded]
- **Methodology changes / series breaks:** [Dates when definitions/methods changed and
  which periods are NOT comparable; say so explicitly if the series is consistent]
- **Known controversies / debates:** [Contested measurement choices worth a caveat; "None
  known" is valid once checked]
- **Notes:** [Anything else — quirks, suppression, imputation]
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
- **How the source collects the data:** Administrative, derived from **individual income
  tax returns**. SOI compares the mailing address on a filer's return in year 1 vs year 2;
  a change in state = a migrant. The universe is **tax filers and their dependents**, not
  the full population — non-filers (many low-income, elderly, some students) are invisible.
  Returns filed after roughly late September are excluded, so totals won't match other IRS
  products. Not a survey; effectively a near-census of filers who match across years.
- **How the source defines the data:**
  - *`n1`* = number of returns filed ≈ **households**.
  - *`n2`* = number of personal exemptions ≈ **individuals** (a single return can cover 1–4+ people).
  - *`AGI`* = total adjusted gross income, in **thousands of origin-year dollars**.
  - A "migrant" is defined by address change between two filing years, not by intent or
    permanence; a mid-year move is attributed to whichever address was on the returns.
- **Methodology changes / series breaks:**
  - **Two known series breaks.** Beginning with **2011–2012** SOI introduced methodology
    enhancements (a new series vs earlier years), and beginning with **2022–2023** SOI
    enhanced the year-to-year matching process (another new series). Counts on either side
    of these boundaries are **not strictly comparable** — flag any multi-year chart that
    crosses 2011–12 or 2022–23. This project's release uses 2023 (a single year), so it does
    not cross a break, but a future time series must caveat both.
  - Late-filed returns are excluded consistently but shift totals slightly vs full-year IRS data.
- **Known controversies / debates:** IRS migration data is widely used in "people vote with
  their feet" tax-policy arguments; critics note it captures *filers* (skewing toward higher
  incomes and away from non-filers) and that AGI is income at origin, not a measure of the
  mover's later earnings. Attribute carefully.
- **Notes:** Special FIPS codes: 96 = total (US + foreign), 97 = total US, 98 = foreign,
  59 = overseas.
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
- **How the source collects the data:** Same administrative tax-return basis as the state
  file (address change between filing years), tabulated at county level. Universe = tax
  filers + dependents who match across years; non-filers excluded.
- **How the source defines the data:** `n1` ≈ households, `n2` ≈ individuals, `AGI` in
  thousands of dollars — identical definitions to the state file. **Income class describes
  the county (place), not the income of the people in each flow** — it is derived from each
  county's non-migrant AGI-per-return, then flagged above/below the national median. IRS
  does not publish migration by income bracket, so "who is rich/poor" here is a property of
  *where they live*, not of the movers.
- **Methodology changes / series breaks:** Same 2011–12 and 2022–23 SOI series breaks as the
  state file. File format also changed (`.xls` for 2011–2020 pairs, `.xlsx` from 2020–2021),
  a cosmetic break only. Currently only 2022–2023 is ingested, so no cross-break comparison
  is made.
- **Known controversies / debates:** The large, non-random suppression (below) is the main
  caveat; county figures are best for the *shape* of movement, not exact totals.
- **Notes / caveats:**
  - **Disclosure suppression is large and non-random.** The IRS suppresses small
    county-to-county flows (roughly fewer than 10 returns) and bundles them into
    "Other flows" regional aggregate rows (dest state codes 58/59), which we exclude
    from the county edge table. As a result, **identified county-to-county edges
    account for only ~60% of domestic county movement nationally** (and ~80% of a
    large directed state pair like CA→TX). County totals therefore **undercount**
    true movement, and the undercount concentrates in *small* flows.
  - Non-migrant rows are used only to derive the income proxy; they are stored in
    `county_nonmigrants`, not in the flow edges.
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
- **How the source collects the data:** A **survey** (American Community Survey, ~3.5M
  household sample per year), not administrative records. Migration comes from the question
  "Where did you live 1 year ago?" Because it's a sample, every estimate carries a **margin
  of error (MOE, 90% confidence)**; small flows are statistically unreliable.
- **How the source defines the data:** *Migrant* = a person (universe: population age 1+)
  whose residence one year ago differs from their current residence. Unlike IRS, this
  **captures everyone regardless of tax-filing status** — it counts people, not returns, and
  includes non-filers. "People-weighted" vs the IRS "income-weighted" view.
- **Methodology changes / series breaks:**
  - **2020 1-year ACS was not released** (COVID-19 response-rate problems) — there is a
    literal gap; never interpolate across it as if continuous.
  - **2022 Connecticut** has a known processing error (corrected in 2023) — treat 2022 CT
    flows as suspect.
  - ACS methodology is otherwise consistent, but sample redesigns and control-total updates
    can nudge estimates; compare within the 1-year series only (never mix 1-year and 5-year).
- **Known controversies / debates:** IRS (filers, income-weighted) and ACS (people-weighted
  survey) measure different universes and will not match exactly — this project reports both
  side by side rather than reconciling them to one number (validated at Pearson r≈0.86).
- **Notes:** MOE reflects sampling uncertainty; a large MOE relative to the estimate means
  the flow is unreliable.
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

### Series breaks & comparability (read before any multi-year comparison)

- **IRS SOI: breaks at 2011–12 and 2022–23.** Methodology enhancement (2011–12) and an
  improved matching process (2022–23) mean counts across those boundaries are not strictly
  comparable. A time-series chart spanning either must carry a visible caveat.
- **ACS: 2020 is missing** (no 1-year release) and **2022 Connecticut is erroneous**
  (fixed in 2023). Do not interpolate across the 2020 gap.
- **IRS vs ACS measure different universes** (tax filers/income-weighted vs all residents/
  people-weighted). They correlate strongly (r≈0.86) but must not be treated as the same
  number — report the method next to any figure.

---

## Source Provenance in DuckDB

Every table in `data/project.duckdb` has a corresponding entry in the
`_sources` metadata table:

```sql
SELECT duckdb_table, source_name, methodology, series_breaks FROM _sources;
```

Alongside `source_name`, `url`, `license`, `notes`, `retrieved`, the table carries
**`methodology`** (how the source collects/defines the data) and **`series_breaks`**
(the IRS 2011–12 / 2022–23 breaks and the ACS 2020 gap), so provenance travels with the
data. Keep these in sync with the per-source sections above.
