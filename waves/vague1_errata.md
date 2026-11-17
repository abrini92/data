# Wave 1 — errata (vague1.yaml unchanged, SHA-256 36d214bb…52311 still valid)
Owner: Data IA · Produit. Logged 2026-11-18 (Asia/Riyadh). These are documentation errors; no question, series, threshold or deadline changes.

## E1 — G_GDP mixes two publications
- P7 resolves on GASTAT detailed quarterly national accounts Q3 2026 (deadline 2026-12-20).
- P8 and P13 resolve on GASTAT GDP flash estimate Q4 2026 (deadline 2027-02-10).
- The product page wrongly said "P7, P8 and P13 resolve on the same publication". Corrected on the page.
- Treatment for scoring: P8–P13 same publication, rho = 1; P7 vs P8/P13 linked by series only (rho 0.3 by convention, Modèle, neff_vague1.md).
- Related: G_IPI (P9, P10) groups one series across two distinct publications; P11 and P12 share the same SAMA Monthly Statistical Bulletin but are not grouped (variant computed by Modèle).

## E2 — P7 driver "calibration" is not a driver
- P7 is a revision question (flash vs detailed accounts), not a measure of any driver M1–M8.
- Treatment: P7 carries no driver loading; only the common macro floor and its series link to P8/P13 (as Modèle already did).
- Wave 2 rule: every question must name one driver M1–M8 or an explicit non-macro category; "calibration" and "all" are not allowed as drivers.

## E3 — P16 resolvability (no change to the question)
- Sources (2026-11-18, 02:32–02:35 Asia/Riyadh) found the matching indicator: Ministry of Tourism "Saudi Tourism Sector Performance" special report (Q1 2026: 8.3 M inbound, -13% YoY, published 8 Apr 2026, https://cdn.mt.gov.sa/mtweb/prod/uploads/MT_2026_Q1_Performance_Special_Report_EN_a5e19cbb34.pdf). No Q2 2026 quarterly report found; no release calendar. Q3 2026 date [to confirm].
- P16's frozen series ("Ministry of Tourism, inbound international tourists, quarterly count") covers this report. Its frozen activation rule already handles the risk: void if the Q3 2026 figure is not published before 2027-02-10. Nothing deducted (no Q2 by subtraction), nothing edited.
- Expect P16 to be void with high probability; it should not be counted in n_eff planning (Modèle's n=14 variant applies).
- From wave 2: quarterly inbound tourism is not used; M8 moves to a series with a fixed calendar (candidate: SAMA balance of payments travel receipts, to be checked by Sources).
