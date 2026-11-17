# Data IA — version 1

Internal **stc** decision engine: a question is broken into a tree of sub-questions, each with daily estimates, fused into one final probability.

**First seed question (ILLUSTRATIVE):** probability that CST approves Starlink’s residential service, open to the public, in KSA before 31 Dec 2027.

Principle: LLMs extract under control; reproducible models calculate. No LLM output enters the maths without schema and range validation.

> The technical deck `docs/Data-IA-Technical-Deck-v3.pptx` was not present in the repo when v1 was built. Deliverables follow `BRIEF.md` (slides 1–14). Slide 15 vision is out of scope.

## Quick start (Windows-friendly, no Docker required)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
python -m data_ia.cli cycle
python -m data_ia.cli brier
streamlit run src/data_ia/dashboard/app.py
pytest
```

One-shot offline cycle (same as `data-ia cycle`):

```powershell
python scripts/run_offline_cycle.py
```

Default storage is **SQLite** (`data/dataia.db`). Tests and the offline cycle run fully without Docker.

### Optional: PostgreSQL + pgvector via Docker

```powershell
docker compose up -d
# set DATABASE_URL=postgresql+psycopg://dataia:dataia@localhost:5432/dataia in .env
python -m data_ia.cli cycle
```

If Postgres is configured but unreachable, the pipeline **falls back to SQLite** automatically (`db_mode: sqlite-fallback`).

Real HTTP collection is **off** by default (`COLLECT_REAL_SOURCES=false`). The Collector uses stub documents + the deterministic stub LLM so the cycle stays offline. Set the flag to `true` only when you intentionally want live fetches of configured public URLs.

## Architecture

```
Orchestrator → Scout → Collector → Controller → Investigator → Strategist
     │            │         │            │             │             │
  question     sources   raw docs +   accept /      surprise     fuse +
  tree         catalogue extractions  quarantine    scores       aggregate
```

| Agent | Produces | Checks | On failure |
| --- | --- | --- | --- |
| Orchestrator | Verified question + sub-question tree | ids, leaf text, structure | Block question; do not schedule Scout |
| Scout | Source catalogue candidates | URL scheme, class allow-list, unique ids | Drop bad candidates; flag coverage gap |
| Collector | Raw docs + extractions with provenance (URL, timestamp, hash, extractor version) | hash / timestamp / version present | Retry with stub body; mark failed if empty |
| Controller | Accepted / rejected / quarantined observations | schema, range, χ² consistency | Reject schema/range; quarantine χ²; exclude from maths |
| Investigator | Per-leaf surprise = −log P(x_t \| past) | finite surprise; threshold alerts | Note insufficient history; do not block Strategist |
| Strategist | Final P, interval, source weights, sensitivities | P∈[0,1]; interval ordered; fused leaves | Withhold publish; keep last good snapshot |

Scheduler: APScheduler cron job (`SCHEDULER_ENABLED=true`) or one-shot via CLI.

## Formula → code mapping

| Formula (BRIEF / slide 5–9) | Code |
| --- | --- |
| \(z_s = x + b_s + \varepsilon_s\) | `data_ia.math.sources` |
| \(b_s = \mathrm{mean}(z_{s,i}-x_i)\) | `estimate_source_reliability` |
| \(\sigma_s^2 = \mathrm{mean}((z_{s,i}-b_s-x_i)^2)\) | same |
| \(\tau_s = 1/\sigma_s^2\) | `SourceReliability.precision` |
| \(\lambda_N = N/(N+N_0)\) shrinkage to class prior | `shrink_toward_prior` |
| Precision-weighted fusion | `fuse_observations` |
| Logit aggregation + taxonomy YAML | `data_ia.math.aggregation.evaluate_taxonomy` + `config/taxonomy.yaml` |
| Sensitivities \(dP/dx_k\) | finite differences in `evaluate_taxonomy` |
| Surprise \(-\log P(x_t\mid\mathrm{past})\) | `data_ia.math.surprise.gaussian_surprise` |
| Brier vs naive baseline | `data_ia.math.brier` + `data-ia brier` |

### Choices where the deck is silent

- **Weighted-logit weights** are normalised to sum to 1 on each node (taxonomy may list unnormalised weights).
- **Variance floor** \(10^{-12}\) so perfect tiny samples do not explode precision.
- **Predictive surprise** uses a Gaussian \(N(\bar x, s^2)\) on the leaf history.
- **Interval** on final P: first-order delta-method style from leaf variances and FD sensitivities (approximate 95% band).
- **χ² check** treats cross-source readings on one leaf as a consistency probe vs their mean (continuous proxy).
- **PyMC** is optional (`pip install -e ".[bayes]"`); v1 maths use NumPy/SciPy only.
- **Default DB** is SQLite for Windows hosts without Docker.

## Seeds & synthetic proof

- `seeds/starlink_ksa.yaml` — ILLUSTRATIVE question tree + public source URLs (CST, SSA, press).
- `seeds/synthetic_resolved.yaml` — ILLUSTRATIVE/SYNTHETIC short-horizon resolved set for Brier. **Never present as real.**

```powershell
python -m data_ia.cli brier
```

## Dashboard

After a cycle:

```powershell
streamlit run src/data_ia/dashboard/app.py
```

Shows the tree, leaf estimate history, final probability with interval, source weights, and sensitivities.

## Tests & CI

```powershell
pytest
```

Postgres-only test is marked `@pytest.mark.postgres` and skips when Docker/Postgres is unavailable. GitHub Actions runs SQLite + stub LLM on Python 3.12.

## Privacy

No telemetry. No external calls except configured sources (when `COLLECT_REAL_SOURCES=true`) and a configured LLM provider. Stub mode makes zero network calls for extraction. Align deployment with Saudi PDPL for production hosting.

## Next steps (toward slide 14 target stack)

- Wire a real LLM provider behind the same interface with strict JSON schema validation.
- Enable live collectors with robots/ToS-aware fetching and Iceberg-style history when the platform grows.
- Calibrate source class priors on a larger resolved set; replace FD sensitivities with analytic forms where taxonomy allows.
- Optional PyMC hierarchical source model; stronger χ² / replication-aware dependence.
- Auth’d dashboard and multi-question workspace.

## Repo layout

```
src/data_ia/     package (math, agents, db, llm, dashboard, scheduler, cli)
config/          taxonomy + source class priors
seeds/           Starlink seed + synthetic resolved set
tests/           pytest (maths, controller, offline cycle)
scripts/         offline cycle helper
docker-compose.yml   pgvector Postgres
```
