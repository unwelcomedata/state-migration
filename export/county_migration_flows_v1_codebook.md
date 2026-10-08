# state-migration — Dataset Codebook
Generated: 2026-10-08

## Columns

### `year`
- **Type**: `int64`
- **Non-null**: 53,614 / 53,614 (100.0%)
- **Description**: Migration year = second year of the IRS pair (2023 = the 2022–2023 move).

### `origin_fips`
- **Type**: `object`
- **Non-null**: 53,614 / 53,614 (100.0%)
- **Description**: 5-digit county GEOID people moved FROM (state FIPS + county FIPS).

### `origin_name`
- **Type**: `object`
- **Non-null**: 53,614 / 53,614 (100.0%)
- **Description**: Origin county name.

### `origin_agi_per_return`
- **Type**: `float64`
- **Non-null**: 53,614 / 53,614 (100.0%)
- **Description**: Origin county income proxy: non-migrant AGI per return, in dollars.

### `origin_income_class`
- **Type**: `object`
- **Non-null**: 53,614 / 53,614 (100.0%)
- **Description**: 'above_median' or 'below_median' vs the national median county AGI-per-return.

### `dest_fips`
- **Type**: `object`
- **Non-null**: 53,614 / 53,614 (100.0%)
- **Description**: 5-digit county GEOID people moved TO.

### `dest_name`
- **Type**: `object`
- **Non-null**: 53,614 / 53,614 (100.0%)
- **Description**: Destination county name.

### `dest_agi_per_return`
- **Type**: `float64`
- **Non-null**: 53,614 / 53,614 (100.0%)
- **Description**: Destination county income proxy: non-migrant AGI per return, in dollars.

### `dest_income_class`
- **Type**: `object`
- **Non-null**: 53,614 / 53,614 (100.0%)
- **Description**: 'above_median' or 'below_median' for the destination county.

### `flow_class`
- **Type**: `object`
- **Non-null**: 53,614 / 53,614 (100.0%)
- **Description**: Combined origin→dest income class: above_to_above / above_to_below / below_to_above / below_to_below.

### `irs_returns_out`
- **Type**: `float64`
- **Non-null**: 53,614 / 53,614 (100.0%)
- **Description**: IRS returns (~households) for this county move, from the origin outflow file.

### `irs_returns_in`
- **Type**: `float64`
- **Non-null**: 53,614 / 53,614 (100.0%)
- **Description**: IRS returns from the destination inflow file.

### `irs_individuals_out`
- **Type**: `float64`
- **Non-null**: 53,614 / 53,614 (100.0%)
- **Description**: IRS individuals (~people), origin outflow file.

### `irs_individuals_in`
- **Type**: `float64`
- **Non-null**: 53,614 / 53,614 (100.0%)
- **Description**: IRS individuals, destination inflow file.

### `irs_agi_out`
- **Type**: `float64`
- **Non-null**: 53,614 / 53,614 (100.0%)
- **Description**: AGI for this move (THOUSANDS of dollars), origin outflow file.

### `irs_agi_in`
- **Type**: `float64`
- **Non-null**: 53,614 / 53,614 (100.0%)
- **Description**: AGI (THOUSANDS of dollars), destination inflow file.

## Notes

Source: IRS SOI county-to-county migration (per-state Excel files) — https://www.irs.gov/statistics/soi-tax-stats-migration-data (public domain)

Grain: one row per origin county x destination county x year (directed edge). True county-to-county moves only;
summary rows, foreign, and non-migrant self-edges excluded (non-migrants used only to derive the income proxy).

Income class: each county is flagged above/below the NATIONAL MEDIAN of county AGI-per-return, where a county's
AGI-per-return is its non-migrant total AGI / non-migrant returns (a proxy for resident income). The median is
computed across all ~3,140 counties, one vote per county. This is a county-level income proxy, NOT the income of
the people in each specific flow (IRS does not publish migration by income bracket).
