"""Social-ready chart export — Pillow backend.

This module is a thin compatibility layer. The actual rendering is handled
by the shared chart_factory + chart_templates (Pillow) pipeline at the
workspace level (../shared/).

The primary workflow:
    from chart_factory import render_chart

    render_chart({
        "type": "side_by_side_bars",  # or "stacked_bars", "single_ranked_bars"
        "db": conn,                    # DuckDB connection
        "preset": "twitter_landscape",
        "table_left": "chart_...",
        "table_right": "chart_...",
        "title": "Chart Title",
        "subtitle": "Unit or scope",
        "source": "Source with year",
        "filename": "01_my_chart",
    })

Chart types available (see shared/chart_templates.py):
    - side_by_side_bars: Two horizontal bar panels side by side
    - stacked_bars: Stacked horizontal bars with segments
    - single_ranked_bars: Single panel of ranked horizontal bars

Features:
    - Bars aligned across panels (forced_bars_y_start)
    - Two-line labels for narrow segments (name / percentage)
    - Detail bars below main chart area
    - Inner segments with dividers (e.g., gestation breakdown)
    - All charts include @unwelcomedata watermark

Platform presets:
    instagram_portrait : 1080x1350
    twitter_landscape  : 1600x900
    instagram_square   : 1080x1080

If you need standalone save_social() (e.g., for a manually composed PIL Image):
    from src.viz_social import save_social
    save_social(img, cfg, 'filename', preset='twitter_landscape')
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PIL import Image

# Import shared brand library from workspace root
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))
from viz import BRAND, PRESETS  # noqa: E402


# ---------------------------------------------------------------------------
# Save to PNG (standalone — normally render_chart() handles this)
# ---------------------------------------------------------------------------

def save_social(
    img: Image.Image,
    cfg: dict[str, Any],
    filename: str,
    preset: str = "twitter_landscape",
) -> Path:
    """Save a PIL Image to the social outputs directory.

    In the normal workflow, render_chart() handles export internally.
    Use this only if you're composing a PIL Image manually outside the
    chart_factory pipeline.

    Args:
        img:       PIL Image object (RGB).
        cfg:       Project config dict (needs paths.outputs_social or paths.outputs).
        filename:  Output filename without extension.
        preset:    Platform preset for target dimensions.

    Returns:
        Path to saved PNG.
    """
    out_dir = Path(cfg["paths"].get("outputs_social", cfg["paths"]["outputs"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{filename}.png"

    w_px, h_px, _ = PRESETS[preset]

    # Resize if needed
    if img.size != (w_px, h_px):
        img = img.resize((w_px, h_px), Image.LANCZOS)

    img.save(out_path, format="PNG", optimize=True)
    print(f"Saved social chart -> {out_path}  ({w_px}x{h_px} px, preset={preset})")
    return out_path
