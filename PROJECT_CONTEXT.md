# Project Context — Austria Energy & Climate Analysis

## Goal
End-to-end data analysis of Austrian electricity generation, demand, pricing, and climate trends (2019–2024).  
Portfolio Project 3 for a data science job search in Austria (Physics MSc → DS transition).

---

## Research Questions

| # | Question | Methods |
|---|---|---|
| RQ1 | How has Austria's electricity mix shifted toward renewables since 2019? | Trend analysis, stacked area chart |
| RQ2 | Does temperature explain electricity demand, and does that vary seasonally? | OLS regression, STL decomposition |
| RQ3 | What is the solar "duck curve" signature, and how has it grown? | Diurnal profiles, year-over-year comparison |
| RQ4 | Do higher renewables shares push down day-ahead prices? (merit-order effect) | Correlation, partial regression |
| RQ5 | Is Austria on track for 100% renewable electricity by 2030? | Log-linear trend, extrapolation |

---

## Folder Structure

```
austria-energy-analysis/
├── data/
│   ├── raw/          # fetched CSVs — gitignored
│   ├── processed/    # cleaned, merged — gitignored
│   └── external/     # OWID CSV — gitignored
├── notebooks/
│   ├── 01_data_collection.ipynb
│   ├── 02_cleaning_eda.ipynb
│   ├── 03_rq1_energy_mix.ipynb
│   ├── 04_rq2_temperature_demand.ipynb
│   ├── 05_rq3_duck_curve.ipynb
│   ├── 06_rq4_merit_order.ipynb
│   └── 07_rq5_ghg_target.ipynb
├── src/
│   ├── __init__.py
│   ├── data_loader.py   # DataLoader class (Phase 1)
│   ├── clean.py         # cleaning transforms (Phase 2)
│   └── viz.py           # shared plot helpers (Phase 3)
├── .env                 # ENTSOE_API_KEY — gitignored
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

---

## Data Sources

| Source | Data | Granularity | Credentials | Status |
|---|---|---|---|---|
| ENTSO-E Transparency Platform | Generation by fuel type, total load, day-ahead prices (AT) | Hourly | API key (free, email request) | ✅ Ready |
| Open-Meteo / ERA5 | Temperature, solar radiation, wind speed, precipitation (Vienna) | Hourly | None | ✅ Ready |
| Our World in Data | Energy mix, renewables share, CO₂ intensity | Annual | None (public CSV) | ✅ Ready |
| Eurostat (env_air_gge) | GHG emissions by sector | Annual | None (REST API) | ⏳ Not yet fetched |

---

## Data notes & gotchas (Phase 3 findings → README at Phase 6)

1. **Timestamps — store UTC, convert at the edge.** All tables store `TIMESTAMPTZ`
   in UTC. Sources parse cleanly (ENTSO-E carries explicit offsets; Open-Meteo
   requested with `timezone="UTC"`). Convert to Vienna local *only* for
   clock-dependent analysis — every hour-of-day / diurnal query uses
   `ts_utc AT TIME ZONE 'Europe/Vienna'`. Diurnal profiles on raw UTC are shifted
   1–2 h and smear the DST fall-back hour.

2. **Completeness — verified, no imputation.** Every hourly bucket present, zero
   nulls, zero gaps (checked in UTC). Distinction worth stating: in a time series
   a missing hour is an *absent row*, not a null — so completeness was checked via
   row-count-vs-expected + a `LAG` gap scan, not only null counts.

3. **`prices` carries one extra hour (52,609 vs 52,608).** An orphan
   `2025-01-01 00:00` pulled in by the day-ahead fetch window (`end + 1 day`).
   Harmless to the price table, but it becomes NaN when joining `prices` to
   `demand` / `weather` (Phase 4) — align or drop before joining.

4. **Day-ahead price floor (−500 €/MWh).**
   > Day-ahead prices are bounded below at −500 €/MWh (SDAC harmonised minimum
   > clearing price, CACM Reg. (EU) 2015/1222, in force 2019–2024). The dataset
   > reaches this floor exactly once — 2 Jul 2023, 14:00, a sunny summer Sunday —
   > so the limit rarely binds but explains the observed `min`. Negative prices
   > more broadly (650 h, ~1.2 %) cluster in high-solar midday hours, consistent
   > with renewable oversupply.

## Tech Stack & Key Decisions

- **Python 3.11**, conda environment (`austria-energy`)
- **pandas** — data wrangling
- **DuckDB** — SQL layer for cleaning and aggregation (learning SQL through the project)
- **entsoe-py** — ENTSO-E API client
- **statsmodels** — regression and time-series decomposition
- **matplotlib** — all visualisation
- **jupyter lab** in **Cursor** IDE on Ubuntu

**Key design decisions:**
- DuckDB chosen over SQLite/PostgreSQL: file-based, no server, excellent pandas interop, analytical SQL (window functions, CTEs)
- `DataLoader` class in `src/` fetches each source independently; gracefully skips ENTSO-E if no key
- ENTSO-E fetched in yearly chunks (API limit), with 1s sleep between requests
- Raw data gitignored; only code and external CSVs committed

---

## Build Phases

| Phase | Description | Status |
|---|---|---|
| 1 | Data collection — `DataLoader` class, `01_data_collection.ipynb` | ✅ Done |
| 2 | DuckDB schema + cleaning — load CSVs into DB, type-cast, handle nulls | ⏳ Next |
| 3 | EDA — distributions, missingness, seasonal patterns | ⬜ Pending |
| 4 | RQ analysis — one notebook per question (RQ1–RQ5) | ⬜ Pending |
| 5 | Refactor to `src/` — extract repeated logic into `clean.py`, `viz.py` | ⬜ Pending |
| 6 | README + polish — key findings, reproduction steps, GitHub push | ⬜ Pending |

**Current status:** Phase 1 complete. Waiting for ENTSO-E API key before running full data fetch. Open-Meteo and OWID fetches can run immediately.

---

## SQL Learning Arc (via DuckDB)

- Phase 2: `CREATE TABLE`, `INSERT`, `SELECT`, `WHERE`, type casting
- Phase 3: `GROUP BY`, `ORDER BY`, aggregation functions, `HAVING`
- Phase 4: Window functions (`LAG`, `OVER PARTITION BY`), CTEs, `JOIN` across tables
