# Data IA – Version 1 brief

Build version 1 of "Data IA", an internal stc decision engine, in this repository.
The file `docs/Data-IA-Technical-Deck-v3.pptx` is the technical deck: read its slides and speaker notes as the spec (python-pptx is fine to extract the text). Slides 1-14 describe what to build. Slide 15 is vision only: do not build it.

## Product in brief
A question is broken into a tree of sub-questions, each with a daily dashboard, combined into one final probability.
First target question: "Probability that CST approves Starlink's residential service, open to the public, in KSA before 31 Dec 2027."
Principle: LLMs extract under control; reproducible models calculate. No LLM output enters the maths without schema and range validation.

## Version 1 stack (keep it simple)
Python 3.11+, PostgreSQL + pgvector (docker-compose), one scheduler (APScheduler or cron-style jobs), scikit-learn and PyMC where needed, a simple dashboard (Streamlit or FastAPI + minimal HTML). No Airflow, Kafka, Kubernetes or LangGraph.

## Deliverables
1. Repo structure, README with one-command local start, `.env.example` with no secrets, LLM provider behind an interface with a deterministic stub so the pipeline runs offline in tests.
2. DB schema: questions and sub-question tree, sources, observations (raw doc, extracted value, provenance: URL, timestamp, hash, extractor version), resolved questions repository, source error history, daily answer snapshots.
3. Six agents as Python jobs under the scheduler: Orchestrator, Scout, Collector, Controller (Python schema and range rules + chi-squared consistency check; rejects/quarantines), Investigator (surprise = -log P(x_t | past)), Strategist (final answer). For each: what it produces, what checks it, what happens on failure (slide 8).
4. Source model (slide 5): z_s = x + b_s + eps_s. b_s = mean(z_s,i - x_i), sigma_s^2 = mean((z_s,i - b_s - x_i)^2) from observed errors on resolved values, tau_s = 1/sigma_s^2, shrunk toward a class prior with lambda_N = N/(N+N0). Precision-weighted fusion per sub-question, logit aggregation into the final probability via a configurable taxonomy (YAML/JSON, slide 7). Sensitivities dP/dx_k.
5. Proof (slide 9): Brier score vs a naive baseline on resolved short-horizon questions, CLI command, small seeded set of resolved questions clearly labelled ILLUSTRATIVE/SYNTHETIC. Never present synthetic numbers as real.
6. Starlink KSA seed config: question, illustrative sub-question tree (labelled illustrative), a few public sources (CST site, news). Real collection may be stubbed behind a flag; say so in README.
7. Dashboard: tree, each sub-question's estimate and history, final probability with interval, source weights.
8. pytest tests for the maths (bias/variance, shrinkage, fusion, logit aggregation, Brier) and Controller rejection paths. CI config if easy.

## Done means
`docker compose up` + one command runs a full offline cycle with the stub LLM and produces a final probability and a dashboard; tests pass; README explains architecture, formula-to-code mapping, choices made where the deck is silent, and next steps toward the target stack (slide 14). No telemetry; no external calls except configured sources and the LLM provider (Saudi PDPL).
