"""
build_database.py
-----------------
Headless one-command rebuild of ``data/processed/austria_energy.duckdb``.

Collapses notebooks 01 (fetch) + 02 (clean + load) into a single script:

    python build_database.py                # full: fetch → clean → load (needs API key)
    python build_database.py --skip-fetch   # rebuild tables from raw files already on disk
    python build_database.py --fresh        # delete the .duckdb first, then rebuild

This is glue over existing code — it does not reimplement fetching or cleaning.
It calls ``DataLoader.fetch_all`` (data_loader.py) and the ``clean.build_*``
transforms (clean.py), both of which are idempotent (``CREATE OR REPLACE``), so
the database rebuilds cleanly on every run.

Style mirrors ``data_loader.py`` / ``clean.py``: type hints, docstrings, the
module ``logging`` setup, ``pathlib.Path``, paths resolved from the repo root.
"""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Callable
from pathlib import Path

import duckdb
from dotenv import load_dotenv

# data_loader configures the root logger (basicConfig) on import and exports the
# raw/external directory constants — reuse both rather than re-deriving them.
from src import clean
from src.data_loader import EXTERNAL, RAW, DataLoader

log = logging.getLogger(__name__)

# This script lives at the repo root, so its own directory *is* ROOT — no need to
# walk up a level the way src/*.py does (``parent.parent``).
ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "processed" / "austria_energy.duckdb"

# Single source of truth for the pipeline wiring, in build order. Each entry maps a
# fetch_all() key → its clean.build_* transform → the on-disk path used by
# --skip-fetch (when fetch_all is not called). Two wrinkles encoded here:
#   • key "load" maps to build_demand (table "demand"), not a build_load.
#   • the skip-fetch basenames mirror the filenames data_loader.py writes (they are
#     hardcoded there with the country code, not exported); safe for this AT-only
#     project. In full mode these paths are ignored — fetch_all returns them instead.
Builder = Callable[[duckdb.DuckDBPyConnection, Path], int]
BUILD_SPEC: list[tuple[str, Builder, Path]] = [
    ("owid",       clean.build_owid,       RAW / "owid_energy_AUT.csv"),
    ("weather",    clean.build_weather,    RAW / "weather_vienna.csv"),
    ("ghg",        clean.build_ghg,        RAW / "eurostat_ghg_AT.csv"),
    ("esr",        clean.build_esr,        EXTERNAL / "eea_esr_effort_sharing.xlsx"),
    ("generation", clean.build_generation, RAW / "entsoe_generation_AT.csv"),
    ("load",       clean.build_demand,     RAW / "entsoe_load_AT.csv"),
    ("prices",     clean.build_prices,     RAW / "entsoe_prices_AT.csv"),
]


def resolve_paths_from_disk() -> dict[str, Path]:
    """
    Locate each source file on disk for ``--skip-fetch`` (no network, no API key).

    Mirrors the ``dict[str, Path]`` that ``DataLoader.fetch_all`` would return, but
    built from the committed layout instead of by fetching. Missing files are simply
    omitted and warned about — the ENTSO-E sources legitimately never exist without an
    API key, so an absent file is a skipped table, not an error.

    Returns
    -------
    dict[str, Path]
        Mapping of source key → existing file path (only keys whose file is present).
    """
    paths: dict[str, Path] = {}
    for key, _builder, path in BUILD_SPEC:
        if path.exists():
            paths[key] = path
        else:
            log.warning("  %-14s → file not found, skipping: %s", key, path)
    return paths


def build_all(
    con: duckdb.DuckDBPyConnection, paths: dict[str, Path]
) -> dict[str, int]:
    """
    Run every ``clean.build_*`` transform whose source path is present.

    Parameters
    ----------
    con : duckdb.DuckDBPyConnection
        Open read-write connection to the target database.
    paths : dict[str, Path]
        Source key → file path, from ``fetch_all`` (full) or ``resolve_paths_from_disk``
        (skip-fetch). Keys absent from the mapping are skipped — this is how the three
        ENTSO-E sources drop out gracefully when there is no API key.

    Returns
    -------
    dict[str, int]
        Source key → row count of the table it built.
    """
    counts: dict[str, int] = {}
    for key, builder, _path in BUILD_SPEC:
        path = paths.get(key)
        if path is None:
            continue  # not fetched / not on disk — already warned upstream
        counts[key] = builder(con, path)
    return counts


def rebuild(skip_fetch: bool, fresh: bool) -> dict[str, int]:
    """
    Produce the source paths (fetch or from disk), then build every table.

    Parameters
    ----------
    skip_fetch : bool
        If True, rebuild from raw files already on disk (no network, no API key).
        If False, run the full ``DataLoader.fetch_all`` first.
    fresh : bool
        If True, delete the existing ``.duckdb`` (and its ``-wal``) before building,
        for a guaranteed-clean artifact rather than relying on ``CREATE OR REPLACE``.

    Returns
    -------
    dict[str, int]
        Source key → row count of the table it built.
    """
    # 1. resolve the source paths
    if skip_fetch:
        log.info("Skip-fetch: rebuilding from raw files on disk (no API key needed).")
        paths = resolve_paths_from_disk()
    else:
        # argument omitted → DataLoader falls back to the ENTSOE_API_KEY env var,
        # and fetch_all skips ENTSO-E gracefully if the key is still missing.
        dl = DataLoader(entsoe_api_key=os.getenv("ENTSOE_API_KEY"))
        paths = dl.fetch_all()

    if not paths:
        raise RuntimeError(
            "No source files available to build from. "
            "Run a full fetch first, or check data/raw and data/external."
        )

    # 2. optionally start from a clean file
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if fresh:
        for p in (DB_PATH, DB_PATH.with_name(DB_PATH.name + ".wal")):
            if p.exists():
                p.unlink()
                log.info("Removed existing %s", p.name)

    # 3. build every table, then close
    con = duckdb.connect(str(DB_PATH))
    try:
        counts = build_all(con, paths)
    finally:
        con.close()
    return counts


def main() -> None:
    """Parse flags, rebuild the database, and print a per-table summary."""
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild data/processed/austria_energy.duckdb from the project's data "
            "sources (fetch → clean → load)."
        )
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Rebuild tables from raw files already on disk (no network, no API key).",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Delete the existing .duckdb before rebuilding (guaranteed-clean artifact).",
    )
    args = parser.parse_args()

    # data_loader.py already called basicConfig on import; this matches its format and
    # is a no-op if the root logger is configured, keeping the script self-contained.
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        level=logging.INFO,
    )

    load_dotenv()  # make ENTSOE_API_KEY from .env visible via os.getenv

    counts = rebuild(skip_fetch=args.skip_fetch, fresh=args.fresh)

    total_rows = sum(counts.values())
    log.info("Database rebuilt → %s", DB_PATH)
    log.info("Built %d source table(s), %d rows total:", len(counts), total_rows)
    for key, _builder, _path in BUILD_SPEC:
        if key in counts:
            log.info("  %-14s %10d rows", key, counts[key])


if __name__ == "__main__":
    main()
