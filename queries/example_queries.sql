-- ============================================================================
-- state-migration — example queries
-- ============================================================================
-- Reference queries against data/project.duckdb. Safe to run read-only.
--
-- How to run (DBCode): open this file, connect to the DuckDB file at
--   data-projects/state-migration/data/project.duckdb  (read-only recommended),
--   then Cmd+Enter on a statement to run it.
--
-- For a personal scratchpad that stays out of git, create `scratch.sql`
-- in this project (it's gitignored).
-- ============================================================================


-- ── Orientation ─────────────────────────────────────────────────────────────

-- What tables exist?
SHOW TABLES;

-- Provenance for every table
SELECT table_name, source_name, retrieved_date, row_count
FROM _sources
ORDER BY table_name;

-- The location crosswalk (FIPS <-> abbrev <-> name <-> type)
SELECT * FROM state_ref ORDER BY loc_type, name;


-- ── migration_flows: grain is one row per origin x destination x year ─────────

-- Peek at the schema
DESCRIBE migration_flows;

-- INCOMING to a state: everyone who moved INTO Florida in 2023,
-- biggest origins first (ACS people estimate).
SELECT origin_state_name, acs_migrants, acs_moe, acs_reliable,
       irs_individuals_in AS irs_people
FROM migration_flows
WHERE dest_state = 'FL' AND year = 2023
ORDER BY acs_migrants DESC NULLS LAST
LIMIT 15;

-- OUTGOING from a state: everyone who left California in 2023.
SELECT dest_state_name, acs_migrants, acs_moe, acs_reliable,
       irs_individuals_out AS irs_people
FROM migration_flows
WHERE origin_state = 'CA' AND year = 2023
ORDER BY acs_migrants DESC NULLS LAST
LIMIT 15;

-- A single directed edge over time (Texas -> Florida across all years).
SELECT year, irs_returns_out, irs_individuals_out, irs_agi_out,
       acs_migrants, acs_moe, acs_reliable
FROM migration_flows
WHERE origin_state = 'TX' AND dest_state = 'FL'
ORDER BY year;


-- ── Aggregations ──────────────────────────────────────────────────────────

-- Total IRS individuals leaving each state in 2023 (state-to-state only).
SELECT origin_state_name AS state,
       SUM(irs_individuals_out) AS people_out
FROM migration_flows
WHERE year = 2023 AND origin_type IN ('state', 'dc')
GROUP BY 1
ORDER BY people_out DESC;

-- NET migration by state, 2023 (IRS individuals): inflow minus outflow.
-- Note: net requires pairing both directions, so we aggregate in two CTEs.
WITH outbound AS (
    SELECT origin_state AS st, SUM(irs_individuals_out) AS gone
    FROM migration_flows
    WHERE year = 2023 AND origin_type IN ('state', 'dc')
    GROUP BY 1
),
inbound AS (
    SELECT dest_state AS st, SUM(irs_individuals_in) AS came
    FROM migration_flows
    WHERE year = 2023 AND dest_type IN ('state', 'dc')
    GROUP BY 1
)
SELECT COALESCE(i.st, o.st) AS state,
       came, gone,
       (came - gone) AS net_individuals
FROM inbound i
FULL OUTER JOIN outbound o ON i.st = o.st
ORDER BY net_individuals DESC;

-- AGI-weighted flows: average income per return moving TX -> FL, 2023.
-- (AGI is in thousands of dollars, so multiply by 1000 for dollars.)
SELECT year,
       irs_returns_out,
       irs_agi_out AS agi_thousands,
       ROUND(irs_agi_out * 1000.0 / irs_returns_out, 0) AS agi_per_return_dollars
FROM migration_flows
WHERE origin_state = 'TX' AND dest_state = 'FL' AND year = 2023;


-- ── Data-quality lenses ───────────────────────────────────────────────────

-- Where do IRS outflow and inflow measurements disagree? (later series only)
SELECT year, origin_state, dest_state, irs_returns_out, irs_returns_in
FROM migration_flows
WHERE irs_returns_out <> irs_returns_in
ORDER BY year, origin_state, dest_state;

-- Unreliable ACS flows (margin of error >= 50% of the estimate).
SELECT year, origin_state, dest_state, acs_migrants, acs_moe, acs_moe_pct
FROM migration_flows
WHERE acs_reliable = FALSE
ORDER BY acs_moe_pct DESC
LIMIT 25;

-- Coverage by year: how many rows have IRS vs ACS data?
SELECT year,
       COUNT(*) AS edges,
       COUNT(irs_returns_out) AS has_irs,
       COUNT(acs_migrants)    AS has_acs
FROM migration_flows
GROUP BY year
ORDER BY year;


-- ── nonmigrants: one row per state x year (people who stayed put) ───────────

SELECT year, state_name, nonmig_returns, nonmig_individuals, nonmig_agi
FROM nonmigrants
WHERE year = 2023
ORDER BY nonmig_individuals DESC;
