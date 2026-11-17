"""Shared numerical constants for the maths layer."""

from __future__ import annotations

# Floor used when clipping probabilities away from {0, 1} for logit / fusion.
# Single shared value — do not mix 1e-6 and 1e-12 elsewhere.
PROB_EPS = 1e-12
