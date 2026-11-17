# Data IA – Pass 3b brief: bugs and minimal tests from the model review

Pass 3 (BRIEF-3.md) is committed on `main`. This short pass adds the bug fixes and minimal tests from the model review (validated by Data IA · Modèle and Data IA · Recherche, Nov 18 2026). Same constraints: Windows, Python 3.14, no Docker, SQLite default, mock all HTTP in tests, keep every test green, logical commits on `main`, **do not push**, no secrets. Do NOT implement the continuous target / Student-t predictive / common shock / NIG estimation: that is pass 4.

## 1. Default cycle must work
- `python -m data_ia.cli cycle` must run with **no environment variable set** and no `.env` file: the default seed path (`config.py` ~L35) must point to a seed that exists and loads. Add a test that clears the relevant env vars and runs the cycle end to end.

## 2. Bugs
- When every observation of a leaf is quarantined, `evaluate_taxonomy` raises an uncaught `KeyError`. Handle it: the leaf is reported as missing, the answer is marked `stale`/not publishable, no crash. Test.
- `validate_extraction_batch`: group by (sub-question, field), not by sub-question only. Test with two fields on one leaf.
- `non_finite` branch in `controller_rules.py`: make it reachable (check finiteness first) or remove it; test NaN and Inf either way.
- `leaf_history` (`pipeline.py` ~L327): sort by `as_of` and keep only `as_of < t` (strictly earlier). Test with out-of-order and same-day rows.
- `SourceError` used for source statistics: filter on resolution date (< forecast time) so backtests have no look-ahead. Test.
- Clipping: one shared epsilon constant for probabilities (today 1e-6 and 1e-12 are mixed); use it everywhere. Test that P=0 and P=1 inputs do not produce inf/NaN.

## 3. Priors mapping (provisional, config only)
- Replace the single N0 in the provisional mapping by a normal-inverse-gamma prior per source: `b0 = 0`, `kappa0 = 2`, `nu0 = 4` (must be > 2), `s0² = k(class) · sigma2_ref`, with `k` table A 0.5 / B 1 / C 1.25 / D 2. All marked `CONVENTION – PROVISIONAL, not calibrated` (sigma2_ref not yet measured). The loader rejects a non-monotone `k` table and `nu0 <= 2`.
- Align `config/source_priors.yaml` on `b0 = 0` (today 0.05 press / 0.10 social).
- Config and loader only in this pass; the NIG update itself is pass 4. Document in README.

## 4. Minimal tests on current formulas
Hand-computed cases for bias, variance, precision, shrinkage, fusion, logit aggregation and Brier, plus: N=0, N=1, single source, identical readings, exact copies of one source (with n_eff: k copies must not shrink the variance as if independent; document current behaviour if it does and mark it xfail for pass 4), heterogeneous precisions, missing rho for a group (error), tau = 0, probabilities 0 and 1, finite differences for sensitivities.

## Done means
`pytest` green offline (count reported), `cycle` works with a clean environment, README notes the provisional priors mapping. Print a short summary at the end: fixed bugs, new test count, anything left for pass 4.
