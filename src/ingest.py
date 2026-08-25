"""Web ingestion utilities for state-migration project.

Primary source: IRS SOI State-to-State Migration Data (2011–2023)
  - Downloads inflow and outflow CSVs for each year pair
  - Saves raw files to data/raw/ unchanged

Also includes generic helpers for html_table, html_scrape, csv, json
sources defined in config.yaml.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yaml
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config(config_path: str | Path = "config.yaml") -> dict[str, Any]:
    """Load project config.yaml and return it as a dict."""
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def raw_path(cfg: dict, filename: str) -> Path:
    """Return a Path inside data/raw, creating the directory if needed."""
    p = Path(cfg["paths"]["data_raw"]) / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_CACHE_DIR: Path | None = None


def _get_cache_dir(cfg: dict) -> Path:
    """Return the cache directory (data/raw by default)."""
    global _CACHE_DIR
    if _CACHE_DIR is None:
        _CACHE_DIR = Path(cfg["paths"]["data_raw"])
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR


def fetch_html(url: str, headers: dict | None = None, timeout: int = 30) -> str:
    """Fetch a URL and return the response text.

    Raises requests.HTTPError on non-2xx status.
    """
    hdrs = {**_DEFAULT_HEADERS, **(headers or {})}
    resp = requests.get(url, headers=hdrs, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch_cached(
    url: str,
    filename: str,
    cfg: dict,
    max_age_hours: float = 24.0,
    headers: dict | None = None,
    timeout: int = 30,
) -> str:
    """Fetch a URL with local file caching.

    If a cached file exists and is younger than max_age_hours, returns its
    contents without making a network request. Otherwise fetches, saves to
    data/raw/{filename}, and returns the content.

    Args:
        url:            URL to fetch.
        filename:       Cache filename (saved in data/raw/).
        cfg:            Loaded config dict.
        max_age_hours:  Re-fetch if cache is older than this (0 = always fetch).
        headers:        Optional extra HTTP headers.
        timeout:        Request timeout in seconds.

    Returns:
        Response text (from cache or network).
    """
    cache_path = _get_cache_dir(cfg) / filename
    if cache_path.exists() and max_age_hours > 0:
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < max_age_hours:
            return cache_path.read_text(encoding="utf-8")

    text = fetch_html(url, headers=headers, timeout=timeout)
    cache_path.write_text(text, encoding="utf-8")
    return text


def fetch_with_retry(
    url: str,
    headers: dict | None = None,
    timeout: int = 30,
    max_retries: int = 3,
    rate_limit_seconds: float = 1.5,
) -> str:
    """Fetch a URL with rate limiting and exponential backoff on 429s.

    Args:
        url:                 URL to fetch.
        headers:             Optional extra HTTP headers.
        timeout:             Request timeout in seconds.
        max_retries:         Max retry attempts on 429/5xx.
        rate_limit_seconds:  Minimum delay between requests.

    Returns:
        Response text.

    Raises:
        requests.HTTPError after exhausting retries.
    """
    hdrs = {**_DEFAULT_HEADERS, **(headers or {})}
    time.sleep(rate_limit_seconds)

    for attempt in range(max_retries + 1):
        resp = requests.get(url, headers=hdrs, timeout=timeout)
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt < max_retries:
                wait = rate_limit_seconds * (2 ** attempt)
                print(f"  ⚠ {resp.status_code} on {url} — retrying in {wait:.0f}s")
                time.sleep(wait)
                continue
        resp.raise_for_status()
        return resp.text

    resp.raise_for_status()  # will raise on the last failed attempt
    return ""  # unreachable


def fetch_html_js(url: str, wait_selector: str | None = None, timeout: int = 30000) -> str:
    """Fetch a JS-rendered page using Playwright (headless Chromium).

    Use this when fetch_html() returns an empty or incomplete page.
    Requires: playwright install chromium

    Args:
        url:           Page URL.
        wait_selector: Optional CSS selector to wait for before returning HTML.
        timeout:       Playwright timeout in milliseconds.
    """
    from playwright.sync_api import sync_playwright  # lazy import

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(extra_http_headers=_DEFAULT_HEADERS)
        page.goto(url, timeout=timeout)
        if wait_selector:
            page.wait_for_selector(wait_selector, timeout=timeout)
        else:
            page.wait_for_load_state("networkidle", timeout=timeout)
        html = page.content()
        browser.close()
    return html


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_html_table(html: str, table_index: int = 0) -> pd.DataFrame:
    """Extract a <table> from HTML by index and return it as a DataFrame.

    Cleans up column names: lowercase, spaces → underscores.
    """
    tables = pd.read_html(html)
    if not tables:
        raise ValueError("No tables found in the provided HTML.")
    if table_index >= len(tables):
        raise IndexError(
            f"table_index {table_index} out of range — page has {len(tables)} table(s)."
        )
    df = tables[table_index]
    df.columns = [
        str(c).strip().lower().replace(" ", "_").replace("-", "_")
        for c in df.columns
    ]
    return df


def parse_html_scrape(
    html: str,
    row_selector: str,
    field_map: dict[str, str],
) -> pd.DataFrame:
    """Scrape structured rows from HTML using CSS selectors.

    Args:
        html:          Raw HTML string.
        row_selector:  CSS selector that matches each "row" element.
        field_map:     Dict mapping output column name → CSS selector
                       relative to each row element.
                       Use '' (empty string) to get the row's own text.

    Example:
        parse_html_scrape(html, "tr.data-row", {"name": "td.name", "value": "td.val"})
    """
    soup = BeautifulSoup(html, "lxml")
    rows = soup.select(row_selector)
    records = []
    for row in rows:
        record: dict[str, str] = {}
        for col, selector in field_map.items():
            el = row.select_one(selector) if selector else row
            record[col] = el.get_text(" ", strip=True) if el else ""
        records.append(record)
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def download_file(url: str, dest: Path, headers: dict | None = None, timeout: int = 60) -> Path:
    """Stream-download a file (CSV, JSON, zip, etc.) to dest and return the path."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    hdrs = {**_DEFAULT_HEADERS, **(headers or {})}
    with requests.get(url, headers=hdrs, timeout=timeout, stream=True) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
    return dest


# ---------------------------------------------------------------------------
# Source-driven ingest (reads config.yaml sources block)
# ---------------------------------------------------------------------------

def ingest_source(
    name: str,
    cfg: dict,
    save_raw: bool = True,
    js_wait_selector: str | None = None,
    row_selector: str | None = None,
    field_map: dict[str, str] | None = None,
    rate_limit_seconds: float = 1.0,
) -> pd.DataFrame:
    """Ingest a named source from config.yaml and return a DataFrame.

    Args:
        name:               Key under `sources:` in config.yaml.
        cfg:                Loaded config dict (from load_config()).
        save_raw:           If True, save the raw HTML/bytes to data/raw/.
        js_wait_selector:   Passed to fetch_html_js() if js_render is true.
        row_selector:       Required for html_scrape type.
        field_map:          Required for html_scrape type.
        rate_limit_seconds: Polite delay before fetching.
    """
    source = cfg["sources"][name]
    url: str = source["url"]
    source_type: str = source.get("type", "html_table")
    js_render: bool = source.get("js_render", False)
    table_index: int = source.get("table_index", 0)

    time.sleep(rate_limit_seconds)

    if source_type == "csv":
        dest = raw_path(cfg, f"{name}.csv")
        download_file(url, dest)
        return pd.read_csv(dest, encoding=cfg["settings"]["encoding"])

    if source_type == "json":
        dest = raw_path(cfg, f"{name}.json")
        download_file(url, dest)
        with open(dest, encoding=cfg["settings"]["encoding"]) as f:
            data = json.load(f)
        return pd.json_normalize(data)

    # HTML-based types
    html = fetch_html_js(url, wait_selector=js_wait_selector) if js_render else fetch_html(url)

    if save_raw:
        raw_path(cfg, f"{name}.html").write_text(html, encoding="utf-8")

    if source_type == "html_table":
        return parse_html_table(html, table_index=table_index)

    if source_type == "html_scrape":
        if row_selector is None or field_map is None:
            raise ValueError("html_scrape requires row_selector and field_map arguments.")
        return parse_html_scrape(html, row_selector, field_map)

    raise ValueError(f"Unknown source type '{source_type}'. Use: html_table, html_scrape, csv, json.")


# ---------------------------------------------------------------------------
# IRS SOI Migration Data — bulk download
# ---------------------------------------------------------------------------

def ingest_irs_soi_migration(
    cfg: dict,
    years: list[str] | None = None,
    directions: list[str] | None = None,
    skip_existing: bool = True,
) -> dict[str, Path]:
    """Download IRS SOI state-to-state migration CSVs.

    Reads the `irs_soi_migration` source block from config.yaml and downloads
    all year × direction combinations to data/raw/.

    Args:
        cfg:            Loaded config dict.
        years:          Override list of year codes (e.g. ["2122", "2223"]).
                        If None, uses all years from config.
        directions:     Override list of directions (["inflow", "outflow"]).
                        If None, uses both from config.
        skip_existing:  If True, skip files that already exist in data/raw/.

    Returns:
        Dict mapping filename → Path for all downloaded files.
    """
    source = cfg["sources"]["irs_soi_migration"]
    base_url = source["base_url"]
    year_list = years or source["years"]
    direction_list = directions or source["directions"]
    pattern = source["filename_pattern"]
    rate_limit = cfg["settings"].get("rate_limit_seconds", 1.5)

    downloaded: dict[str, Path] = {}

    total = len(year_list) * len(direction_list)
    count = 0

    for year in year_list:
        for direction in direction_list:
            filename = pattern.format(direction=direction, year=year)
            url = f"{base_url}/{filename}"
            dest = raw_path(cfg, filename)
            count += 1

            if skip_existing and dest.exists():
                print(f"  [{count}/{total}] skip (exists): {filename}")
                downloaded[filename] = dest
                continue

            print(f"  [{count}/{total}] downloading: {filename}")
            try:
                download_file(url, dest, timeout=60)
                downloaded[filename] = dest
            except requests.HTTPError as e:
                print(f"  ⚠ FAILED {filename}: {e}")
                continue

            # Polite rate limit
            if count < total:
                time.sleep(rate_limit)

    print(f"\n✓ Downloaded {len(downloaded)}/{total} files to {cfg['paths']['data_raw']}/")
    return downloaded


def verify_raw_files(cfg: dict) -> pd.DataFrame:
    """List all raw CSVs with row counts and file sizes for quick verification.

    Returns a DataFrame summarizing what's in data/raw/.
    """
    raw_dir = Path(cfg["paths"]["data_raw"])
    records = []
    for f in sorted(raw_dir.glob("state*.csv")):
        # Quick row count without loading full DataFrame
        with open(f) as fh:
            row_count = sum(1 for _ in fh) - 1  # subtract header
        records.append({
            "filename": f.name,
            "rows": row_count,
            "size_kb": round(f.stat().st_size / 1024, 1),
        })
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Census ACS State-to-State Migration Flows — bulk download
# ---------------------------------------------------------------------------

def ingest_census_acs_migration(
    cfg: dict,
    years: list[int] | None = None,
    skip_existing: bool = True,
) -> dict[str, Path]:
    """Download Census ACS state-to-state migration Excel files.

    Reads the `census_acs_migration` source block from config.yaml and downloads
    all available year files to data/raw/.

    Args:
        cfg:            Loaded config dict.
        years:          Override list of years (e.g. [2022, 2023]).
                        If None, uses all years from config.
        skip_existing:  If True, skip files that already exist in data/raw/.

    Returns:
        Dict mapping filename → Path for all downloaded files.
    """
    source = cfg["sources"]["census_acs_migration"]
    base_url = source["base_url"]
    url_pattern = source["url_pattern"]
    year_entries = source["years"]
    rate_limit = cfg["settings"].get("rate_limit_seconds", 1.5)

    if years:
        year_entries = [e for e in year_entries if e["year"] in years]

    downloaded: dict[str, Path] = {}
    total = len(year_entries)

    for i, entry in enumerate(year_entries, 1):
        year = entry["year"]
        filename = entry["filename"]
        url = url_pattern.format(base_url=base_url, year=year, filename=filename)

        # Save with a consistent naming scheme
        local_filename = f"census_acs_migration_{year}.{'xlsx' if filename.endswith('.xlsx') else 'xls'}"
        dest = raw_path(cfg, local_filename)

        if skip_existing and dest.exists():
            print(f"  [{i}/{total}] skip (exists): {local_filename}")
            downloaded[local_filename] = dest
            continue

        print(f"  [{i}/{total}] downloading: {local_filename} ({year})")
        try:
            download_file(url, dest, timeout=60)
            downloaded[local_filename] = dest
        except requests.HTTPError as e:
            print(f"  ⚠ FAILED {local_filename}: {e}")
            continue

        if i < total:
            time.sleep(rate_limit)

    print(f"\n✓ Downloaded {len(downloaded)}/{total} Census ACS files to {cfg['paths']['data_raw']}/")
    return downloaded


def parse_census_acs_migration(filepath: Path, year: int) -> pd.DataFrame:
    """Parse a Census ACS state-to-state migration Excel file into long format.

    Handles two layouts:
      - Wide crosstab (2011–2023): rows = current residence, columns = previous residence
      - Long format (2024+): columns = current residence, previous residence, estimate, MOE

    Args:
        filepath:  Path to the downloaded .xls/.xlsx file.
        year:      The ACS year for labeling.

    Returns:
        DataFrame with columns: origin, destination, migrants, moe, year
    """
    engine = "openpyxl" if str(filepath).endswith(".xlsx") else "xlrd"

    # Read with no header to inspect structure
    df_raw = pd.read_excel(filepath, sheet_name=0, header=None, engine=engine)

    # Detect format: long format has "Residence 1 year ago" in header area
    is_long_format = False
    for idx in range(min(8, len(df_raw))):
        row_text = " ".join(str(v) for v in df_raw.iloc[idx] if pd.notna(v))
        if "Residence 1 year ago" in row_text:
            is_long_format = True
            break

    if is_long_format:
        return _parse_census_long_format(df_raw, year)
    else:
        return _parse_census_wide_format(df_raw, filepath, year)


def _parse_census_long_format(df_raw: pd.DataFrame, year: int) -> pd.DataFrame:
    """Parse the 2024+ long format: current residence, previous residence, estimate, MOE."""
    # Find header row (contains "Estimate")
    header_row = None
    for idx in range(min(10, len(df_raw))):
        row_vals = df_raw.iloc[idx].astype(str)
        if row_vals.str.contains("Estimate", case=False).any():
            header_row = idx
            break

    if header_row is None:
        raise ValueError("Could not find header row with 'Estimate' in long-format file")

    # Data starts on the row after header
    data_start = header_row + 1

    records = []
    for row_idx in range(data_start, len(df_raw)):
        destination = str(df_raw.iloc[row_idx, 0]).strip()  # Current residence
        origin = str(df_raw.iloc[row_idx, 1]).strip()       # Residence 1 year ago

        if destination in ("nan", "") or origin in ("nan", ""):
            continue
        if destination.startswith("Source:") or destination.startswith("Note"):
            break

        # Estimate is column 2, MOE is column 3
        est_val = df_raw.iloc[row_idx, 2]
        moe_val = df_raw.iloc[row_idx, 3] if len(df_raw.columns) > 3 else None

        # Skip non-numeric (X means suppressed)
        try:
            est = int(float(est_val)) if pd.notna(est_val) and str(est_val).strip() not in ("", "nan", "N", "-", "X") else None
        except (ValueError, TypeError):
            est = None

        try:
            moe = int(float(moe_val)) if pd.notna(moe_val) and str(moe_val).strip() not in ("", "nan", "N", "-", "X") else None
        except (ValueError, TypeError):
            moe = None

        if est is not None:
            # Clean footnote markers from names
            destination_clean = destination.rstrip("0123456789")
            origin_clean = origin.rstrip("0123456789")
            records.append({
                "origin": origin_clean,
                "destination": destination_clean,
                "migrants": est,
                "moe": moe,
                "year": year,
            })

    return pd.DataFrame(records)


def _parse_census_wide_format(df_raw: pd.DataFrame, filepath: Path, year: int) -> pd.DataFrame:
    """Parse the 2011–2023 wide crosstab format."""
    # Find the row with state names (look for "Alabama")
    state_header_row = None
    for idx in range(min(10, len(df_raw))):
        row_vals = df_raw.iloc[idx].astype(str)
        if row_vals.str.contains("Alabama", case=False).any():
            state_header_row = idx
            break

    if state_header_row is None:
        raise ValueError(f"Could not find state header row in {filepath}")

    state_names_row = df_raw.iloc[state_header_row]

    # Find the data start row (US total row)
    data_start_row = None
    for idx in range(state_header_row + 2, min(state_header_row + 10, len(df_raw))):
        val = str(df_raw.iloc[idx, 0]).strip()
        if val in ("United States", "United States2"):
            data_start_row = idx
            break

    if data_start_row is None:
        for idx in range(state_header_row + 2, min(state_header_row + 15, len(df_raw))):
            val = str(df_raw.iloc[idx, 0]).strip()
            if val in ("Alabama", "Alaska"):
                data_start_row = idx - 1
                break

    if data_start_row is None:
        raise ValueError(f"Could not find data start row in {filepath}")

    # Extract destination state names from the header row
    dest_states = []
    dest_col_indices = []

    for col_idx in range(1, len(state_names_row)):
        val = str(state_names_row.iloc[col_idx]).strip()
        if val != "nan" and val != "" and val not in ("Estimate", "MOE (±)"):
            dest_states.append(val)
            dest_col_indices.append(col_idx)

    # Read data rows
    records = []
    for row_idx in range(data_start_row, len(df_raw)):
        origin = str(df_raw.iloc[row_idx, 0]).strip()
        if origin == "nan" or origin == "" or origin.startswith("Source:") or origin.startswith("Note"):
            continue
        origin = origin.rstrip("0123456789")

        for dest_name, col_idx in zip(dest_states, dest_col_indices):
            est_val = df_raw.iloc[row_idx, col_idx]
            moe_val = df_raw.iloc[row_idx, col_idx + 1] if col_idx + 1 < len(df_raw.columns) else None

            try:
                est = int(float(est_val)) if pd.notna(est_val) and str(est_val).strip() not in ("", "nan", "N", "-") else None
            except (ValueError, TypeError):
                est = None

            try:
                moe = int(float(moe_val)) if pd.notna(moe_val) and str(moe_val).strip() not in ("", "nan", "N", "-") else None
            except (ValueError, TypeError):
                moe = None

            if est is not None:
                records.append({
                    "origin": origin,
                    "destination": dest_name.rstrip("0123456789"),
                    "migrants": est,
                    "moe": moe,
                    "year": year,
                })

    return pd.DataFrame(records)
