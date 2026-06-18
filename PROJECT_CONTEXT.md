# Project Context — Austria Energy & Climate Analysis

## Goal
End-to-end data analysis of Austrian electricity generation, demand, pricing, and
climate trends. Hourly electricity data spans 2019–2024; the annual emissions
inventory spans 1990–2024.
Portfolio Project 3 for a data science job search in Austria (Physics MSc → DS transition).

---

## Research Questions

| # | Question | Methods |
|---|---|---|
| RQ1 | How has Austria's electricity mix shifted toward renewables since 2019? | Trend analysis, stacked area chart |
| RQ2 | Does temperature explain electricity demand, and does that vary seasonally? | OLS regression, STL decomposition |
| RQ3 | What is the solar "duck curve" signature, and how has it grown? | Diurnal profiles, year-over-year comparison |
| RQ4 | Do higher renewables shares push down day-ahead prices? (merit-order effect) | Correlation, partial regression |
| RQ5 | Is Austria on track for 100% renewable **electricity** by 2030? | Log-linear trend, extrapolation |
| RQ6 | Is Austria's total **GHG emissions** trajectory on track for its 2030 target? | Trend analysis, target-gap vs ESR −48%/2005 |

**RQ5 vs RQ6 (resolved):** two different questions, kept separate. RQ5 = renewable
share of *electricity* vs the national 100%-by-2030 goal (Renewable Expansion Act /
EAG), using ENTSO-E generation + OWID. RQ6 = *economy-wide* GHG emissions vs the binding
EU Effort Sharing target, using Eurostat + EEA. GHG was added as a **new RQ6** rather
than replacing RQ5.

---

## Folder Structure

```
austria-energy-analysis/
├── data/
│   ├── raw/          # fetched CSVs — gitignored
│   ├── processed/    # DuckDB database — gitignored
│   └── external/     # OWID CSV — gitignored
├── notebooks/
│   ├── 01_data_collection.ipynb
│   ├── 02_cleaning_eda.ipynb
│   ├── 03_rq1_energy_mix.ipynb
│   ├── 04_rq2_temperature_demand.ipynb
│   ├── 05_rq3_duck_curve.ipynb
│   ├── 06_rq4_merit_order.ipynb
│   ├── 07_rq5_renewable_electricity.ipynb
│   └── 08_rq6_ghg_target.ipynb
├── src/
│   ├── __init__.py
│   ├── data_loader.py   # DataLoader class (Phase 1) — one fetch method per source
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
| ENTSO-E Transparency Platform | Generation by fuel type, total load, day-ahead prices (AT) | Hourly | API key (free) | ✅ Loaded |
| Open-Meteo / ERA5 | Temperature, solar radiation, wind speed, precipitation (Vienna) | Hourly | None | ✅ Loaded |
| Our World in Data | Energy mix, renewables share, CO₂ intensity | Annual | None (public CSV) | ✅ Loaded (EDA pending) |
| Eurostat (`env_air_gge`) | GHG emissions by CRF sector | Annual | None (`eurostat` pkg) | ✅ Loaded → `ghg_emissions` |
| EEA — Effort Sharing (ESR) | Non-ETS emissions vs the 2030 target path | Annual | None | ⏳ Not yet fetched (RQ6) |

---

## Data notes & gotchas (Phase 3 and 4 findings → README at Phase 6)

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
   results that don't depend on session settings.

6. **`ghg_emissions` is a hierarchy + totals in one column.** The table holds the
   top-level CRF sectors (CRF1–CRF6) *and* the national totals (`TOTX4_MEMO` excl.
   LULUCF, `TOTXMEMO` incl. LULUCF) in the same `mt_co2e` column. Never `SUM` the
   whole column — it double-counts. Filter to `TOTX4_MEMO` for the headline total,
   or to the `CRF*` set for a sector decomposition (which sums back to `TOTX4_MEMO`).
   LULUCF (CRF4) is a *negative* sink — exclude it from emissions stacks.

7. **`owid_energy_at` — window, columns & reconciliation (RQ1).** Annual, contiguous
   1900–2025. **RQ1 capped at 2019–2024** to match the project window — a 2025 row
   exists and looks complete, but is excluded to keep all RQs aligned (revisit only as a
   deliberate RQ1+RQ5 extension, with the scope docs updated). Use the *electricity*
   column family (`*_share_elec`, per-source `*_electricity` in TWh) — **not**
   `*_share_energy` (primary energy, folds in transport/heat). `nuclear_electricity` = 0
   every year → `low_carbon_share_elec` ≡ `renewables_share_elec` (no nuclear in AT —
   Zwentendorf never opened). The seven named sources
   (hydro/wind/solar/biofuel/gas/coal/oil) sum **exactly** to `electricity_generation`
   (residual = 0) — no hidden "other" category.

8. **Grain is chosen per question.** RQ2 aggregates to **daily** means (Vienna-local day) —
   this removes the hour-of-day cycle *by construction* and is the right grain for a
   seasonal/weather question and for STL. RQ3/RQ4 deliberately stay **hourly** (within-day
   phenomena: the duck curve, the merit-order price effect). New dependency: `holidays`
   (conda-forge) for the Austrian public-holiday dummy.

## Phase 3 — EDA key findings (complete → README at Phase 6)

EDA covered distributions, missingness, and seasonal patterns across the hourly
data (demand, prices, weather, generation), plus a first look at the annual GHG
inventory. Each finding is a hook for its RQ.

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
- **GHG → RQ6.** Total emissions (excl. LULUCF) peaked ~93 Mt in 2005, fell to
  66.6 Mt in 2024 (≈ −28% vs 2005), most of the drop after 2019. Energy (CRF1) is
  the dominant and most-declining sector. NB the −28% is *total*; the −48% target
  is non-ETS only (see RQ5/RQ6 section).

**Artifacts:** `src/viz.py` now holds `PALETTE`, `set_house_style()`,
`line_profile()`. Notebook `02_cleaning_eda.ipynb` cells J–M produce the electricity
plots; Cell O produces the GHG trajectory + sector-decomposition stackplot.

## Phase 4 — RQ findings (in progress)

- **RQ1 — electricity mix.** Renewable share of electricity rose 77% → 86% (2019→2024),
  but the gain is **back-loaded into 2023–24** and driven by solar scaling **~5×**
  (1.7 → 8.1 TWh) alongside gas generation falling **by a third** (≈11 → 7.5 TWh); coal
  fully phased out after 2020. Hydro stayed dominant (35–46 TWh); its weather-driven
  **~11 TWh peak-to-trough swing** (2022 drought trough, 2024 recovery) exceeds solar's
  entire six-year gain, so any single year's share is a noisy read of the trend.
  Visual: absolute-TWh stacked area + renewable-share line (twin axis), notebook 03.
- **RQ2 — temperature → demand.** Temperature is the dominant driver of daily demand, and
  strongly **asymmetric**. A **degree-day regression** (heating/cooling degree-days about an
  empirically estimated **balance point of 16.5 °C**) gives a steep heating slope of
  **+105 MW per °C** below the balance point and a weak, **marginally significant** cooling
  slope of **+16 MW per °C** above it (p ≈ 0.05 — Austria's minimal AC, plus a data-starved
  coefficient: few hot days). Model `demand_mw ~ hdd + cdd + is_weekend + is_holiday`, daily
  grain, **HAC / Newey–West** standard errors (residuals strongly autocorrelated,
  Durbin–Watson ≈ 0.65). R² = **0.79**; weekend −1230 MW, holiday −1156 MW. Visual:
  degree-day curve over a calendar-adjusted scatter (notebook 04, Cell G).
- **RQ2 — STL cross-check + a trend the regression misses.** An independent STL
  decomposition (daily, period 365, robust) confirms the **seasonal demand swing is the
  mirror of the temperature cycle** — found *without* using temperature, so corroboration,
  not proof. It also exposes what the flat-intercept regression cannot: a **multi-year
  baseline decline (~7250 → ~6650 MW)** — post-COVID rebound hump (~2021), then sustained
  energy-crisis demand destruction (2022→), levelling 2024 — and a **heteroskedastic
  remainder** (residual variance balloons 2020–2023). Temperature explains the seasonal +
  day-to-day swing, *not* the structural trend. (Extension hook: a year/trend term if RQ2 is
  ever revisited; slopes are unaffected since the drift is slow and ~orthogonal to daily temp.)
- **RQ3 — solar duck curve.** Net load = demand − solar (hourly, Vienna-local); `demand ⋈ solar`
  is 1:1 (52,608 h, no orphan — the orphan hour is prices-only), both series national. **The duck is
  a 2023–24 event, not a trend:** belly depth, ramp rate, and steepest-hour ramp sit flat through
  2019–22, inflect in 2023, ~double again in 2024 — the net-load mirror of RQ1's back-loaded solar
  ~5× build-out. Summer 2024 belly **2,524 MW** (deepest), avg evening ramp **459 MW/h**, steepest
  single hour **785 MW/h**. **Crossover (the key tell):** summer had the *shallowest* belly in
  low-solar years (280 MW in 2021) and the *deepest* by 2024 — the season with the most solar
  overtook all others exactly when solar scaled, i.e. the belly is solar-carved, not a demand
  artifact. Spring close behind (2,426 MW); winter shallowest but **more than doubled** (470→1,200).
  **Timing:** trough migrates 15h→13h (all seasons); summer peak 18h→20h — the neck deepens *and*
  stretches. **Corrected scope:** the duck is present in **every season** (not summer-only), deepest
  in summer, weakest in deep winter.
  - **Method.** Belly depth = morning shoulder (max 06–10h) − midday trough (min 11–15h), kept
    **shoulder-relative** so the post-2022 demand-decline level shift cancels — read the *growth*, not
    the absolute. Evening ramp = (evening peak max 17–22h − trough) / Δhours; plus steepest single-hour
    ramp. Reusable `duck_metrics(profile)` (Phase-5 candidate → metrics module or `viz.py`), with a
    `len < 24` guard for partial profiles.
  - **Solar-only, justified empirically.** Solar's diurnal profile spans **0.00×–3.21×** its daily
    mean (clock-locked); wind only **0.87×–1.10×** (flat) — netting wind shifts net-load *level*, not
    *shape*, so we net solar only. (Wind label is `Wind Onshore`; no offshore in AT.)
  - **Gotcha (instance of #5).** Per-(season, year) grouping needs `WHERE ts_local < TIMESTAMP
    '2025-01-01'`: the final UTC hour spills to 2025 local and spawns a phantom 2025 group with a
    degenerate 1-row profile, crashing `idxmin()`.
  - Notebook `05_rq3_duck_curve`: connect → verify 1:1 join → summer-vs-winter (solar wedge) →
    per-season avg-vs-2024 (4-panel) → wind justification → `duck_metrics` → metric table →
    belly-depth growth → headline (summer net load, one line per year). Closing 2-sentence finding.

## RQ5 / RQ6 — targets & scope (decided)

**RQ5 — renewable electricity.** Austria's Renewable Expansion Act (EAG, 2021) targets
100% renewable electricity (national balance) by 2030. Track the renewable share of
generation / electricity (ENTSO-E + OWID) with a log-linear trend + extrapolation.

**RQ6 — GHG emissions.**
- Headline series: `ghg_emissions` filtered to `TOTX4_MEMO` (total excl. LULUCF).
- Binding 2030 target: EU Effort Sharing Regulation **−48% vs 2005, non-ETS sectors
  only** (Reg 2018/842, raised from −36% by Reg 2023/857 under Fit-for-55).
- Scope catch: the −48% applies to the ~63% non-ETS slice, NOT the total, and that
  slice **cannot** be derived from `env_air_gge`'s CRF sectors (ETS/non-ETS cuts
  across them).
- **Option A (chosen):** also pull the EEA ESR-scope series so the −48% target line
  is apples-to-apples.

**Open items / next:**
- EEA ESR-scope series **not yet fetched** → RQ6 target line pending. ← next.
- Build RQ5 notebook (07_rq5_renewable_electricity) and RQ6 notebook
  (08_rq6_ghg_target) — Phase 4.
- Phase-6 figure pass: RQ1 stackplot Biomass/Wind colours are too close for colorblind
  viewers — pick more distinct colours.

## Tech Stack & Key Decisions

- **Python 3.11**, conda environment (`austria-energy`)
- **pandas** — data wrangling
- **DuckDB** — SQL layer for cleaning and aggregation (learning SQL through the project)
- **entsoe-py** — ENTSO-E API client
- **eurostat** — Eurostat REST client for the GHG inventory (`env_air_gge`)
- **statsmodels** — regression and time-series decomposition
- **matplotlib** — all visualisation
- **jupyter lab** in **Cursor** IDE on Ubuntu

**Key design decisions:**
- DuckDB chosen over SQLite/PostgreSQL: file-based, no server, excellent pandas interop, analytical SQL (window functions, CTEs, UNPIVOT)
- `DataLoader` class in `src/` fetches each source independently; gracefully skips ENTSO-E if no key
- ENTSO-E fetched in yearly chunks (API limit), with 1s sleep between requests
- Eurostat GHG fetched once (all sectors/units for AT), reshaped wide→long in DuckDB via `UNPIVOT`, filtered to `MIO_T` + curated sectors
- Raw data gitignored; only code and external CSVs committed

---

## Build Phases

| Phase | Description | Status |
|---|---|---|
| 1 | Data collection — `DataLoader`, `01_data_collection.ipynb` (incl. Eurostat GHG) | ✅ Done |
| 2 | DuckDB schema + cleaning — load CSVs into DB, type-cast, handle nulls | ✅ Done |
| 3 | EDA — distributions, missingness, seasonal patterns (incl. GHG, Cell O) | ✅ Done |
| 4 | RQ analysis — one notebook per question (RQ1–RQ6) | ⏳ In progress |
| 5 | Refactor to `src/` — extract repeated logic into `clean.py`, `viz.py` | ⬜ Pending |
| 6 | README + polish — key findings, reproduction steps, GitHub push | ⬜ Pending |

**Current status:** Phases 1–3 complete; Phase 4 underway. **RQ1, RQ2, and RQ3 done** (notebooks
`03_rq1_energy_mix`, `04_rq2_temperature_demand`, `05_rq3_duck_curve`). Next RQ: **RQ4** (merit-order
effect — hourly grain, day-ahead prices vs renewable supply). Remaining Phase-4 prerequisite: the EEA
ESR-scope fetch for RQ6. DuckDB holds `generation`, `demand`, `prices`, `weather`, `owid_energy_at`,
`ghg_emissions`, plus the two staging tables.

---

## SQL Learning Arc (via DuckDB)

- Phase 2: `CREATE TABLE`, `INSERT`, `SELECT`, `WHERE`, type casting
- Phase 3: `GROUP BY`, `ORDER BY`, aggregation functions, `HAVING`, `UNPIVOT` (wide→long)
- Phase 4: Window functions (`LAG`, `OVER PARTITION BY`), CTEs, `JOIN` across tables