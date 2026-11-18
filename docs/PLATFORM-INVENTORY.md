# Platform inventory (Lot 0) — what exists in the repo

Recorded 2026-11-18 against `main` at HEAD `d9ce4ea` (local). Paths are relative to the repo root. No invented tables, columns, or CLI flags.

## Baseline tests

- Command: `python -m pytest`
- Result before Lot 0/1 work: **140 passed**, 1 skipped, 1 xfailed, 0 failed (142 collected).
- Target after each lot: keep existing suite green (0 failures); new platform tests are additive.

## CLI (`src/data_ia/cli.py`, entry `data-ia` in `pyproject.toml`)

| Subcommand | Purpose (from `--help`) | Implementation |
|---|---|---|
| `cycle` | Full offline cycle (stub LLM) | `cli.py` |
| `brier` | Brier proof from `forecast_registry` vs class-rate baseline | `cli.py` → `data_ia.math.brier_match` / registry |
| `verify-registry` | Recompute `forecast_registry` hashes | `cli.py` → `forecast_registry.verify_registry` |
| `migrate-registry` | ADD COLUMN + chain genesis (Pass-3 → Pass-4); never rewrites rows | `cli.py` → `migrate_registry.migrate_registry` |
| `annotate-forecast` | Append-only annotation (e.g. TEST) without rewriting the registry row | `cli.py` → `migrate_registry.annotate_forecast` |
| `replay` | Replay engine from stored observation ids | `cli.py` → `forecast_registry.replay_forecast` |
| `import-waves` | Import vague1/vague1b after SHA-256 verification (`--verify-only` available) | `cli.py` → `wave_import` |
| `freeze` | Freeze one proof question into the registry | `cli.py` → `freeze.freeze_question` |
| `agents` | Describe the six agents | `cli.py` |
| `dashboard` | Print Streamlit launch command | `cli.py` |
| `collect` | Collect from a registered source | `cli.py` |
| `sources` | List `sources.yaml` registry | `cli.py` |

Notable flags (from `--help`, not invented):

- `freeze`: `--question`, `--probability`, `--data-cutoff`, `--forecast-at`, `--series`, `--vintage-sha`, `--series-changes`, `--event-history`, `--baseline-method {persist_v3,frequency,0.5}`, `--p-base`, `--baseline-justification`, `--label`, `--wave`, `--database-url`, `--chain-head`, `--allow-dirty`
- `migrate-registry`: `--db`, `--dry-run`
- `annotate-forecast`: `--id`, `--label`, `--reason`
- `import-waves`: `--wave` (repeatable), `--verify-only`
- `brier`: `--path`, `--min-n`
- `replay`: `--forecast-id`

No `ui` / `ui-user` commands yet (planned in later lots).

## Forecast registry schema

Model: `src/data_ia/db/models.py` (`ForecastRegistry`, table `forecast_registry`).

Columns present in code:

| Column | Notes |
|---|---|
| `id` | PK, autoincrement |
| `question_id` | FK → `questions.id` |
| `forecast_at`, `data_cutoff` | timezone-aware DateTime |
| `git_commit`, `config_hash`, `extractor_version` | integrity metadata |
| `observation_ids` | JSON |
| `probability`, `interval_low`, `interval_high` | floats |
| `data_label` | string |
| `prev_sha256` | Pass 4 / BRIEF-4b (`REGISTRY_PASS4_COLUMNS`) |
| `p_base`, `baseline_method` | Pass 4 |
| `series_id`, `vintage_sha256`, `observations_content_hash`, `seed_hash`, `wave_id` | Pass 4 |
| `sha256` | row content hash |
| `created_at` | server default |

Pass-4 column list constant: `REGISTRY_PASS4_COLUMNS` in `src/data_ia/db/models.py`.
Genesis markers: `CHAIN_GENESIS_QUESTION_ID`, `CHAIN_GENESIS_METHOD` in the same file.
Append-only triggers: `install_forecast_registry_triggers` in `src/data_ia/db/models.py`.

Legacy (Pass-3) open helper for tests: `migrate_registry.open_legacy_sqlite_schema` in `src/data_ia/migrate_registry.py`.

## Annotations table

Model: `ForecastAnnotation` in `src/data_ia/db/models.py`, table `forecast_annotations`.

| Column | Notes |
|---|---|
| `id` | PK |
| `forecast_id` | FK → `forecast_registry.id` |
| `label` | e.g. `TEST` |
| `reason` | text |
| `created_at` | timezone-aware |

Written only via `annotate_forecast` (`src/data_ia/migrate_registry.py`), never by rewriting registry rows.

## Chain verification

- Hash / verify: `src/data_ia/forecast_registry.py` — `verify_registry`, `export_chain_head`, `read_chain_head`, `forecast_sha256` / legacy via `src/data_ia/math/registry_hash.py`
- CLI exit: `0` if `report["ok"]` else `1` (`cmd_verify_registry` in `src/data_ia/cli.py`)
- Report keys (from `verify_registry` return): `ok`, `n`, `legacy_n`, `legacy_ids`, `genesis_id`, `mismatches`, `chain_breaks`, `id_gaps`, `head_mismatch`, `annotations`

## Exported chain head

- Default path: `data/registry_chain_head.jsonl`
- Config field: `Settings.registry_chain_head_path` / env `REGISTRY_CHAIN_HEAD_PATH` in `src/data_ia/config.py`
- Writers: `export_chain_head` in `src/data_ia/forecast_registry.py`; also used by `migrate_registry` and `freeze`

## Freeze calendar

- Config file: `config/freeze_calendar.yaml`
- Loader: `src/data_ia/freeze_calendar.py` (`load_freeze_calendar`, `freeze_deadline_for`, `assert_before_freeze_deadline`)
- Settings path: `Settings.freeze_calendar_path` / `FREEZE_CALENDAR_PATH` in `src/data_ia/config.py`
- Deadlines in the YAML (Riyadh offsets as stored): P17, P1, P7, P3, P9, P5, P11–P15, P10, P6, P8, P13, P16

## Waves

- Directory: `waves/` (do not modify; `*.sha256` sidecars must stay untouched)
- Import / verify: `src/data_ia/wave_import.py` (`verify_wave_hash`, `load_wave`, `import_waves`)
- Known frozen names in repo history / COORDINATION: `vague1`, `vague1b` (and bases / errata siblings)

## Database access (CLI / engine)

- Engine factory: `src/data_ia/db/session.py` — `get_engine`, `init_db`, `get_session`, `try_init_db`, `reset_engine`
- Default SQLite URL: `sqlite:///{REPO_ROOT}/data/dataia.db` (`src/data_ia/config.py`)
- **Production DB path to never write from UI:** `data/dataia.db`
- Platform will use a **separate** read-only adapter (`mode=ro` + `PRAGMA query_only=ON`); not yet present before Lot 1

## Settings / secrets

- `src/data_ia/config.py` — `Settings`, `SETTINGS_ERROR_MESSAGE`, `settings_error_public_message`
- Example env: `.env.example` (no real secrets)
- `.env` is gitignored

## Streamlit (legacy)

- `dashboard` CLI prints a Streamlit launch command; port default `DASHBOARD_PORT=8501` in `src/data_ia/config.py`
- Platform UI port must not collide (planned default ≠ 8501)

## Recent commits (context)

```
d9ce4ea Add BRIEF-4b and export production chain genesis head.
223d87f Add BRIEF-4b tests for migrate, verify, and TEST exclusion.
5b5fe39 Add migrate-registry, dual-hash verify, and annotate-forecast.
8930b8a Add Priority 0 end-to-end tests for freeze, chain, waves, B1/B5.
61e9b3b Implement Pass 4 Priority 0: freeze, chained registry, waves, brier guards.
```

## Gaps for the platform (Lots 1+)

- No `data_ia.platform` package yet
- No FastAPI / Jinja2 extra `[ui]` yet (added in Lot 0 scaffolding)
- No read-only DB adapter, no `/api/v1`, no local auth, no HTML screens
