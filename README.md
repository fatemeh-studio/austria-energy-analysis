# Austria Energy & Climate Analysis

End-to-end data analysis of Austrian electricity generation, demand, pricing, and climate trends (2019–2024).

Built as Portfolio Project 3 — demonstrating data collection, SQL-based data engineering, EDA, regression analysis, and time-series decomposition.

## Research questions

| # | Question | Methods |
|---|---|---|
| RQ1 | How has Austria's electricity mix shifted toward renewables? | Trend analysis, stacked area chart |
| RQ2 | Does temperature explain electricity demand? | OLS regression, STL decomposition |
| RQ3 | How pronounced is the solar "duck curve"? | Diurnal profiles, year-over-year comparison |
| RQ4 | Do higher renewables shares push down prices? (merit-order effect) | Correlation, partial regression |
| RQ5 | Is Austria on track for 100% renewable electricity by 2030? | Log-linear trend, extrapolation |

## Data sources

- **ENTSO-E Transparency Platform** — hourly generation, load, day-ahead prices (free API key required)
- **Open-Meteo / ERA5** — hourly weather reanalysis for Vienna (no key needed)
- **Our World in Data** — annual energy & CO₂ time series (public CSV)

## Setup

```bash
git clone <repo>
cd austria-energy-analysis

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and add your ENTSOE_API_KEY

jupyter lab
```

Then run notebooks in order: `01_data_collection` → `02_cleaning_eda` → `03_rq1_...`

## Project structure

```
data/
  raw/          # fetched CSVs — gitignored
  processed/    # cleaned, merged data
  external/     # OWID CSV
notebooks/      # one notebook per phase / research question
src/
  data_loader.py   # DataLoader class
  clean.py         # cleaning transforms (Phase 2+)
  viz.py           # shared plot helpers (Phase 3+)
```

## Key findings

> _To be filled in after analysis._

## Tech stack

Python · pandas · DuckDB · statsmodels · matplotlib · entsoe-py
