"""
data_loader.py
--------------
Fetchers for all three data sources in the Austria Energy & Climate project.

Sources:
    1. Our World in Data              — annual energy & CO2 time series
    2. Open-Meteo / ERA5              — hourly weather (Vienna by default)
    3. Eurostat (env_air_gge)         — annual GHG emissions by CRF sector
    4. EEA Effort Sharing (DAT-170)   — annual non-ETS emissions & 2030 target
    5. ENTSO-E Transparency Platform  — hourly generation, load, prices (AT)

Usage:
    from src.data_loader import DataLoader
    dl = DataLoader(entsoe_api_key="YOUR_KEY")
    dl.fetch_all(start="2019-01-01", end="2024-12-31")
"""


import io
import logging
import os
import time
import zipfile
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import requests

# ── optional: entsoe-py (only needed for ENTSO-E fetches) ──────────────────────
try:
    from entsoe.entsoe import EntsoePandasClient
    ENTSOE_AVAILABLE = True
except ImportError:
    ENTSOE_AVAILABLE = False  # pyright: ignore[reportConstantRedefinition]

# ── optional: eurostat (only needed for the GHG emissions fetch) ───────────────
try:
    import eurostat
    EUROSTAT_AVAILABLE = True
except ImportError:
    EUROSTAT_AVAILABLE = False  # pyright: ignore[reportConstantRedefinition]

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
    EEA_ESR_URL = (
            # EEA datahub serves this dataset via a Nextcloud share; its /download
            # endpoint returns a ZIP of the (single-file) folder, so we unzip it.
            # The share token is pinned to this dataset version — it changes on the
            # next annual release (2005-2025), at which point this URL goes stale.
            "https://sdi.eea.europa.eu/datashare/s/NRLMznfmje62ggJ/download"
    )

    def __init__(self, entsoe_api_key: str | None = None, country: str = "AT"):
        self.country: str = country

        # resolve API key: argument > env var
        self._api_key: str | None = entsoe_api_key or os.getenv("ENTSOE_API_KEY")

        if self._api_key and ENTSOE_AVAILABLE:
            self._entsoe_client: EntsoePandasClient | None = EntsoePandasClient(api_key=self._api_key)  # pyright: ignore[reportPossiblyUnboundVariable]
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

        # 3. Eurostat GHG inventory — no credentials, annual (ignores start/end)
        results["ghg"] = self.fetch_ghg(geo=self.country)
        
        # 4. EEA Effort Sharing (non-ETS) — no credentials, annual
        results["esr"] = self.fetch_esr()

        # 5. ENTSO-E — skip gracefully if key is missing
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

    def fetch_generation(self, start: pd.Timestamp, end: pd.Timestamp) -> Path | None:
        """
        Hourly actual generation per production type (MW).
        Saved to: data/raw/entsoe_generation_AT.csv
        """
        return self._year_chunked_fetch(
            label="generation",
            query=lambda s, e: self._entsoe_client.query_generation(self.country, start=s, end=e),  # pyright: ignore[reportOptionalMemberAccess]
            out_name=f"entsoe_generation_{self.country}.csv",
            start=start, end=end,
        )
    
    
    def fetch_load(self, start: pd.Timestamp, end: pd.Timestamp) -> Path | None:
        """
        Hourly actual total load / electricity demand (MW).
        Saved to: data/raw/entsoe_load_AT.csv
        """
        return self._year_chunked_fetch(
            label="load",
            query=lambda s, e: self._entsoe_client.query_load(self.country, start=s, end=e),  # pyright: ignore[reportOptionalMemberAccess]
            out_name=f"entsoe_load_{self.country}.csv",
            start=start, end=end,
        )
    
    
    def fetch_prices(self, start: pd.Timestamp, end: pd.Timestamp) -> Path | None:
        """
        Hourly day-ahead electricity prices (€/MWh).
        Saved to: data/raw/entsoe_prices_AT.csv
        """
        return self._year_chunked_fetch(
            label="day-ahead prices",
            query=lambda s, e: self._entsoe_client.query_day_ahead_prices(self.country, start=s, end=e),  # pyright: ignore[reportOptionalMemberAccess]
            out_name=f"entsoe_prices_{self.country}.csv",
            start=start, end=end,
            to_csv_kwargs={"header": ["price_eur_mwh"]},
        )

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
            "timezone": "UTC",
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

    # ── Eurostat (GHG inventory) ─────────────────────────────────────────────────

    def fetch_ghg(self, geo: str = "AT") -> Path:
        """
        Annual greenhouse-gas emissions inventory from Eurostat (dataset
        ``env_air_gge``) — the official UNFCCC inventory, re-published by Eurostat.

        Pulls the GHG aggregate (all gases, expressed in CO2-equivalent) for every
        source sector and every year (1990 -> latest, ~t-2), for one country.
        We deliberately fetch *all* sectors and *all* units and pick what we need
        at the cleaning stage — easier to inspect first than to guess the codes.

        Saved to: data/raw/eurostat_ghg_{geo}.csv

        Parameters
        ----------
        geo : str
            Eurostat country code. Default: "AT" (Austria).
        """
        if not EUROSTAT_AVAILABLE:
            raise ImportError(
                "The 'eurostat' package is required for fetch_ghg(). "
                "Install it with: pip install eurostat"
            )

        log.info("Fetching Eurostat GHG inventory (env_air_gge) for %s …", geo)

        # airpol="GHG" -> the all-gases aggregate, already in CO2-equivalent.
        # unit and src_crf left unfiltered so we can see every available unit
        # (absolute Mt, index, per-capita) and every sector before choosing.
        df = eurostat.get_data_df(
            "env_air_gge",
            filter_pars={"geo": geo, "airpol": "GHG"},
        )
        if df is None or df.empty:
            raise RuntimeError(
                f"Eurostat returned no data for env_air_gge / geo={geo}."
            )

        out = RAW / f"eurostat_ghg_{geo}.csv"
        df.to_csv(out, index=False)
        log.info("  Saved %d rows x %d cols → %s", df.shape[0], df.shape[1], out)
        return out

    # ── EEA (Effort Sharing emissions & targets) ─────────────────────────────────

    def fetch_esr(self) -> Path:
        """
        Annual non-ETS (Effort Sharing) greenhouse-gas emissions and targets from
        the European Environment Agency — dataset DAT-170-en, "Greenhouse gas
        emissions under the Effort Sharing Legislation, 2005-2024".

        This is the apples-to-apples source for RQ6: the EEA reconciles the
        non-ETS emission series, the 2005 base-year and the Annual Emission
        Allocations (AEAs) / 2030 target onto one accounting basis — something
        that *cannot* be derived from Eurostat ``env_air_gge`` (the ETS/non-ETS
        split cuts across the CRF sectors).

        Accounting basis (carried into RQ6): the file spans two regimes — the
        Effort Sharing Decision for 2013-2020 (AR4 global-warming potentials,
        excl. NF3) and the Effort Sharing Regulation for 2021-2030 (AR5 GWPs,
        incl. NF3). 2005-2012 and the latest year are EEA estimates.

        The full multi-country workbook is saved as-is; we filter to Austria and
        pick the columns we need at the cleaning stage (same approach as
        ``fetch_ghg`` — inspect first, don't guess the layout).

        Source is CC-BY 4.0 (© European Commission, EEA) — acknowledge in README.

        Saved to: data/external/eea_esr_effort_sharing.xlsx
        """
        log.info("Fetching EEA Effort Sharing emissions (DAT-170-en) …")

        # The datahub link resolves to a Nextcloud share whose /download endpoint
        # returns a ZIP of the folder (one .xlsx inside), not the bare workbook —
        # so we fetch the archive and extract the spreadsheet in-memory.
        resp = requests.get(
            self.EEA_ESR_URL,
            timeout=120,
            headers={"User-Agent": "austria-energy-analysis/1.0 (+research)"},
        )
        resp.raise_for_status()

        # Fail loudly if we got an HTML page instead of a zip (e.g. URL went stale)
        if resp.content[:2] != b"PK":
            raise RuntimeError(
                "EEA download was not a ZIP archive — the share URL may have changed. "
                f"First bytes: {resp.content[:16]!r}"
            )

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            members = [n for n in zf.namelist()
                       if n.lower().endswith((".xlsx", ".xls"))]
            if not members:
                raise RuntimeError(
                    f"No spreadsheet in EEA archive; contents: {zf.namelist()}"
                )
            xlsx_bytes = zf.read(members[0])

        out = EXTERNAL / "eea_esr_effort_sharing.xlsx"
        out.write_bytes(xlsx_bytes)  # pyright: ignore[reportUnusedCallResult]
        log.info("  Extracted %s (%.0f KB) → %s",
                 members[0], len(xlsx_bytes) / 1024, out)
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

    @staticmethod
    def _call_with_backoff(
        query: "Callable[[pd.Timestamp, pd.Timestamp], pd.DataFrame | pd.Series]",
        start: pd.Timestamp,
        end: pd.Timestamp,
        *,
        attempts: int = 4,
        base_delay: float = 2.0,
    ) -> "pd.DataFrame | pd.Series":
        """
        Call one ENTSO-E chunk query with exponential backoff on *transient* errors.

        Retries network hiccups and rate-limit / server errors (HTTP 429, 5xx),
        doubling the wait each time (base_delay, 2×, 4×, …). Anything else — a 4xx
        other than 429, or entsoe-py's NoMatchingDataError — is a real failure and is
        re-raised at once rather than retried.
        """
        retryable_status = {429, 500, 502, 503, 504}
        for attempt in range(1, attempts + 1):
            try:
                return query(start, end)
            except requests.exceptions.RequestException as exc:
                # HTTPError carries a .response; a non-retryable status fails fast.
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and status not in retryable_status:
                    raise
                if attempt == attempts:
                    log.error("  chunk %s failed after %d attempts", start.year, attempts)
                    raise
                wait = base_delay * 2 ** (attempt - 1)
                log.warning(
                    "  chunk %s attempt %d/%d failed (%s) — retrying in %.0fs",
                    start.year, attempt, attempts, status or type(exc).__name__, wait,
                )
                time.sleep(wait)
        raise RuntimeError("retry loop exited without returning")  # unreachable; satisfies type-checkers


    def _year_chunked_fetch(
        self,
        *,
        label: str,
        query: "Callable[[pd.Timestamp, pd.Timestamp], pd.DataFrame | pd.Series]",
        out_name: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
        to_csv_kwargs: dict | None = None,
    ) -> Path | None:
        """
        Shared fetch shape for ENTSO-E series: chunk the range by calendar year (the
        API rejects >~1-year requests), retry each chunk on transient errors, then
        concatenate → drop year-boundary overlap → sort → save CSV.

        Parameters
        ----------
        label : str
            Human-readable name for logging, e.g. "generation".
        query : callable
            Takes (start, end) timestamps and returns one chunk — a DataFrame
            (generation, load) or a Series (prices).
        out_name : str
            CSV filename under data/raw/, e.g. "entsoe_generation_AT.csv".
        start, end : pd.Timestamp
            UTC range, end-exclusive.
        to_csv_kwargs : dict, optional
            Extra kwargs forwarded to ``.to_csv`` — prices uses this to set
            ``header=["price_eur_mwh"]`` on its unnamed Series.

        Returns
        -------
        Path | None
            Saved CSV path, or None if no ENTSO-E client is configured.
        """
        if not self._entsoe_client:
            return None

        log.info("Fetching ENTSO-E %s  %s → %s …", label, start.date(), end.date())

        chunks: list[pd.DataFrame | pd.Series] = []
        for year_start, year_end in self._year_chunks(start, end):
            log.info("  chunk %s …", year_start.year)
            chunks.append(self._call_with_backoff(query, year_start, year_end))
            time.sleep(1)   # be polite between chunks

        data = pd.concat(chunks)
        data = data[~data.index.duplicated(keep="first")]   # remove year-boundary overlap
        data.sort_index(inplace=True)

        out = RAW / out_name
        data.to_csv(out, **(to_csv_kwargs or {}))
        log.info("  Saved %d rows → %s", len(data), out)
        return out
