# Data IA – Pass 2 brief: real Saudi data sources

Version 1 is built (see README). This pass connects real sources and fixes three points. Keep everything working offline in tests (mock HTTP responses / recorded fixtures), and keep all existing tests green.

## 1. Real source connectors (Collector)
Add one connector module per source, each storing raw payload + provenance (URL, timestamp, hash, connector version) and passing Controller schema/range rules. All network access is behind the existing COLLECT_REAL_SOURCES flag; keys come from .env (never commit keys).
First batch (verified official APIs, Nov 2026):
- World Bank Indicators API (country SAU, no key) – e.g. GDP, population, mobile/internet indicators.
- IMF SDMX 3.0 data API (incl. WEO) – KSA macro series.
- UN Comtrade public API (no key, limited preview) – KSA trade flows.
- GASTAT developer portal (stats.gov.sa) – check docs; if a key is needed, read it from .env and skip gracefully if absent.
- CMA OpenDataAPIs (Capital Market Authority) – funds, licences, rating agencies.
- EIA API (free key, public domain) – KSA energy series.
Optional if docs are reachable: SAMA API. Do NOT add scraping for Umm Al-Qura, KAPSARC, Ookla, Saudi Exchange, or Etimad salary APIs (terms/PDPL issues). Respect robots.txt and rate limits; set a clear User-Agent.
Add a `sources.yaml` registry (name, url, class, access method, key required, license, update frequency, priority) and a CLI command `python -m data_ia.cli collect --source <name>` plus `collect --all`.

## 2. Question config
Remove Starlink as the default question. Make the default seed a neutral, clearly ILLUSTRATIVE KSA macro question that uses the new sources (e.g. a short-horizon indicator question), and keep the Starlink config as an optional example file only.

## 3. Correlated sources (n_eff)
In fusion, support correlated sources: n_eff = n / (1 + (n-1)*rho), with rho configurable per source group (e.g. outlets relaying the same wire). Add tests.

## 4. Hygiene
Add *.egg-info, .env, __pycache__, data/ caches to .gitignore and remove tracked egg-info if any.

## Done means
Tests pass offline; `collect --source worldbank` works live when COLLECT_REAL_SOURCES=true; README updated (sources table, how to add keys, legal notes); logical commits on main, do not push. Print a short summary at the end: what works live, what failed and why, test results.
