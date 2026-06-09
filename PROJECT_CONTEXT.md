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

3. **`prices` carries exactly one extra row.** A trailing orphan hour at
   `2025-01-01 00:00 UTC` (`01:00` Vienna), one hour past the end of `demand` /
   `weather`. All three tables share the same start. An inner join on `ts_utc`
   drops it automatically; a left join *from* `prices` would NaN it. Restrict to
   the shared window before Phase 4 joins.

4. **Day-ahead price floor (−500 €/MWh).**
   > Day-ahead prices are bounded below at −500 €/MWh (SDAC harmonised minimum
   > clearing price, CACM Reg. (EU) 2015/1222, in force 2019–2024). The dataset
   > reaches this floor exactly once — 2 Jul 2023, 14:00, a sunny summer Sunday —
   > so the limit rarely binds but explains the observed `min`. Negative prices
   > more broadly (650 h, ~1.2 %) cluster in high-solar midday hours, consistent
   > with renewable oversupply.

5. **`EXTRACT` / `date_part` on a `TIMESTAMPTZ` uses the session timezone, not UTC.**
   So `EXTRACT(year FROM ts_utc)` returns the local-calendar year, and boundary
   hours can fall into an adjacent year — this is why the per-year price plot
   showed a spurious "2025" bucket (two late-Dec/early-Jan boundary hours leaking
   across the Vienna year line). Always extract in explicit local time, e.g.
   `EXTRACT(hour FROM ts_utc AT TIME ZONE 'Europe/Vienna')`, for deterministic
   results that don't depend on session settings

## Phase 3 — EDA key findings (complete → README at Phase 6)

EDA covered distributions, missingness, and seasonal patterns across the hourly
data (demand, prices, weather, generation). Each finding is a hook for its RQ.

- **Prices → RQ4.** 2022 regime shift (median ~€224 vs ~€35 in 2019–20);
  right-skewed (mean ≫ median). Negative prices ~1.2% of hours, rising to 3.4% in
  2024; cluster midday 11–16h (solar oversupply) with a smaller overnight 3–5h
  mode (wind + must-run baseload). −500 €/MWh floor touched exactly once.
- **Demand → RQ2.** Clean, near-symmetric. Double-humped day (morning + evening
  peaks, overnight trough), weekday > weekend, winter-peak/summer-trough.
  Heating-driven — no summer cooling spike (little AC in AT).
- **Temperature → RQ2.** Warm-summer / cold-winter arc (~2 °C Jan, ~22 °C Jul);
  near-perfect inverse mirror of demand-by-month → the RQ2 relationship.
- **Solar → RQ3.** Duck-curve driver. Summer midday avg ~1025 MW vs winter ~320 MW
  (~3×), summer bump wider (day length). The duck curve is effectively a summer
  phenomenon — winter solar barely dents net load.
- **Generation mix → RQ1.** Hydro run-of-river is the baseload backbone
  (never < ~1337 MW); fossil gas is the flexible price-setter (→ RQ4); fossil coal
  ~85% zero = phased out (~2020); biomass near-constant (must-run). The 5
  nominal/zero fuels are excluded from variability work.

**Artifacts:** `src/viz.py` now holds `PALETTE`, `set_house_style()`,
`line_profile()`. Notebook `02_cleaning_eda.ipynb` cells J–M produce the plots above.

**Open items / next:**
- Eurostat GHG data **not yet loaded** into DuckDB (only `owid_energy_at` is the
  annual table) → **RQ5 is blocked** until it's ingested + examined. ← next chat.
- `owid_energy_at` (annual mix) not yet EDA'd → quick coverage check feeds RQ1.

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
