# Austria Energy & Climate Analysis

End-to-end data analysis of Austrian electricity generation, demand, pricing, and greenhouse-gas emissions. The hourly electricity data spans 2019–2024; the annual emissions inventory spans 1990–2024.

Built as Portfolio Project 3 — demonstrating data collection, SQL-based data engineering, EDA, regression analysis, and time-series decomposition.

## Research questions

| # | Question | Methods |
|---|---|---|
| RQ1 | How has Austria's electricity mix shifted toward renewables since 2019? | Trend analysis, stacked area chart |
| RQ2 | Does temperature explain electricity demand? | OLS regression, STL decomposition |
| RQ3 | How pronounced is the solar "duck curve"? | Diurnal profiles, year-over-year comparison |
| RQ4 | Do higher renewables shares push down prices? (merit-order effect) | Correlation, partial regression |
| RQ5 | Is Austria on track for 100% renewable electricity by 2030? | Log-linear trend, extrapolation |
| RQ6 | Is Austria's GHG trajectory on track for its 2030 emissions target? | Trend analysis, target-gap comparison |

RQ5 and RQ6 are deliberately separate. RQ5 tracks the **renewable share of electricity** against Austria's national 100%-renewable-electricity-by-2030 goal (Renewable Expansion Act). RQ6 tracks **economy-wide greenhouse-gas emissions** against the binding EU Effort Sharing target (−48% vs 2005, non-ETS sectors). One is an electricity-mix question; the other is an emissions question.

## Data sources

- **ENTSO-E Transparency Platform** — hourly generation, load, day-ahead prices (free API key required)
- **Open-Meteo / ERA5** — hourly weather reanalysis for Vienna (no key needed)
- **Our World in Data** — annual energy & CO₂ time series (public CSV)
- **Eurostat (`env_air_gge`)** — annual national GHG emissions inventory by sector, 1990–2024 (no key; fetched via the `eurostat` package)
- **EEA Effort Sharing** — non-ETS (ESR) emissions vs the 2030 target path, for RQ6's apples-to-apples comparison

## Notes on the data

ENTSO-E feeds for Austria (operated by APG) are exceptionally complete across 2019–2024: every hourly bucket contains exactly four 15-minute observations, with zero null values in generation, load, or price data. No imputation was applied. This is unusual for European TSO data, where multi-percent gap rates are common.

Five fuel categories in the generation feed (Waste, Other, Geothermal, Fossil Oil, Other renewable) report constant or zero values throughout the period — likely installed-capacity placeholders rather than measured output. They are excluded from variability-driven analyses (RQ3, RQ4) but retained in the dataset for completeness.

The GHG inventory (`env_air_gge`) is the official UNFCCC submission, re-published by Eurostat. It is annual (1990–2024, with the usual ~2-year reporting lag) and organised in the CRF/IPCC source-sector hierarchy. The headline total used here excludes LULUCF (`TOTX4_MEMO`); LULUCF is a separate, volatile land sink and is not part of the emissions total. Note the scope subtlety behind RQ6: the −48%/2005 target applies only to the non-ETS share (~63% of the total), which cannot be derived from the CRF sectors — hence the separate EEA series.

Austria has no nuclear generation (Zwentendorf never opened), so "low-carbon" and
"renewable" electricity are identical here — the OWID `low_carbon_share_elec` and
`renewables_share_elec` series coincide exactly. RQ1/RQ5 use the *electricity* column
family rather than primary-energy shares, and are capped at 2024 to match the project
window even though OWID now carries a provisional 2025 row.

### Setup

```bash
git clone <repo>
cd austria-energy-analysis
```

**Option A — conda** (what the project was developed with):

```bash
conda create -n austria-energy python=3.11
conda activate austria-energy
pip install -r requirements.txt
```

**Option B — venv:**

```bash
python -m venv .venv && source .venv/bin/activate   # requires Python 3.11+
pip install -r requirements.txt
```

Then, with the environment active:

```bash
cp .env.example .env
# edit .env and add your ENTSOE_API_KEY

jupyter lab
```

Run notebooks in order: `01_data_collection` → `02_cleaning_eda` → `03_rq1_…` through `08_rq6_…`.

Notebooks also open in any Jupyter-capable editor (VS Code, Cursor, PyCharm) — JupyterLab is just the no-setup default.

## Project structure

```
data/
  raw/          # fetched CSVs — gitignored
  processed/    # cleaned, merged data (DuckDB)
  external/     # OWID CSV
notebooks/      # one notebook per phase / research question (01–08)
src/
  data_loader.py   # DataLoader class — one fetch method per source
  clean.py         # cleaning transforms (Phase 2+)
  viz.py           # shared plot helpers (Phase 3+)
```

## Key findings

**RQ1 — Electricity mix.** Austria's renewable share of electricity rose from **77% to
86%** (2019–2024), but the gain is back-loaded into 2023–24 and driven by solar scaling
**~5×** (1.7 → 8.1 TWh) alongside gas generation falling **by a third** (≈11 → 7.5 TWh);
coal was fully phased out after 2020. Hydro remained the dominant source (35–46 TWh), and
its weather-driven **~11 TWh swing** — a 2022 drought trough, recovered by 2024 — exceeds
solar's entire six-year gain, so any single year's share is a noisy read of the trend.

**RQ2 — Temperature & demand.** Temperature is the dominant driver of Austria's daily
electricity demand, and the relationship is sharply **asymmetric**. A heating/cooling
degree-day regression locates a **balance point at 16.5 °C**: below it, each degree colder
adds **≈105 MW** (heating); above it, each degree warmer adds only **≈16 MW** — a weak,
barely-significant cooling response, reflecting Austria's minimal air-conditioning.
Temperature plus weekend and public-holiday effects explain **79%** of daily demand variance,
with robust HAC standard errors since daily residuals are strongly autocorrelated. An
independent STL decomposition confirms the seasonal swing is the mirror image of the
temperature cycle, and separately reveals a multi-year **baseline decline from 2022**
(energy-crisis demand reduction) that temperature does not explain — the weather model
captures the seasonal and day-to-day swing, not the structural trend.

_RQ3–RQ6 findings to follow…_

## Tech stack

Python · pandas · DuckDB · statsmodels · matplotlib · entsoe-py · eurostat

## License

Code in this repository is licensed under the [MIT License](LICENSE).

The datasets are **not** redistributed here (see `.gitignore`); notebook
`01_data_collection.ipynb` fetches them at runtime under each source's own terms:

| Source | License / terms | Attribution |
|---|---|---|
| ENTSO-E Transparency Platform | Open data licence (TSO data, Reg. EU 543/2013); platform T&Cs apply | © ENTSO-E Transparency Platform |
| Open-Meteo / ERA5 | CC BY 4.0 (free API = non-commercial use) | Open-Meteo; Copernicus Climate Change Service (C3S) ERA5 |
| Our World in Data — Energy | CC BY 4.0 (OWID); provider terms apply | OWID; Ember; Energy Institute – Statistical Review of World Energy |
| Eurostat (env_air_gge) | Reuse permitted, Commission Decision 2011/833/EU | © European Union / Eurostat |
| EEA — Effort Sharing | EEA reuse policy (attribution required) | © European Environment Agency |

This is a non-commercial portfolio project.