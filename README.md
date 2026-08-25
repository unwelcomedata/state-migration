# state-migration

> **AI-Assisted Development**
> This project was built with the assistance of [Kiro](https://kiro.dev),
> an AI-powered development environment. All data sourcing decisions,
> methodology choices, and published findings are the responsibility of the
> author. AI was used for code generation, data pipeline construction, and
> research assistance — not for analysis conclusions or editorial judgment.

---

## Data Sources

All data sources are documented in [SOURCES.md](SOURCES.md) with full
attribution, URLs, licenses, and retrieval notes.

Source provenance is also recorded inside the project database:

```sql
-- Open data/project.duckdb and run:
SELECT * FROM _sources;
```

---

## Project Structure

```
state-migration/
├── config.yaml              ← sources, paths, export settings — edit this first
├── SOURCES.md               ← full data source attribution
├── requirements.txt
├── data/
│   ├── raw/                 ← original downloaded files, never modified
│   ├── interim/             ← cleaned Parquet files (1:1 match DuckDB table names)
│   ├── processed/           ← analysis-ready Parquet files
│   └── project.duckdb       ← single-file database for the project
├── export/                  ← packaged datasets (CSV, Excel, Parquet + codebook)
├── outputs/                 ← exploratory chart PNGs (from 04-viz)
│   └── social/             ← publication-ready charts for posting (from 04b-viz-social)
├── scripts/
│   ├── README.md            ← pipeline run order and conventions
│   ├── ingest_all.py        ← reproducible ingestion
│   ├── clean_all.py         ← standardize raw tables
│   └── prepare_export.py    ← build final export
├── notebooks/
│   ├── 00-explore.ipynb     ← DuckDB query sandbox
│   ├── 01-ingest.ipynb      ← fetch sources → data/raw/ → DuckDB
│   ├── 02-clean.ipynb       ← clean + quality checks → data/interim/
│   ├── 03-prepare.ipynb     ← feature engineering + export packaging
│   ├── 04-viz.ipynb         ← exploratory charts → outputs/
│   ├── 04b-viz-social.ipynb ← publication social charts → outputs/social/
│   └── 05-analysis.ipynb    ← statistical analysis + findings
└── src/
    ├── ingest.py            ← fetch helpers (caching, rate limiting)
    ├── clean_quality.py     ← DuckDB cleaning + quality reports + _sources
    ├── prepare.py           ← PII stripping, codebook, packaging
    ├── viz.py               ← matplotlib chart builders (exploratory)
    └── viz_social.py        ← Altair + vl-convert social export
```

---

## Workflow

### 1. Configure `config.yaml`

Add each data source under the `sources:` block before ingesting:

```yaml
sources:
  my_source:
    url: https://example.gov/data/table
    type: html_table      # html_table | html_scrape | csv | json
    table_index: 0
    js_render: false
```

### 2. Document sources in `SOURCES.md`

Before ingesting any data, add an entry to `SOURCES.md` for each source:
- Full URL
- Publisher / agency
- License
- Fields used
- Any caveats

### 3. Ingest (`01-ingest.ipynb`)

```python
from src.ingest import load_config, ingest_source
cfg = load_config("config.yaml")
df = ingest_source("my_source", cfg)
```

Raw files land in `data/raw/` untouched. All tables load into DuckDB at
`data/project.duckdb` with source metadata written to `_sources`.

### 4. Clean (`02-clean.ipynb`)

```python
from src.clean_quality import get_connection, clean_table, quality_report, save_interim
con = get_connection(cfg)
df_clean = clean_table(df, "my_source_raw", con, cast_map={"year": "INTEGER"})
quality_report(df_clean, "my_source_clean", con)
save_interim(df_clean, cfg, "my_source_clean.parquet")
```

### 5. Prepare & export (`03-prepare.ipynb`)

```python
from src.prepare import package_dataset
package_dataset(df, cfg, name="my_dataset_v1",
                codebook={"col": "description"},
                notes="Source: Agency. License: Public domain.")
```

### 6. Visualize (`04-viz.ipynb` + `04b-viz-social.ipynb`)

**04-viz** is for exploratory charting (matplotlib). Output goes to `outputs/`.

```python
from src.viz import ranked_bar_chart, save_chart
fig = ranked_bar_chart(df, x="state", y="rate", title="Top 10 States", top_n=10,
                       preset="instagram_portrait")
save_chart(fig, cfg, "top10_states", preset="instagram_portrait",
           add_watermark="@unwelcomedata")
```

**04b-viz-social** is for publication-ready charts (Altair + vl-convert).
Output goes to `outputs/social/`. Only curated, validated charts go here.

```python
from src.viz_social import save_social
save_social(chart, cfg, 'my_social_chart', preset='twitter_landscape')
```

### 7. Analyze (`05-analysis.ipynb`)

Statistical analysis, regression, group comparisons. Always read from the
**export** parquet (not raw DuckDB tables) to ensure consistency with
published data.

---

## Anonymity

Commits are authored as `unwelcomedata` to keep the author's real identity
off the public commit history. Data files, exports, outputs, and `.env`
secrets are excluded from version control via `.gitignore`.
