"""
Phase-2 cleaning transforms for the Austria energy & climate project.

Each public ``build_*`` function turns one raw source file into one typed DuckDB
table (two, for the resampled series), idempotently via ``CREATE OR REPLACE`` — so
the identical pipeline runs from notebook 02 or from ``build_database.py``. The
connection and source paths are passed in: this module owns the transforms, not
where the data lives or how the database is opened.

Style mirrors ``data_loader.py``: type hints, docstrings, ``logging``, ``Path``.
All timestamps are stored as UTC ``TIMESTAMPTZ``; conversion to ``Europe/Vienna``
happens only at the display layer in the notebooks.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

import duckdb
import pandas as pd

log = logging.getLogger(__name__)


def _rowcount(con: duckdb.DuckDBPyConnection, table: str) -> int:
    """Row count of an internal table as a plain int (``table`` is always a literal)."""
    result = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    assert result is not None  # COUNT(*) always returns exactly one row
    return int(result[0])


@contextmanager
def _registered(con: duckdb.DuckDBPyConnection, name: str, df: pd.DataFrame):
    """Register ``df`` as a temp view for the block, then drop it — so intermediate
    DataFrames never linger in the catalog (or show up in ``SHOW TABLES``)."""
    con.register(name, df)
    try:
        yield
    finally:
        con.unregister(name)


# ── pure transform (no DB; unit-testable on its own) ──────────────────────────────
def melt_generation(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Reshape the wide ENTSO-E generation feed to long format.

    The raw frame has a two-level column header (``fuel_type`` × the ENTSO-E flow
    label ``{"Actual Aggregated", "Actual Consumption"}``) and a UTC ``DatetimeIndex``.
    Every (fuel_type, flow) column becomes one row; the second header level is mapped
    onto ``flow`` = ``"generation"`` / ``"consumption"``. Blank cells are dropped, and
    an unrecognised flow label raises rather than passing through as NULL.

    Parameters
    ----------
    raw : pd.DataFrame
        Wide frame from ``entsoe_generation_AT.csv`` (``header=[0, 1]``), UTC index.

    Returns
    -------
    pd.DataFrame
        Long frame with columns ``[ts_utc, fuel_type, flow, mw]``.

    Raises
    ------
    ValueError
        If the feed contains a flow label not present in the mapping.
    """
    raw = raw.copy()  # don't mutate the caller's index/column metadata
    raw.index.name = "ts_utc"
    raw.columns.names = ["fuel_type", "_flow_raw"]  # so stack() yields tidy names

    long = (
        raw
        .stack(level=["fuel_type", "_flow_raw"], future_stack=True)
        .rename("mw")
        .reset_index()
        .dropna(subset=["mw"])  # ENTSO-E didn't report these
    )

    flow_map = {"Actual Aggregated": "generation", "Actual Consumption": "consumption"}
    long["flow"] = long["_flow_raw"].map(flow_map)

    unmapped = long["flow"].isna()
    if unmapped.any():
        raise ValueError(
            f"Unknown ENTSO-E flow types: {long.loc[unmapped, '_flow_raw'].unique().tolist()}"
        )

    return long[["ts_utc", "fuel_type", "flow", "mw"]]


# ── table builders: raw file → typed DuckDB table(s), idempotent ──────────────────
def build_generation(con: duckdb.DuckDBPyConnection, csv_path: Path) -> int:
    """
    Build ``generation_15min`` (long staging) then resample to hourly ``generation``.

    MW is instantaneous power, so the hourly step averages rather than sums, and keeps
    only real flows: all generation, plus the one fuel that genuinely draws from the
    grid (Hydro Pumped Storage). ``n_quarters`` records the 15-min rows per hour
    (4 when the source is complete).

    Parameters
    ----------
    con : duckdb.DuckDBPyConnection
        Open read-write connection.
    csv_path : Path
        Path to ``entsoe_generation_AT.csv``.

    Returns
    -------
    int
        Row count of the hourly ``generation`` table.
    """
    raw = pd.read_csv(csv_path, header=[0, 1], index_col=0)
    raw.index = pd.to_datetime(raw.index, utc=True)  # mixed DST offsets → UTC

    gen_long = melt_generation(raw)

    con.execute("""
        CREATE OR REPLACE TABLE generation_15min (
            ts_utc      TIMESTAMPTZ NOT NULL,
            fuel_type   VARCHAR     NOT NULL,
            flow        VARCHAR     NOT NULL,      -- 'generation' or 'consumption'
            mw          DOUBLE,
            PRIMARY KEY (ts_utc, fuel_type, flow)
        )
    """)
    with _registered(con, "gen_long", gen_long):
        con.execute("INSERT INTO generation_15min BY NAME SELECT * FROM gen_long")

    con.execute("""
        CREATE OR REPLACE TABLE generation AS
        SELECT
            time_bucket(INTERVAL 1 HOUR, ts_utc) AS ts_utc,
            fuel_type,
            flow,
            AVG(mw)  AS mw,            -- instantaneous power → average, don't sum
            COUNT(*) AS n_quarters     -- expect 4 per hour; <4 means a source gap
        FROM generation_15min
        WHERE flow = 'generation'                                      -- always keep
           OR (flow = 'consumption' AND fuel_type = 'Hydro Pumped Storage')
                                                                       -- only pumped storage consumes
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
    """)

    n_stg, n = _rowcount(con, "generation_15min"), _rowcount(con, "generation")
    log.info("generation_15min: %d rows  →  generation (hourly): %d rows", n_stg, n)
    return n


def build_demand(con: duckdb.DuckDBPyConnection, csv_path: Path) -> int:
    """
    Build ``demand_15min`` then resample to hourly ``demand``.

    Parameters
    ----------
    con : duckdb.DuckDBPyConnection
        Open read-write connection.
    csv_path : Path
        Path to ``entsoe_load_AT.csv`` (single demand column).

    Returns
    -------
    int
        Row count of the hourly ``demand`` table.
    """
    raw = pd.read_csv(csv_path, index_col=0)
    raw.index = pd.to_datetime(raw.index, utc=True)
    demand = raw.rename_axis("ts_utc").reset_index()
    demand.columns = ["ts_utc", "demand_mw"]

    con.execute("""
        CREATE OR REPLACE TABLE demand_15min (
            ts_utc     TIMESTAMPTZ PRIMARY KEY,
            demand_mw  DOUBLE
        )
    """)
    with _registered(con, "demand_long", demand):
        con.execute("INSERT INTO demand_15min BY NAME SELECT * FROM demand_long")

    con.execute("""
        CREATE OR REPLACE TABLE demand AS
        SELECT
            time_bucket(INTERVAL 1 HOUR, ts_utc) AS ts_utc,
            AVG(demand_mw) AS demand_mw,
            COUNT(*)       AS n_quarters
        FROM demand_15min
        GROUP BY 1
        ORDER BY 1
    """)

    n_stg, n = _rowcount(con, "demand_15min"), _rowcount(con, "demand")
    log.info("demand_15min: %d rows  →  demand (hourly): %d rows", n_stg, n)
    return n


def build_prices(con: duckdb.DuckDBPyConnection, csv_path: Path) -> int:
    """
    Build ``prices`` (native hourly day-ahead). Timestamps carry offsets → parsed to UTC.

    Returns
    -------
    int
        Row count of ``prices``.
    """
    raw = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    raw.index = pd.to_datetime(raw.index, utc=True)
    prices = raw.rename_axis("ts_utc").reset_index()
    prices.columns = ["ts_utc", "price_eur_mwh"]

    con.execute("""
        CREATE OR REPLACE TABLE prices (
            ts_utc         TIMESTAMPTZ PRIMARY KEY,
            price_eur_mwh  DOUBLE
        )
    """)
    with _registered(con, "prices_df", prices):
        con.execute("INSERT INTO prices BY NAME SELECT * FROM prices_df")
    n = _rowcount(con, "prices")
    log.info("prices: %d rows", n)
    return n


def build_weather(con: duckdb.DuckDBPyConnection, csv_path: Path) -> int:
    """
    Build ``weather`` (native hourly). Naive timestamps are tagged UTC; columns renamed.

    Returns
    -------
    int
        Row count of ``weather``.
    """
    raw = pd.read_csv(csv_path, index_col="timestamp", parse_dates=True)
    raw.index = raw.index.tz_localize("UTC")  # naive label → UTC, no shift
    weather = raw.rename(columns={
        "temperature_2m":      "temperature_c",
        "shortwave_radiation": "solar_wm2",
        "windspeed_10m":       "wind_kmh",
        "precipitation":       "precip_mm",
        "cloudcover":          "cloudcover_pct",
    }).rename_axis("ts_utc").reset_index()

    con.execute("""
        CREATE OR REPLACE TABLE weather (
            ts_utc          TIMESTAMPTZ PRIMARY KEY,
            temperature_c   DOUBLE,
            solar_wm2       DOUBLE,
            wind_kmh        DOUBLE,
            precip_mm       DOUBLE,
            cloudcover_pct  DOUBLE
        )
    """)
    with _registered(con, "weather_df", weather):
        con.execute("INSERT INTO weather BY NAME SELECT * FROM weather_df")
    n = _rowcount(con, "weather")
    log.info("weather: %d rows", n)
    return n


def build_owid(con: duckdb.DuckDBPyConnection, csv_path: Path) -> int:
    """
    Build ``owid_energy_at`` (annual) via CTAS straight from the CSV.

    Returns
    -------
    int
        Row count of ``owid_energy_at``.
    """
    # csv_path is a trusted local constant, so f-string interpolation is fine here.
    con.execute(f"""
        CREATE OR REPLACE TABLE owid_energy_at AS
        SELECT * FROM read_csv_auto('{csv_path}', header = true)
    """)
    n = _rowcount(con, "owid_energy_at")
    log.info("owid_energy_at: %d rows", n)
    return n


def build_ghg(con: duckdb.DuckDBPyConnection, csv_path: Path) -> int:
    """
    Build ``ghg_emissions`` from the Eurostat env_air_gge extract.

    Keeps Mt CO2-eq rows (``unit = 'MIO_T'``) for the two national totals and the six
    top-level CRF sectors, then UNPIVOTs the year columns to long (one row per
    sector × year) — UNPIVOT is DuckDB's wide→long, the SQL twin of pandas ``.melt()``.

    Returns
    -------
    int
        Row count of ``ghg_emissions``.
    """
    # csv_path is a trusted local constant; the doubled backslash is the literal
    # column name 'geo\TIME_PERIOD' that Eurostat ships.
    con.execute(f"""
        CREATE OR REPLACE TABLE ghg_emissions AS
        WITH raw AS (
            SELECT * FROM read_csv_auto('{csv_path}', header = true)
        ),
        filtered AS (
            SELECT * EXCLUDE ("geo\\TIME_PERIOD")
            FROM raw
            WHERE unit = 'MIO_T'
              AND src_crf IN (
                  'TOTX4_MEMO',   -- Total, excl. LULUCF  -> headline emissions
                  'TOTXMEMO',     -- Total, incl. LULUCF  -> net (with land sink)
                  'CRF1','CRF2','CRF3','CRF4','CRF5','CRF6'
              )
        ),
        long AS (
            UNPIVOT filtered
            ON COLUMNS(* EXCLUDE (freq, unit, airpol, src_crf))
            INTO NAME year_str VALUE mt_co2e
        )
        SELECT
            CAST(year_str AS INTEGER) AS year,
            src_crf                   AS sector_code,
            CASE src_crf
                WHEN 'TOTX4_MEMO' THEN 'Total (excl. LULUCF)'
                WHEN 'TOTXMEMO'   THEN 'Total (incl. LULUCF)'
                WHEN 'CRF1' THEN 'Energy'
                WHEN 'CRF2' THEN 'Industrial processes'
                WHEN 'CRF3' THEN 'Agriculture'
                WHEN 'CRF4' THEN 'LULUCF'
                WHEN 'CRF5' THEN 'Waste'
                WHEN 'CRF6' THEN 'Other'
            END                       AS sector,
            mt_co2e
        FROM long
        WHERE mt_co2e IS NOT NULL
        ORDER BY sector_code, year
    """)
    n = _rowcount(con, "ghg_emissions")
    log.info("ghg_emissions: %d rows", n)
    return n


def build_esr(con: duckdb.DuckDBPyConnection, xlsx_path: Path) -> int:
    """
    Build ``esr_emissions`` from the EEA Effort-Sharing workbook.

    Reads the GHG_ESD sheet, keeps Austria, asserts the unit is constant (so a future
    format change fails loudly), and stores the non-ETS series with its accounting
    regime (ESD/AR4 vs ESR/AR5).

    Returns
    -------
    int
        Row count of ``esr_emissions``.
    """
    df = (
        pd.read_excel(xlsx_path, sheet_name="GHG_ESD")
        .rename(columns={
            "Country":      "country",
            "Year":         "year",
            "ValueNumeric": "mt_co2e",
            "ESD_ESR":      "regime",
            "Unit":         "unit",
            "Data_source":  "data_source",
        })
    )
    df = df[df["country"] == "Austria"].copy()

    assert (df["unit"] == "MtCO2 eq").all(), df["unit"].unique()
    df["year"] = df["year"].astype(int)
    df["mt_co2e"] = df["mt_co2e"].astype(float)
    df = df[["year", "regime", "mt_co2e", "data_source"]].sort_values("year")

    con.execute("""
        CREATE OR REPLACE TABLE esr_emissions (
            year         SMALLINT PRIMARY KEY,
            regime       VARCHAR,     -- 'ESD' (AR4) or 'ESR' (AR5)
            mt_co2e      DOUBLE,      -- non-ETS Effort Sharing emissions, Mt CO2-eq
            data_source  VARCHAR
        )
    """)
    with _registered(con, "esr_df", df):
        con.execute("INSERT INTO esr_emissions BY NAME SELECT * FROM esr_df")
    n = _rowcount(con, "esr_emissions")
    log.info("esr_emissions: %d rows", n)
    return n