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
