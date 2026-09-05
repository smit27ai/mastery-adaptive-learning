"""Feature builder tests.

The contract this file protects is train/serve parity: the vector must be complete,
ordered deterministically, and free of any information from after the scored item.
"""

from datetime import UTC, datetime, timedelta

import pytest

from mastery.features.builder import (
    FEATURE_NAMES,
    Interaction,
    ItemMeta,
    build_features,
    to_vector,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_history(pattern: list[bool], concept_id: int = 1) -> list[Interaction]:
    return [
        Interaction(
            question_id=i + 1,
            concept_id=concept_id,
            is_correct=correct,
            response_time_ms=5000 + i * 100,
            hints_used=0,
            created_at=NOW - timedelta(minutes=len(pattern) - i),
        )
        for i, correct in enumerate(pattern)
    ]


ITEM = ItemMeta(question_id=99, concept_id=1, irt_difficulty=0.5, p_value=0.6)


def test_every_declared_feature_is_produced() -> None:
    feats = build_features(make_history([True, False]), ITEM, now=NOW)
    assert set(feats) == set(FEATURE_NAMES)


def test_vector_order_is_stable() -> None:
    feats = build_features(make_history([True]), ITEM, now=NOW)
    assert to_vector(feats) == [float(feats[n]) for n in FEATURE_NAMES]
    assert len(to_vector(feats)) == len(FEATURE_NAMES)


def test_empty_history_does_not_crash() -> None:
    feats = build_features([], ITEM, now=NOW)
    assert feats["total_attempts"] == 0.0
    assert feats["overall_accuracy"] == 0.0
    # -1 is the explicit "never seen" sentinel; 0 would read as "just now".
    assert feats["hours_since_last_attempt"] == -1.0
    assert feats["hours_since_concept_seen"] == -1.0


def test_accuracy_and_streak() -> None:
    feats = build_features(make_history([True, True, False, True, True, True]), ITEM, now=NOW)
    assert feats["overall_accuracy"] == pytest.approx(5 / 6)
    assert feats["current_streak"] == 3.0


def test_negative_streak_on_wrong_run() -> None:
    feats = build_features(make_history([True, False, False]), ITEM, now=NOW)
    assert feats["current_streak"] == -2.0


def test_concept_features_isolate_the_target_concept() -> None:
    history = make_history([True, True], concept_id=1) + make_history([False], concept_id=2)
    feats = build_features(history, ITEM, now=NOW)  # ITEM is concept 1
    assert feats["concept_attempts"] == 2.0
    assert feats["concept_accuracy"] == 1.0


def test_item_metadata_flows_through() -> None:
    feats = build_features([], ITEM, now=NOW)
    assert feats["item_difficulty"] == 0.5
    assert feats["item_p_value"] == 0.6


def test_out_of_order_history_is_sorted() -> None:
    history = make_history([True, False, True])
    shuffled = [history[2], history[0], history[1]]
    assert build_features(shuffled, ITEM, now=NOW) == build_features(history, ITEM, now=NOW)


def test_rolling_windows_only_use_the_tail() -> None:
    history = make_history([False] * 20 + [True] * 5)
    feats = build_features(history, ITEM, now=NOW)
    assert feats["rolling_accuracy_5"] == 1.0
    assert feats["overall_accuracy"] < 0.3
