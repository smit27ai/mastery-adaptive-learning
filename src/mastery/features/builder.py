"""THE shared feature module.

Training and serving must both import this file. If features are computed one way in a
notebook and another way in the API, the model silently degrades and nothing errors.
That failure mode is called train/serve skew and it is the single most common way an
ML project dies after deployment.

Everything here is pure: given a history of interactions, produce a feature dict.
No database access, no I/O, no globals.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

FEATURE_NAMES: list[str] = [
    "total_attempts",
    "overall_accuracy",
    "concept_attempts",
    "concept_accuracy",
    "rolling_accuracy_5",
    "rolling_accuracy_10",
    "current_streak",
    "mean_response_time_ms",
    "response_time_zscore",
    "hint_rate",
    "hours_since_last_attempt",
    "hours_since_concept_seen",
    "attempts_this_session",
    "item_difficulty",
    "item_discrimination",
    "item_p_value",
]


@dataclass(frozen=True)
class Interaction:
    """One past attempt, in the shape both the trainer and the API can produce."""

    question_id: int
    concept_id: int
    is_correct: bool
    response_time_ms: int
    hints_used: int
    created_at: datetime


@dataclass(frozen=True)
class ItemMeta:
    """Static properties of the question being scored."""

    question_id: int
    concept_id: int
    irt_difficulty: float = 0.0
    irt_discrimination: float = 1.0
    p_value: float = 0.5


def _accuracy(rows: list[Interaction]) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if r.is_correct) / len(rows)


def _streak(rows: list[Interaction]) -> int:
    """Signed run length: +3 means three correct in a row, -2 two wrong in a row."""
    if not rows:
        return 0
    latest = rows[-1].is_correct
    count = 0
    for row in reversed(rows):
        if row.is_correct != latest:
            break
        count += 1
    return count if latest else -count


def as_utc(value: datetime) -> datetime:
    """Coerce a timestamp to timezone-aware UTC.

    SQLite hands back naive datetimes even for a timezone-aware column, and Parquet
    exports often drop the zone too. Normalising here means the same feature code works
    against the dev database, the prod database, and an offline training file.
    """
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _hours_between(later: datetime, earlier: datetime) -> float:
    delta: timedelta = as_utc(later) - as_utc(earlier)
    return max(delta.total_seconds() / 3600.0, 0.0)


def build_features(
    history: list[Interaction],
    item: ItemMeta,
    *,
    now: datetime | None = None,
    session_attempts: int = 0,
) -> dict[str, float]:
    """Build the feature vector for 'will this learner answer `item` correctly?'.

    `history` must be sorted oldest-first and must contain only attempts made *before*
    the item being scored. Passing in later attempts is target leakage.
    """
    now = as_utc(now) if now else datetime.now(UTC)
    history = sorted(history, key=lambda r: as_utc(r.created_at))
    concept_rows = [r for r in history if r.concept_id == item.concept_id]

    times = [r.response_time_ms for r in history if r.response_time_ms > 0]
    mean_rt = sum(times) / len(times) if times else 0.0
    if len(times) > 1:
        var = sum((t - mean_rt) ** 2 for t in times) / (len(times) - 1)
        std_rt = math.sqrt(var)
    else:
        std_rt = 0.0
    last_rt = history[-1].response_time_ms if history else 0
    rt_z = (last_rt - mean_rt) / std_rt if std_rt > 1e-9 else 0.0

    features = {
        "total_attempts": float(len(history)),
        "overall_accuracy": _accuracy(history),
        "concept_attempts": float(len(concept_rows)),
        "concept_accuracy": _accuracy(concept_rows),
        "rolling_accuracy_5": _accuracy(history[-5:]),
        "rolling_accuracy_10": _accuracy(history[-10:]),
        "current_streak": float(_streak(history)),
        "mean_response_time_ms": mean_rt,
        "response_time_zscore": rt_z,
        "hint_rate": (sum(r.hints_used for r in history) / len(history) if history else 0.0),
        "hours_since_last_attempt": (
            _hours_between(now, history[-1].created_at) if history else -1.0
        ),
        "hours_since_concept_seen": (
            _hours_between(now, concept_rows[-1].created_at) if concept_rows else -1.0
        ),
        "attempts_this_session": float(session_attempts),
        "item_difficulty": item.irt_difficulty,
        "item_discrimination": item.irt_discrimination,
        "item_p_value": item.p_value,
    }

    # Fail loudly rather than let training and serving drift apart silently.
    assert set(features) == set(FEATURE_NAMES), "FEATURE_NAMES is out of sync with build_features"
    return features


def to_vector(features: dict[str, float]) -> list[float]:
    """Deterministic ordering. Never rely on dict insertion order across processes."""
    return [float(features[name]) for name in FEATURE_NAMES]
