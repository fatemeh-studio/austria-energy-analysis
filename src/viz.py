"""
viz.py
------
Shared plotting helpers and house style for the Austria Energy & Climate project.

Importing does nothing on its own; call set_house_style() once near the top of a
notebook to apply consistent matplotlib defaults, then use PALETTE in plots.

Usage:
    from src.viz import set_house_style, PALETTE, save_headline_fig, save_qa_fig

    set_house_style()                                   # once, top of the notebook
    # ... build `fig` using PALETTE for colours ...
    save_headline_fig(fig, "rq1_energy_mix")            # → figures/headline/
    save_qa_fig(fig, "missingness", "02_cleaning_eda")  # → figures/qa/02_cleaning_eda/
"""

from pathlib import Path

import matplotlib as mpl
from matplotlib.figure import Figure

# paths
# anchor on the repo root via this file's location, not the caller's cwd — so a
# notebook saves to the same figures/ whether it's run from notebooks/ or the root.
ROOT = Path(__file__).resolve().parent.parent
FIGURES = ROOT / "figures"
HEADLINE_DIR = FIGURES / "headline"  # polished, committed, embedded in the README
QA_DIR = FIGURES / "qa"  # diagnostic / sanity-check plots (EDA, notebook 01)

# house palette
# semantic colours reused across the project, carried over from the sanity-check
# plots in 01_data_collection so the whole portfolio reads as one piece.
PALETTE: dict[str, str] = {
    "temp": "#E8593C",  # warm red — temperature
    "solar": "#EF9F27",  # amber — solar / radiation
    "wind": "#1D9E75",  # teal — wind
    "hydro": "#378ADD",  # blue — hydro / water
    "price": "#7F77DD",  # purple — prices
    "demand": "#5F5E5A",  # grey — demand / load
    "accent": "#D85A30",  # coral — highlight (e.g. crisis year)
    "muted": "#B4B2A9",  # light grey — secondary / context
}


def set_house_style() -> None:
    """Apply project-wide matplotlib defaults. Call once per notebook."""
    mpl.rcParams.update({
        "figure.figsize": (12, 5),
        "figure.dpi": 110,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.titleweight": "normal",
        "axes.grid": True,
        "grid.alpha": 0.25,
        "grid.linewidth": 0.6,
        "axes.spines.top": False,  # replaces the manual despine in notebook 01
        "axes.spines.right": False,
        "axes.axisbelow": True,  # gridlines behind the data
        "legend.frameon": False,
    })


def line_profile(ax, x, y, *, color, label=None):
    """Plot one line-with-markers series on `ax` in the project profile style.
    Call once per series; set title / labels / legend on the axis yourself."""
    ax.plot(x, y, marker="o", ms=4, color=color, label=label)
    return ax


# figure saving
def _save_fig(fig: Figure, name: str, out_dir: Path) -> Path:
    """
    Write ``fig`` as ``<name>.png`` into ``out_dir`` (created if missing).

    The shared core behind save_headline_fig() and save_qa_fig(): the path-build,
    mkdir, and save live here in exactly one place, so the two public helpers differ
    only in their destination. dpi and bbox are inherited from set_house_style()'s
    rcParams (set in one place, so they can't drift). print (not logging) matches the
    notebooks' interactive idiom — these helpers only ever run from a notebook cell,
    where logging is typically unconfigured and silent.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure to write.
    name : str
        Filename stem, no extension — e.g. "rq1_energy_mix" → <out_dir>/rq1_energy_mix.png.
    out_dir : Path
        Destination directory: HEADLINE_DIR, QA_DIR, or a QA_DIR subfolder.

    Returns
    -------
    Path
        The path written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{name}.png"
    fig.savefig(out)  # dpi + bbox from set_house_style()
    print(f"saved → {out.relative_to(ROOT)}")
    return out


def save_headline_fig(fig: Figure, name: str) -> Path:
    """Save a polished, committed headline figure (one per RQ) → figures/headline/.

    These are the README-embedded figures — e.g.
    save_headline_fig(fig, "rq1_energy_mix") → figures/headline/rq1_energy_mix.png."""
    return _save_fig(fig, name, HEADLINE_DIR)


def save_qa_fig(fig: Figure, name: str, notebook: str = "") -> Path:
    """Save a diagnostic QA / EDA figure → figures/qa/[notebook]/.

    Sanity-check plots (distributions, missingness, residuals) that support the work
    but aren't the headline story. Pass ``notebook`` (e.g. "02_cleaning_eda") to group
    a notebook's QA figures in their own subfolder — recommended, since EDA alone
    produces many; omit it to save flat in figures/qa/. Bind it once per notebook with
    functools.partial to avoid repeating it:

        save_qa = partial(save_qa_fig, notebook="02_cleaning_eda")
        save_qa(fig, "missingness_heatmap")   # → figures/qa/02_cleaning_eda/missingness_heatmap.png
    """
    out_dir = QA_DIR / notebook if notebook else QA_DIR
    return _save_fig(fig, name, out_dir)
