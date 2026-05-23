"""
data_loader.py
--------------
Fetchers for all three data sources in the Austria Energy & Climate project.

Sources:
  1. ENTSO-E Transparency Platform  — hourly generation, load, prices (AT)
  2. Open-Meteo / ERA5              — hourly weather (Vienna by default)
  3. Our World in Data              — annual energy & CO2 time series

Usage:
  from src.data_loader import DataLoader
  dl = DataLoader(entsoe_api_key="YOUR_KEY")
  dl.fetch_all(start="2019-01-01", end="2024-12-31")
"""


import os
import time
import logging
from pathlib import Path

import pandas as pd
import requests

# ── optional: entsoe-py (only needed for ENTSO-E fetches) ──────────────────────
try:
    from entsoe.entsoe import EntsoePandasClient
    ENTSOE_AVAILABLE = True
except ImportError:
    ENTSOE_AVAILABLE = False  # pyright: ignore[reportConstantRedefinition]

# ── logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ── paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
EXTERNAL = ROOT / "data" / "external"
RAW.mkdir(parents=True, exist_ok=True)
EXTERNAL.mkdir(parents=True, exist_ok=True)


class DataLoader:
    """
    Central data-fetching class for the Austria Energy & Climate project.

    Parameters
    ----------
    entsoe_api_key : str, optional
        ENTSO-E Web API Security Token.  If omitted, ENTSO-E fetches are skipped.
        Can also be set via the ENTSOE_API_KEY environment variable.
    country : str
        ENTSO-E country code.  Default: "AT" (Austria).
    """

    OWID_URL = (
        "https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv"
    )

    def __init__(self, entsoe_api_key: str | None = None, country: str = "AT"):
        self.country: str = country

        # resolve API key: argument > env var
        self._api_key: str | None = entsoe_api_key or os.getenv("ENTSOE_API_KEY")

        if self._api_key and ENTSOE_AVAILABLE:
            self._entsoe_client: EntsoePandasClient | None = EntsoePandasClient(api_key=self._api_key)
            log.info("ENTSO-E client initialised.")
        else:
            self._entsoe_client = None
            if not self._api_key:
                log.warning(
                    "No ENTSO-E API key found.  "
                    "Set ENTSOE_API_KEY in .env or pass entsoe_api_key=... "
                    "ENTSO-E fetches will be skipped."
                )
            if not ENTSOE_AVAILABLE:
                log.warning("entsoe-py not installed.  Run: pip install entsoe-py")

    # ── public interface ───────────────────────────────────────────────────────

    def fetch_all(self, start: str = "2019-01-01", end: str = "2024-12-31") -> dict[str, Path]:
        """
        Run all fetchers.  Returns a dict mapping dataset name → saved file path.

        Parameters
        ----------
        start : str  ISO date, e.g. "2019-01-01"
        end   : str  ISO date, inclusive, e.g. "2024-12-31"
        """
        results = {}

        # 1. OWID — no credentials needed, fetch first
        results["owid"] = self.fetch_owid()

        # 2. Open-Meteo weather — no credentials needed
        results["weather"] = self.fetch_weather(start=start, end=end)

        # 3. ENTSO-E — skip gracefully if key is missing
        if self._entsoe_client:
            ts_start = pd.Timestamp(start, tz="UTC")
            ts_end   = pd.Timestamp(end,   tz="UTC") + pd.Timedelta(days=1)

            results["generation"] = self.fetch_generation(ts_start, ts_end)
            results["load"]       = self.fetch_load(ts_start, ts_end)
            results["prices"]     = self.fetch_prices(ts_start, ts_end)
        else:
            log.info("Skipping ENTSO-E fetches (no API key).")

        log.info("fetch_all complete.  Files saved:")
        for name, path in results.items():
            if path:
                log.info("  %-14s → %s", name, path)
        return results

    # ── ENTSO-E ────────────────────────────────────────────────────────────────

    def fetch_generation(
        self, start: pd.Timestamp, end: pd.Timestamp
    ) -> Path | None:
        """
        Hourly actual generation per production type (MW).
        Saved to: data/raw/entsoe_generation_AT.csv
        """
        if not self._entsoe_client:
            return None

        log.info("Fetching ENTSO-E generation  %s → %s …", start.date(), end.date())

        # ENTSO-E API has a 1-year limit per request — chunk by year
        chunks: list[pd.DataFrame] = []
        for year_start, year_end in self._year_chunks(start, end):
            log.info("  chunk %s …", year_start.year)
            df_chunk = self._entsoe_client.query_generation(
                self.country, start=year_start, end=year_end
            )
            chunks.append(df_chunk)
            time.sleep(1)   # be polite to the API

        df = pd.concat(chunks)
        df = df[~df.index.duplicated(keep="first")]   # remove overlap rows
        df.sort_index(inplace=True)

        out = RAW / f"entsoe_generation_{self.country}.csv"
        df.to_csv(out)
        log.info("  Saved %d rows → %s", len(df), out)
        return out

    def fetch_load(
        self, start: pd.Timestamp, end: pd.Timestamp
    ) -> Path | None:
        """
        Hourly actual total load / electricity demand (MW).
        Saved to: data/raw/entsoe_load_AT.csv
        """
        if not self._entsoe_client:
            return None

        log.info("Fetching ENTSO-E load  %s → %s …", start.date(), end.date())

        chunks: list[pd.DataFrame] = []
        for year_start, year_end in self._year_chunks(start, end):
            log.info("  chunk %s …", year_start.year)
            df_chunk = self._entsoe_client.query_load(
                self.country, start=year_start, end=year_end
            )
            chunks.append(df_chunk)
            time.sleep(1)

        df = pd.concat(chunks)
        df = df[~df.index.duplicated(keep="first")]
        df.sort_index(inplace=True)

        out = RAW / f"entsoe_load_{self.country}.csv"
        df.to_csv(out)
        log.info("  Saved %d rows → %s", len(df), out)
        return out

    def fetch_prices(
        self, start: pd.Timestamp, end: pd.Timestamp
    ) -> Path | None:
        """
        Hourly day-ahead electricity prices (€/MWh).
        Saved to: data/raw/entsoe_prices_AT.csv
        """
        if not self._entsoe_client:
            return None

        log.info("Fetching ENTSO-E day-ahead prices  %s → %s …", start.date(), end.date())

        chunks: list[pd.Series] = []
        for year_start, year_end in self._year_chunks(start, end):
            log.info("  chunk %s …", year_start.year)
            s_chunk = self._entsoe_client.query_day_ahead_prices(
                self.country, start=year_start, end=year_end
            )
            chunks.append(s_chunk)
            time.sleep(1)

        s = pd.concat(chunks)
        s = s[~s.index.duplicated(keep="first")]
        s.sort_index(inplace=True)

        out = RAW / f"entsoe_prices_{self.country}.csv"
        s.to_csv(out, header=["price_eur_mwh"])
        log.info("  Saved %d rows → %s", len(s), out)
        return out

    # ── Open-Meteo (ERA5 reanalysis) ───────────────────────────────────────────

    def fetch_weather(
        self,
        start: str = "2019-01-01",
        end: str   = "2024-12-31",
        lat: float = 48.2083,   # Vienna
        lon: float = 16.3731,
    ) -> Path:
        """
        Hourly weather from Open-Meteo ERA5 reanalysis — no API key needed.

        Variables fetched:
          temperature_2m          °C
          shortwave_radiation      W/m²  (proxy for solar generation potential)
          windspeed_10m            km/h
          precipitation            mm
          cloudcover               %

        Saved to: data/raw/weather_vienna.csv
        """
        log.info("Fetching Open-Meteo weather  %s → %s …", start, end)

        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude":  lat,
            "longitude": lon,
            "start_date": start,
            "end_date":   end,
            "hourly": ",".join([
                "temperature_2m",
                "shortwave_radiation",
                "windspeed_10m",
                "precipitation",
                "cloudcover",
            ]),
            #"timezone": "Europe/Vienna",
            #"timezone": "UTC",          # was: "Europe/Vienna"
            #"timezone": "GMT",          # was: "Europe/Vienna"
            # TODO: change time zone to UTC
        }

        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        df = pd.DataFrame(data["hourly"])
        df["time"] = pd.to_datetime(df["time"])
        df.set_index("time", inplace=True)
        df.index.name = "timestamp"

        out = RAW / "weather_vienna.csv"
        df.to_csv(out)
        log.info("  Saved %d rows → %s", len(df), out)
        return out

    # ── Our World in Data ──────────────────────────────────────────────────────

    def fetch_owid(self, country_iso: str = "AUT") -> Path:
        """
        Download OWID energy dataset and filter to Austria.

        Full CSV is ~10 MB; we save the full file to data/external/ and the
        Austria slice to data/raw/ so analysts can re-filter without re-downloading.

        Saved to:
          data/external/owid_energy_full.csv   (full dataset)
          data/raw/owid_energy_AUT.csv          (Austria only)
        """
        log.info("Fetching OWID energy dataset …")

        resp = requests.get(self.OWID_URL, timeout=120)
        resp.raise_for_status()

        full_path = EXTERNAL / "owid_energy_full.csv"
        full_path.write_bytes(resp.content)  # pyright: ignore[reportUnusedCallResult]
        log.info("  Full dataset saved → %s", full_path)

        df_full = pd.read_csv(full_path)
        df_at   = df_full[df_full["iso_code"] == country_iso].copy()
        df_at.set_index("year", inplace=True)

        out = RAW / f"owid_energy_{country_iso}.csv"
        df_at.to_csv(out)
        log.info("  Austria slice (%d rows) → %s", len(df_at), out)
        return out

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _year_chunks(
        start: pd.Timestamp, end: pd.Timestamp
    ) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
        """
        Split a date range into (start, end) pairs by calendar year.
        ENTSO-E API rejects requests spanning more than ~1 year.
        """
        chunks = []
        cursor = start
        while cursor < end:
            year_end = min(
                pd.Timestamp(f"{cursor.year + 1}-01-01", tz=cursor.tz),
                end,
            )
            chunks.append((cursor, year_end))
            cursor = year_end
        return chunks
