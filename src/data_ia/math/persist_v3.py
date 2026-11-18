"""Probabilistic persistence v3 (P(hausse) baseline).

Reference: scripts/persist_v3.py and COORDINATION (two states: strict up / non-up;
zero = non-up). Recalculate at each data_cutoff.
"""

from __future__ import annotations

from typing import Sequence


def p_haut(
    changes: Sequence[float],
    *,
    K: int = 12,
    lo: float = 0.05,
    hi: float = 0.95,
) -> tuple[float, str]:
    """Persistence-v3 P(next is a strict rise) from recent signed changes.

    Returns (probability, method_detail). Uses at most the last ``K`` changes.
    Fewer than 3 observations → 0.5 with written justification tag.
    """
    if K < 1:
        raise ValueError("K must be >= 1")
    c = list(changes)[-K:]
    st = [1 if x > 0 else 0 for x in c]
    m = len(st)
    h = sum(st)
    if m < 3:
        return 0.5, "0,5 + justification (m<3)"
    f = (h + 1) / (m + 2)
    n = m - 1
    if n < 6:
        p = min(hi, max(lo, f))
        return p, f"f f={f:.6f}"
    d = st[-1]
    nd = sum(1 for i in range(n) if st[i] == d)
    ud = sum(1 for i in range(n) if st[i] == d and st[i + 1] == 1)
    raw = (ud + 4 * f) / (nd + 4)
    p = min(hi, max(lo, raw))
    return p, f"markov nd={nd} ud={ud} f={f:.6f} raw={raw:.6f}"


def historical_frequency(
    events: Sequence[int],
    *,
    default: float = 0.5,
) -> tuple[float, str]:
    """Laplace-smoothed frequency of binary events (1 = event occurred)."""
    if not events:
        return default, "0,5 + justification (no history)"
    k = sum(1 for e in events if int(e) == 1)
    n = len(events)
    p = (k + 1) / (n + 2)
    return float(p), f"frequency_laplace k={k} n={n}"
