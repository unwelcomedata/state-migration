# state-migration — Dataset Codebook
Generated: 2026-08-30

## Columns

### `year`
- **Type**: `int64`
- **Non-null**: 38,756 / 38,756 (100.0%)
- **Description**: Migration year = the later of the two years compared (IRS 2022–23 pair and ACS 2023 survey both map to 2023).

### `origin_fips`
- **Type**: `object`
- **Non-null**: 38,756 / 38,756 (100.0%)
- **Description**: FIPS code of the origin (state people moved FROM). Non-state codes: 72=Puerto Rico, 57=Foreign Country; U.S. Island Areas uses sentinel US-ISL.

### `origin_state`
- **Type**: `object`
- **Non-null**: 38,756 / 38,756 (100.0%)
- **Description**: Two-letter abbreviation of the origin.

### `origin_state_name`
- **Type**: `object`
- **Non-null**: 38,756 / 38,756 (100.0%)
- **Description**: Full name of the origin.

### `origin_type`
- **Type**: `object`
- **Non-null**: 38,756 / 38,756 (100.0%)
- **Description**: Origin location type: state, dc, territory (PR / U.S. Island Areas), or foreign.

### `dest_fips`
- **Type**: `object`
- **Non-null**: 38,756 / 38,756 (100.0%)
- **Description**: FIPS code of the destination (state people moved TO). Same coding as origin_fips.

### `dest_state`
- **Type**: `object`
- **Non-null**: 38,756 / 38,756 (100.0%)
- **Description**: Two-letter abbreviation of the destination.

### `dest_state_name`
- **Type**: `object`
- **Non-null**: 38,756 / 38,756 (100.0%)
- **Description**: Full name of the destination.

### `dest_type`
- **Type**: `object`
- **Non-null**: 38,756 / 38,756 (100.0%)
- **Description**: Destination location type: state, dc, territory, or foreign.

### `irs_returns_out`
- **Type**: `Int64`
- **Non-null**: 31,123 / 38,756 (80.3%)
- **Description**: IRS: number of tax returns (~households) for this origin→dest move, as reported in the ORIGIN state outflow file. Raw counts (not thousands).

### `irs_returns_in`
- **Type**: `Int64`
- **Non-null**: 31,122 / 38,756 (80.3%)
- **Description**: IRS: number of tax returns (~households) for this origin→dest move, as reported in the DESTINATION state inflow file. Usually equals irs_returns_out; differs slightly in later series.

### `irs_individuals_out`
- **Type**: `Int64`
- **Non-null**: 31,123 / 38,756 (80.3%)
- **Description**: IRS: number of personal exemptions (~people) for this move, from the origin outflow file.

### `irs_individuals_in`
- **Type**: `Int64`
- **Non-null**: 31,122 / 38,756 (80.3%)
- **Description**: IRS: number of personal exemptions (~people) for this move, from the destination inflow file.

### `irs_agi_out`
- **Type**: `Int64`
- **Non-null**: 31,123 / 38,756 (80.3%)
- **Description**: IRS: total adjusted gross income for this move (in THOUSANDS of dollars), from the origin outflow file.

### `irs_agi_in`
- **Type**: `Int64`
- **Non-null**: 31,122 / 38,756 (80.3%)
- **Description**: IRS: total adjusted gross income for this move (in THOUSANDS of dollars), from the destination inflow file.

### `acs_migrants`
- **Type**: `Int64`
- **Non-null**: 35,543 / 38,756 (91.7%)
- **Description**: Census ACS: estimated number of people who made this origin→dest move (survey estimate).

### `acs_moe`
- **Type**: `Int64`
- **Non-null**: 35,543 / 38,756 (91.7%)
- **Description**: Census ACS: margin of error (± people) on acs_migrants at 90% confidence.

### `acs_moe_pct`
- **Type**: `float64`
- **Non-null**: 32,415 / 38,756 (83.6%)
- **Description**: acs_moe as a fraction of acs_migrants. Higher = less reliable.

### `acs_reliable`
- **Type**: `boolean`
- **Non-null**: 32,415 / 38,756 (83.6%)
- **Description**: True when acs_moe is less than 50% of acs_migrants (a usability cutoff for small survey flows).

## Notes

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
