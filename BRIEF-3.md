# Data IA – Pass 3 brief: honest proof, frozen forecasts, real target question

Passes 1-2 are on `main` (local commits up to 03d0299). This pass makes the proof honest and auditable, fixes the Controller, and prepares the real target question. Spec of reference: the technical deck v3 (slides 1-14). Environment: Windows, Python 3.14, no Docker, SQLite by default. Keep every existing test green, mock all HTTP in tests, never commit keys, commit in logical commits on `main`, **do not push**.

## 1. Frozen forecast registry (append-only)
- New table `forecast_registry`, append-only (no UPDATE/DELETE in code; a DB trigger on SQLite/Postgres rejects them): `id`, `question_id`, `forecast_at`, `data_cutoff`, `git_commit`, `config_hash` (taxonomy + priors + source registry), `extractor_version`, `observation_ids` (JSON list), `probability`, `interval_low`, `interval_high`, `data_label` (REAL | SYNTHETIC), `sha256` of the canonical JSON of all the other fields.
- Every cycle writes one row. A second cycle on the same day adds a row; it never overwrites (today `pipeline.py` overwrites the daily snapshot: fix it).
- CLI `python -m data_ia.cli verify-registry` recomputes every hash and fails on any mismatch.
- CLI `python -m data_ia.cli replay --forecast-id <id>` re-runs the engine from the stored observation ids and config and checks it reproduces the stored probability.

## 2. No look-ahead
- Every observation carries `published_at`. A forecast may only use observations with `published_at <= data_cutoff <= forecast_at`; the pipeline refuses otherwise.
- Source error statistics (bias, variance, precision) used by a forecast are computed only from questions resolved **before** `forecast_at`.
- Tests that inject a future-dated observation and a resolution after `forecast_at` and assert both are rejected.

## 3. Synthetic data off by default
- The synthetic resolved set and synthetic source-error history are disabled by default (`USE_SYNTHETIC=false`).
- When `COLLECT_REAL_SOURCES=true`, synthetic data is blocked outright, even if the flag is set (hard error, not a warning).
- Every row in resolved questions, source errors, observations and forecasts has a `data_label` REAL | SYNTHETIC. Any scoring or fusion batch mixing labels is refused.

## 4. Proof that measures the engine (slide 9)
- `data-ia brier` scores forecasts **read from the registry** (produced by the engine), not probabilities written in a YAML. Remove the hand-written `probability` field from scoring paths.
- Naive baseline = base rate of the question class (from resolved questions before `forecast_at`), with status quo as an alternative for "will X change" questions; not 0.5.
- Report: Brier, baseline Brier, Brier Skill Score `BSS = 1 - Brier/Brier_baseline`, 95% interval of the Brier difference by paired bootstrap (seeded), reliability/calibration table (bins), and n.
- Below a minimum n (config, default 30), the output says "non interprétable" and shows no verdict.
- Keep the ILLUSTRATIVE/SYNTHETIC disclaimer whenever any synthetic label is involved.

## 5. Controller fixes
- χ² consistency: today the statistic compares values with their own mean, so it always equals n and never rejects (`controller_rules.py` ~L152-166). Replace with `Σ_s (z_s - b_s - x̂)² / σ_s²` using the source reliability (bias, variance) from the source model, x̂ the precision-weighted fused value, df = n-1.
- A leaf with a single observation is not quarantined by the χ² rule (it is accepted with a "single source" flag).
- Rewrite `test_chi2_quarantines_outliers` so it actually asserts quarantine on a clear outlier and acceptance on a consistent set.
- Make the `non_finite` branch reachable or remove it.

## 6. Computable question (slide 2) and extraction fields (slide 4)
- Question schema gets `target_variable` (Y), `threshold`, `horizon`, `zone`, `unit`, `resolution_source`, `resolution_rule`. The Orchestrator refuses a question missing any of them.
- Extractions (stub included) return value, unit, date (`published_at`) and the source passage; the Controller requires them and checks the unit against the question.

## 7. New target question (empty config)
- Add `seeds/ksa_nonoil_growth_2027.yaml` with the exact question text: "Will Saudi real non-oil activities grow by at least 4.5% in 2027, according to GASTAT's first estimate of 2027 annual real GDP?" (Y = real growth of non-oil activities 2027 vs 2026, threshold = 4.5%, horizon = GASTAT's first estimate of 2027 annual real GDP, zone = KSA, unit = percent, resolution source = GASTAT first annual estimate; the 4.5% threshold is anchored on the IMF Article IV forecast of July 2026). Fill the slide-2 fields; leave the sub-question tree **empty** with a clear `TODO: tree provided by the Product team` comment. The Orchestrator must report it as "not ready" (no forecast) while the tree is empty. Do not invent the tree.
- Keep the current illustrative macro seed as default until the tree lands.

## 8. Source registry merge and priors mapping
- `config/sources_verified.yaml` (provided, 10 sources, verified Nov 18 2026) is the reference. Merge it with the pass 2 `config/sources.yaml` into one registry; keep `[à confirmer]` markers as they are; fields: name, url, class, reliability_prior, access, key_required, license, update_frequency, priority, connector (if any).
- `reliability_prior` is a score in [0,1]; the source model needs a prior bias and variance per class. Add an explicit, configurable mapping `config/prior_mapping.yaml` from score to prior variance (monotonic decreasing in the score) and prior bias (0 by default), plus the shrinkage constant N0. Values in that file are marked `PROVISIONAL – pending validation by the model owner`; do not present them as calibrated. Document the mapping in the README.
- Test: the mapping is monotonic and the loader rejects a non-monotonic table.
- No connector for open.data.gov.sa (no documented public API; do not use its internal routes). SAMA stays skipped.

## 9. GASTAT extraction
- The live GASTAT call returns HTTP 200 but 0 parsed records. Inspect the real payload (save one sanitised sample as a new fixture), map it to series (indicator id, period, value, unit, published date), and add a test on that fixture. Only use the official developer portal routes; respect robots.txt (`Disallow: /api/` on www.stats.gov.sa).
- CMA: add a configurable timeout and a clear "live_failed" status; keep the fixture fallback labelled as such (never counted as REAL).

## 10. Hygiene
- Add `.streamlit/config.toml` with `browser.gatherUsageStats = false` (Streamlit sends usage stats by default: not acceptable under PDPL).
- `collect` output reports the number of parsed records per source.
- Edge-case tests: empty batch, n below minimum, all-same outcomes, probability exactly 0 or 1, NaN/Inf, duplicated observation ids, hash tampering, mixed labels.

## Done means
- `pytest` green offline (Python 3.14), including the new tests above.
- `cycle` twice in a row writes two registry rows; `verify-registry` passes; editing one row by hand makes it fail; `replay` reproduces the probability.
- `brier` reads the registry, shows BSS, bootstrap interval, calibration bins and "non interprétable" below the minimum n.
- With `COLLECT_REAL_SOURCES=true` and `USE_SYNTHETIC=true`, the run refuses to start.
- `collect --source gastat` live returns > 0 parsed records, or the summary explains exactly why not.
- README updated (registry, proof method, look-ahead rules, priors mapping marked provisional, sources table).
- Print a short summary at the end: what works live, what failed and why, test counts.
