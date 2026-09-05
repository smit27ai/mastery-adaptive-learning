"""Tutor policy tests.

The property that matters: the policy must aim at the target success rate, not at the
easiest item. If these pass, the RL component is doing something defensible.
"""

from mastery.models.bandit import (
    Candidate,
    TutorPolicy,
    bucket_of,
    learning_gain,
    shaped_reward,
)


def candidates() -> list[Candidate]:
    return [
        Candidate(question_id=1, concept_id=1, difficulty=-2.5, predicted_p_correct=0.97),
        Candidate(question_id=2, concept_id=1, difficulty=-0.5, predicted_p_correct=0.70),
        Candidate(question_id=3, concept_id=1, difficulty=2.5, predicted_p_correct=0.08),
    ]


def test_learning_gain_peaks_at_target() -> None:
    assert learning_gain(0.7, 0.7) == 1.0
    assert learning_gain(0.97, 0.7) < 0.2
    assert learning_gain(0.05, 0.7) < 0.2


def test_greedy_picks_the_sweet_spot_not_the_easiest() -> None:
    chosen, policy, _ = TutorPolicy(policy="greedy").select(candidates())
    assert chosen.question_id == 2
    assert policy == "greedy"


def test_thompson_is_deterministic_under_a_fixed_seed() -> None:
    a = TutorPolicy(policy="thompson", seed=7).select(candidates())[0]
    b = TutorPolicy(policy="thompson", seed=7).select(candidates())[0]
    assert a.question_id == b.question_id


def test_thompson_usually_lands_near_the_target() -> None:
    hits = sum(
        TutorPolicy(policy="thompson", seed=s).select(candidates())[0].question_id == 2
        for s in range(60)
    )
    assert hits >= 45  # exploration is allowed, but exploitation should dominate


def test_frustration_penalty_applies_on_a_losing_streak() -> None:
    calm = shaped_reward(0.7, 0.7, streak=0)
    frustrated = shaped_reward(0.7, 0.7, streak=-5)
    assert frustrated < calm


def test_boredom_penalty_applies_on_a_long_winning_streak() -> None:
    assert shaped_reward(0.7, 0.7, streak=8) < shaped_reward(0.7, 0.7, streak=0)


def test_bucket_mapping_is_bounded() -> None:
    assert bucket_of(-99.0) == 0
    assert bucket_of(99.0) == 4
    assert 0 <= bucket_of(0.0) <= 4


def test_posterior_update_shifts_the_mean() -> None:
    policy = TutorPolicy(policy="thompson", seed=1)
    bucket = bucket_of(0.0)
    before = policy.buckets[bucket].mean()
    policy.update(0.0, learned=True)
    assert policy.buckets[bucket].mean() > before


def test_empty_candidate_list_is_rejected() -> None:
    try:
        TutorPolicy().select([])
    except ValueError:
        return
    raise AssertionError("select() must reject an empty candidate list")


def test_explanation_does_not_claim_the_sweet_spot_when_it_is_not() -> None:
    """The learner reads this string; it must not misdescribe the item it picked."""
    policy = TutorPolicy(target_success_rate=0.7)

    at_target = policy.explain(
        Candidate(question_id=1, concept_id=1, difficulty=0.0, predicted_p_correct=0.70)
    )
    assert "fastest" in at_target

    too_hard = policy.explain(
        Candidate(question_id=2, concept_id=1, difficulty=2.0, predicted_p_correct=0.32)
    )
    assert "harder" in too_hard
    assert "fastest" not in too_hard

    too_easy = policy.explain(
        Candidate(question_id=3, concept_id=1, difficulty=-2.0, predicted_p_correct=0.95)
    )
    assert "easier" in too_easy
    assert "fastest" not in too_easy
