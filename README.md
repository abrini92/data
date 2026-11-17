# Data IA — version 1 (+ Pass 2 connectors + Pass 3 proof)

Internal **stc** decision engine: a question is broken into a tree of sub-questions, each with daily estimates, fused into one final probability, frozen in an append-only forecast registry.

**Default seed (ILLUSTRATIVE):** short-horizon KSA indicator question — probability that the next published World Bank observation of Saudi Arabia individuals-using-the-internet (`IT.NET.USER.ZS`) remains at or above 95% (`seeds/ksa_macro_2026.yaml`). Target question (empty tree until Product lands it): `seeds/ksa_nonoil_growth_2027.yaml`. Starlink remains an optional example (`seeds/starlink_ksa.yaml` + `TAXONOMY_PATH=config/taxonomy_starlink.yaml`).

Principle: LLMs extract under control; reproducible models calculate. No LLM output enters the maths without schema and range validation.

> Specs: `BRIEF.md`, `BRIEF-2.md`, `BRIEF-3.md`.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
python -m data_ia.cli cycle
python -m data_ia.cli verify-registry
python -m data_ia.cli brier
python -m data_ia.cli collect --source gastat
streamlit run src/data_ia/dashboard/app.py
pytest
```

Default DB is **SQLite** (`data/dataia.db`). Real HTTP collection is **off** by default (`COLLECT_REAL_SOURCES=false`). Synthetic resolved history is **off** by default (`USE_SYNTHETIC=false`). Setting both `COLLECT_REAL_SOURCES=true` and `USE_SYNTHETIC=true` is a hard error.

Streamlit usage stats are disabled (`.streamlit/config.toml`) under PDPL.

## Pass 3 — honest proof & frozen forecasts

### Forecast registry (append-only)

Every successful `cycle` appends one row to `forecast_registry` (never UPDATE/DELETE; SQLite/Postgres triggers enforce this). Fields include `data_cutoff`, `git_commit`, `config_hash`, `observation_ids`, probability/interval, `data_label` (`REAL`|`SYNTHETIC`), and `sha256` of the canonical JSON.

```powershell
python -m data_ia.cli cycle                 # second run same day → second row
python -m data_ia.cli verify-registry       # recomputes hashes; fails on tamper
python -m data_ia.cli replay --forecast-id 1
```

### No look-ahead

Observations carry `published_at`. A forecast may only use observations with `published_at <= data_cutoff <= forecast_at`. Source-error statistics use only questions resolved **before** `forecast_at`.

### Proof method (`data-ia brier`)

Scores probabilities **from the forecast registry** (engine output), never hand-written YAML probabilities. Baseline = class base rate from resolved questions before `forecast_at` (status-quo alternative for “will X change” questions) — not a flat 0.5. Report includes Brier, baseline Brier, Brier Skill Score `BSS = 1 - Brier/Brier_baseline`, 95% paired-bootstrap interval of the Brier difference (seeded), reliability/calibration bins, and n. Below `BRIER_MIN_N` (default 30) the verdict is **non interprétable**. ILLUSTRATIVE/SYNTHETIC disclaimer whenever any synthetic label is involved. Mixed REAL/SYNTHETIC batches are refused.

### Priors mapping (PROVISIONAL)

`reliability_prior` ∈ [0,1] in `config/sources.yaml` maps to prior variance (monotonic decreasing) and prior bias (0 by default) via `config/prior_mapping.yaml`, plus shrinkage constant `N0`.

> **PROVISIONAL – pending validation by the model owner.** Do not present these values as calibrated.

### Sources (verified 18 Nov 2026)

Merged registry: `config/sources.yaml` (connectors from Pass 2 + verified lot). Markers `[à confirmer]` kept as-is. No connector for `open.data.gov.sa`. SAMA stays skipped.

| Source | Class | Prior | Connector | Notes |
| --- | --- | --- | --- | --- |
| GASTAT | A | 0.95 | `gastat` | Official portal routes only; robots.txt Disallow `/api/` on www.stats.gov.sa |
| National Open Data Platform | A | 0.80 | — | No documented public API |
| Ministry of Finance | A | 0.95 | — | File downloads |
| SAMA | A | 0.85 | `sama` (skip) | Optional; no scraping |
| World Bank | B | 0.85 | `worldbank` | REST JSON |
| IMF SDMX 3.0 | B | 0.85 | `imf` | WEO |
| UN Comtrade | B | 0.80 | `comtrade` | Public preview |
| EIA | B | 0.85 | `eia` | Needs `EIA_API_KEY` |
| CMA | C | 0.75 | `cma` | Configurable timeout; fixture fallback never REAL |
| CST | C | 0.85 | — | Files / open.data.gov.sa hosting |

```powershell
python -m data_ia.cli sources
python -m data_ia.cli collect --source gastat --real
```

`collect` reports `n_parsed` / `n_records` per source.

## Architecture

```
Orchestrator → Scout → Collector → Controller → Investigator → Strategist
```

Orchestrator requires slide-2 fields (`target_variable`, `threshold`, `horizon`, `zone`, `unit`, `resolution_source`, `resolution_rule`) and refuses an empty sub-question tree as **not ready**. Extractions must carry value, unit, `published_at`, and source passage; Controller checks unit against the question. χ² uses `Σ (z_s - b_s - x̂)² / σ_s²` with source reliability; a single observation is accepted with a `single_source` flag.

## Privacy / legal

No telemetry. Offline tests make no network calls. Live mode only hits configured APIs when `COLLECT_REAL_SOURCES=true` or `--real`. Align production hosting with Saudi PDPL.

## Repo layout

```
config/sources.yaml              merged verified registry + connectors
config/prior_mapping.yaml        PROVISIONAL score→variance map
config/sources_verified.yaml     verified lot reference (18 Nov 2026)
seeds/ksa_macro_2026.yaml        default ILLUSTRATIVE question
seeds/ksa_nonoil_growth_2027.yaml target question (empty tree)
src/data_ia/forecast_registry.py append-only registry helpers
tests/fixtures/connectors/       recorded HTTP fixtures (incl. GASTAT cardsinfo)
```
