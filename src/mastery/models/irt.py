"""Item Response Theory (2PL).

Gives every question a difficulty and a discrimination, and every learner an ability.
Used for two things here: cold start (a brand-new learner has no history, so fall back
to the population prior) and sensible difficulty buckets for the tutor.
"""

from __future__ import annotations

import math


def p_correct_2pl(ability: float, difficulty: float, discrimination: float = 1.0) -> float:
    """Logistic 2PL: P(correct) = sigma(a * (theta - b))."""
    z = discrimination * (ability - difficulty)
    z = max(min(z, 35.0), -35.0)  # keep exp() out of overflow territory
    return 1.0 / (1.0 + math.exp(-z))


def ability_from_mastery(mastery: float) -> float:
    """Map a mastery probability in (0,1) onto the IRT ability (logit) scale."""
    m = min(max(mastery, 1e-4), 1 - 1e-4)
    return math.log(m / (1 - m))


def difficulty_for_target(ability: float, target_p: float, discrimination: float = 1.0) -> float:
    """Which difficulty puts this learner at `target_p` chance of success?

    This is the whole 'desirable difficulty' idea in one line: solve the 2PL for b.
    """
    t = min(max(target_p, 1e-4), 1 - 1e-4)
    return ability - math.log(t / (1 - t)) / max(discrimination, 1e-6)
