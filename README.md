# Data IA — version 1 (+ Pass 2 connectors)

Internal **stc** decision engine: a question is broken into a tree of sub-questions, each with daily estimates, fused into one final probability.

**Default seed (ILLUSTRATIVE):** short-horizon KSA indicator question — probability that the next published World Bank observation of Saudi Arabia individuals-using-the-internet (`IT.NET.USER.ZS`) remains at or above 95% (`seeds/ksa_macro_2026.yaml`). Starlink remains an optional example only (`seeds/starlink_ksa.yaml` + `TAXONOMY_PATH=config/taxonomy_starlink.yaml`).

Principle: LLMs extract under control; reproducible models calculate. No LLM output enters the maths without schema and range validation.

> Specs: `BRIEF.md` (v1) and `BRIEF-2.md` (real sources / n_eff). Technical deck pptx was not in-repo at build time.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
python -m data_ia.cli cycle
python -m data_ia.cli brier
python -m data_ia.cli collect --source worldbank
streamlit run src/data_ia/dashboard/app.py
pytest
```

Or: `powershell -ExecutionPolicy Bypass -File scripts/dev_start.ps1`

Default DB is **SQLite** (`data/dataia.db`). Optional: `docker compose up -d` + Postgres URL in `.env`.

Real HTTP collection is **off** by default (`COLLECT_REAL_SOURCES=false`). Connectors use recorded fixtures offline.

## Pass 2 — real source connectors

Registry: `config/sources.yaml`. CLI:

```powershell
python -m data_ia.cli sources
python -m data_ia.cli collect --source worldbank          # fixture by default
python -m data_ia.cli collect --source worldbank --real   # live HTTP
$env:COLLECT_REAL_SOURCES="true"; python -m data_ia.cli collect --all
```

| Source | Access | Key | License / notes |
| --- | --- | --- | --- |
| `worldbank` | REST JSON Indicators API (SAU) | none | World Bank open data |
| `imf` | SDMX 3.0 WEO | none | IMF data terms |
| `comtrade` | Public preview API | none | Rate-limited preview |
| `gastat` | stats.gov.sa / cards API | optional `GASTAT_API_KEY` | Skip if auth required |
| `cma` | opendataapi.cma.gov.sa | none | CMA open data; live may time out |
| `eia` | api.eia.gov | `EIA_API_KEY` | U.S. public domain; skip if absent |
| `sama` | optional | — | Skipped live (no scraping) |

**Do not scrape** Umm Al-Qura, KAPSARC, Ookla, Saudi Exchange, or Etimad salary APIs (terms / PDPL). Respect robots.txt and rate limits; User-Agent is `DataIA/0.2`.

### API keys

Put keys only in `.env` (never commit):

```
EIA_API_KEY=
GASTAT_API_KEY=
```

## Architecture

```
Orchestrator → Scout → Collector → Controller → Investigator → Strategist
```

| Agent | Produces | Checks | On failure |
| --- | --- | --- | --- |
| Orchestrator | Question + sub-question tree | ids, leaf text, structure | Block; do not schedule Scout |
| Scout | Source catalogue | URL, class, unique ids | Drop bad candidates |
| Collector | Raw docs + extractions + provenance | hash, timestamp, version | Retry stub; mark failed |
| Controller | Accept / reject / quarantine | schema, range, χ² | Exclude from maths |
| Investigator | Surprise −log P(x_t \| past) | finite; threshold alerts | Note; do not block Strategist |
| Strategist | Final P, interval, weights, dP/dx | bounds; fused leaves | Withhold publish |

## Formula → code

| Formula | Code |
| --- | --- |
| Source bias / variance / τ / shrinkage | `data_ia.math.sources` |
| Fusion | `fuse_observations` |
| \(n_{\mathrm{eff}}=n/(1+(n-1)\rho)\) | `n_eff` + group scales in `fuse_observations` |
| Logit taxonomy + sensitivities | `data_ia.math.aggregation` |
| Brier vs baseline | `data_ia.math.brier` + `data-ia brier` |

Correlation groups / ρ: `config/sources.yaml` and seed `correlation_groups` / `group_rho`.

## Seeds

- **Default:** `seeds/ksa_macro_2026.yaml` (ILLUSTRATIVE KSA short-horizon indicator)
- Optional: `seeds/starlink_ksa.yaml` + `TAXONOMY_PATH=config/taxonomy_starlink.yaml`
- Brier set: `seeds/synthetic_resolved.yaml` — **never present as real**

## Privacy / legal

No telemetry. Offline tests make no network calls. Live mode only hits configured APIs when `COLLECT_REAL_SOURCES=true` or `--real`. Align production hosting with Saudi PDPL.

## Repo layout

```
src/data_ia/connectors/   World Bank, IMF, Comtrade, GASTAT, CMA, EIA, SAMA
config/sources.yaml       registry + correlation groups
tests/fixtures/connectors recorded HTTP fixtures
seeds/ksa_macro_2026.yaml default ILLUSTRATIVE question
```
