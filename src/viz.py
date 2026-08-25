"""Social media chart export helpers.

Produces publication-ready PNG images sized for common social platforms.
All charts are generated with matplotlib and exported via Pillow so you
have full pixel-level control with no browser dependency.

Supported presets:
  - instagram_square   : 1080×1080
  - instagram_portrait : 1080×1350
  - twitter_landscape  : 1600×900
  - twitter_square     : 1080×1080

Usage:
    from src.viz import bar_chart, line_chart, save_chart
    fig = bar_chart(df, x="state", y="rate", title="DUI Rate by State")
    save_chart(fig, cfg, "dui_rate_by_state", preset="instagram_square")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
from PIL import Image

# ---------------------------------------------------------------------------
# Platform presets (width px, height px, DPI)
# Matplotlib figsize is in inches; we derive it from px / dpi.
# ---------------------------------------------------------------------------

PRESETS: dict[str, tuple[int, int, int]] = {
    "instagram_square":   (1080, 1080, 150),
    "instagram_portrait": (1080, 1350, 150),
    "twitter_landscape":  (1600,  900, 150),
    "twitter_square":     (1080, 1080, 150),
}

# Default style — clean, minimal, no chartjunk
_STYLE = {
    "axes.spines.top":    False,
    "axes.spines.right":  False,
    "axes.grid":          True,
    "grid.alpha":         0.25,
    "axes.axisbelow":     True,
    "font.family":        "sans-serif",
}


def _fig_for_preset(preset: str) -> tuple[plt.Figure, plt.Axes]:
    """Create a (fig, ax) pair sized for the given platform preset."""
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset '{preset}'. Choose from: {list(PRESETS)}")
    w_px, h_px, dpi = PRESETS[preset]
    fig_w = w_px / dpi
    fig_h = h_px / dpi
    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    return fig, ax


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def bar_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "",
    subtitle: str = "",
    xlabel: str = "",
    ylabel: str = "",
    color: str = "#2563EB",
    preset: str = "instagram_square",
    sort: bool = True,
) -> plt.Figure:
    """Horizontal bar chart, sorted descending by default.

    Args:
        df:       DataFrame with at least the x and y columns.
        x:        Category column (will appear on the y-axis of a hbar).
        y:        Numeric column.
        title:    Bold headline text.
        subtitle: Smaller text below the title.
        color:    Bar fill color (hex or named).
        preset:   Platform preset key.
        sort:     Sort bars by value descending.
    """
    data = df[[x, y]].dropna().copy()
    if sort:
        data = data.sort_values(y, ascending=True)  # ascending for hbar

    fig, ax = _fig_for_preset(preset)
    with plt.rc_context(_STYLE):
        bars = ax.barh(data[x].astype(str), data[y], color=color)
        ax.bar_label(bars, fmt="{:,.0f}", padding=4, fontsize=9)
        ax.set_xlabel(ylabel or y)
        ax.set_ylabel(xlabel or x)
        _add_title_block(fig, ax, title, subtitle)
    return fig


def line_chart(
    df: pd.DataFrame,
    x: str,
    y: str | list[str],
    title: str = "",
    subtitle: str = "",
    xlabel: str = "",
    ylabel: str = "",
    colors: list[str] | None = None,
    preset: str = "twitter_landscape",
    markers: bool = True,
) -> plt.Figure:
    """Line chart supporting one or multiple y series.

    Args:
        y: Single column name, or list of column names for multi-line.
    """
    y_cols = [y] if isinstance(y, str) else y
    default_colors = ["#2563EB", "#DC2626", "#16A34A", "#D97706", "#7C3AED"]
    colors = colors or default_colors[: len(y_cols)]

    fig, ax = _fig_for_preset(preset)
    with plt.rc_context(_STYLE):
        for col, clr in zip(y_cols, colors):
            ax.plot(
                df[x],
                df[col],
                color=clr,
                linewidth=2.5,
                marker="o" if markers else None,
                markersize=5,
                label=col,
            )
        if len(y_cols) > 1:
            ax.legend(framealpha=0.8)
        ax.set_xlabel(xlabel or x)
        ax.set_ylabel(ylabel or (y_cols[0] if len(y_cols) == 1 else ""))
        _add_title_block(fig, ax, title, subtitle)
    return fig


def ranked_bar_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "",
    subtitle: str = "",
    top_n: int = 10,
    color: str = "#2563EB",
    highlight_color: str = "#DC2626",
    highlight_values: list[str] | None = None,
    preset: str = "instagram_portrait",
) -> plt.Figure:
    """Top-N horizontal bar chart with optional highlighted bars.

    Great for 'Top 10 states by X' social posts.

    Args:
        top_n:             Keep only the top N rows by y value.
        highlight_values:  x values to color differently (e.g., ["California"]).
    """
    data = df[[x, y]].dropna().nlargest(top_n, y).sort_values(y, ascending=True)
    bar_colors = [
        highlight_color if str(v) in (highlight_values or []) else color
        for v in data[x]
    ]

    fig, ax = _fig_for_preset(preset)
    with plt.rc_context(_STYLE):
        bars = ax.barh(data[x].astype(str), data[y], color=bar_colors)
        ax.bar_label(bars, fmt="{:,.0f}", padding=4, fontsize=9)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
        _add_title_block(fig, ax, title, subtitle)
    return fig


# ---------------------------------------------------------------------------
# Title block helper
# ---------------------------------------------------------------------------

def _add_title_block(
    fig: plt.Figure,
    ax: plt.Axes,
    title: str,
    subtitle: str,
) -> None:
    """Add a title and optional subtitle with consistent styling."""
    if title:
        ax.set_title(title, fontsize=14, fontweight="bold", pad=12, loc="left")
    if subtitle:
        fig.text(
            0.125, 0.96, subtitle,
            fontsize=9, color="#6B7280",
            ha="left", va="top",
            transform=fig.transFigure,
        )
    fig.tight_layout(rect=[0, 0, 1, 0.94] if subtitle else [0, 0, 1, 1])


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_chart(
    fig: plt.Figure,
    cfg: dict[str, Any],
    filename: str,
    preset: str = "instagram_square",
    add_watermark: str = "",
) -> Path:
    """Save a matplotlib figure to outputs/ as a PNG.

    Args:
        fig:           Figure returned by any chart builder above.
        cfg:           Loaded config dict.
        filename:      Output filename without extension.
        preset:        Used to verify final pixel dimensions via Pillow.
        add_watermark: Optional short text drawn in the bottom-right corner.
                       Useful for branding without exposing your identity
                       (e.g. "@unwelcomedata").
    """
    out_dir = Path(cfg["paths"]["outputs"])
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{filename}.png"

    if add_watermark:
        _add_watermark(fig, add_watermark)

    w_px, h_px, dpi = PRESETS.get(preset, (1080, 1080, 150))
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    # Verify and optionally resize to exact pixel dimensions
    img = Image.open(out_path)
    if img.size != (w_px, h_px):
        img = img.resize((w_px, h_px), Image.LANCZOS)
        img.save(out_path, format="PNG", optimize=True)

    print(f"Saved chart → {out_path}  ({w_px}×{h_px} px, preset={preset})")
    return out_path


def _add_watermark(fig: plt.Figure, text: str) -> None:
    """Draw a faint watermark in the lower-right corner of the figure."""
    fig.text(
        0.98, 0.02, text,
        fontsize=8, color="#9CA3AF", alpha=0.7,
        ha="right", va="bottom",
        transform=fig.transFigure,
    )
