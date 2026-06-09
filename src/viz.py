"""
viz.py
------
Shared plotting helpers and house style for the Austria Energy & Climate project.

Importing does nothing on its own; call set_house_style() once near the top of a
notebook to apply consistent matplotlib defaults, then use PALETTE in plots.

Usage:
    from src.viz import set_house_style, PALETTE
    set_house_style()
"""

import matplotlib as mpl

# ── house palette ──────────────────────────────────────────────────────────────
# Semantic colours reused across the project, carried over from the sanity-check
# plots in 01_data_collection so the whole portfolio reads as one piece.
PALETTE: dict[str, str] = {
    "temp":   "#E8593C",   # warm red   — temperature
    "solar":  "#EF9F27",   # amber      — solar / radiation
    "wind":   "#1D9E75",   # teal       — wind
    "hydro":  "#378ADD",   # blue       — hydro / water
    "price":  "#7F77DD",   # purple     — prices
    "demand": "#5F5E5A",   # grey       — demand / load
    "accent": "#D85A30",   # coral      — highlight (e.g. crisis year)
    "muted":  "#B4B2A9",   # light grey — secondary / context
}


def set_house_style() -> None:
    """Apply project-wide matplotlib defaults. Call once per notebook."""
    mpl.rcParams.update({
        "figure.figsize":    (12, 5),
        "figure.dpi":        110,
        "savefig.dpi":       120,
        "savefig.bbox":      "tight",
        "font.size":         11,
        "axes.titlesize":    13,
        "axes.titleweight":  "medium",
        "axes.grid":         True,
        "grid.alpha":        0.25,
        "grid.linewidth":    0.6,
        "axes.spines.top":   False,   # replaces the manual despine in notebook 01
        "axes.spines.right": False,
        "axes.axisbelow":    True,    # gridlines behind the data
        "legend.frameon":    False,
    })

def line_profile(ax, x, y, *, color, label=None):
    """Plot one line-with-markers series on `ax` in the project profile style.
    Call once per series; set title / labels / legend on the axis yourself."""
    ax.plot(x, y, marker="o", ms=4, color=color, label=label)
    return ax