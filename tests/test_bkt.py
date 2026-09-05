"""BKT behaviour tests.

These assert the *properties* the model must have, not hardcoded numbers - so they keep
holding when the parameters are refitted on real data.
"""

import pytest

from mastery.models import bkt
from mastery.models.bkt import BKTParams


def test_correct_answer_raises_mastery() -> None:
    params = BKTParams()
    assert bkt.update(0.3, correct=True, params=params) > 0.3


def test_wrong_answer_lowers_posterior_before_learning() -> None:
    params = BKTParams(prior=0.5, learn=0.0, slip=0.1, guess=0.2)
    # With learn=0 there is no transition, so a wrong answer must strictly reduce mastery.
    assert bkt.update(0.5, correct=False, params=params) < 0.5


def test_mastery_stays_in_unit_interval() -> None:
    params = BKTParams()
    mastery = params.prior
    for correct in [True, False, True, True, False, True] * 20:
        mastery = bkt.update(mastery, correct, params)
        assert 0.0 <= mastery <= 1.0


def test_repeated_success_converges_upward() -> None:
    params = BKTParams()
    assert bkt.replay([True] * 12, params) > 0.9


def test_repeated_failure_stays_low() -> None:
    params = BKTParams()
    assert bkt.replay([False] * 12, params) < 0.35


def test_predict_correct_is_monotone_in_mastery() -> None:
    params = BKTParams()
    values = [bkt.predict_correct(m / 10, params) for m in range(11)]
    assert values == sorted(values)


def test_predict_bounded_by_slip_and_guess() -> None:
    params = BKTParams(slip=0.1, guess=0.2)
    assert bkt.predict_correct(0.0, params) == pytest.approx(0.2)
    assert bkt.predict_correct(1.0, params) == pytest.approx(0.9)


def test_degenerate_params_are_clamped() -> None:
    # slip + guess >= 1 makes answers anti-informative; validated() must prevent it.
    params = BKTParams(slip=0.9, guess=0.9).validated()
    assert params.slip <= 0.45
    assert params.guess <= 0.45


def test_em_recovers_a_high_learning_rate() -> None:
    """Sequences that flip from wrong to right imply real learning, not guessing."""
    sequences = [[False, False, True, True, True, True] for _ in range(60)]
    fitted = bkt.fit_em(sequences, iterations=40)
    assert 0.0 < fitted.learn < 1.0
    assert fitted.slip < 0.45
    assert fitted.guess < 0.45


def test_em_is_deterministic() -> None:
    sequences = [[True, False, True], [False, True, True], [True, True, True]]
    assert bkt.fit_em(sequences) == bkt.fit_em(sequences)


def test_em_recovers_the_generating_parameters() -> None:
    """The real check on an EM implementation: simulate from known parameters, refit, compare.

    A broken M-step passes shape assertions but fails this test, so it is the one that
    matters.
    """
    import random

    rng = random.Random(0)
    true = BKTParams(prior=0.15, learn=0.25, slip=0.08, guess=0.22)

    sequences = []
    for _ in range(400):
        knows = rng.random() < true.prior
        row = []
        for _ in range(12):
            if knows:
                row.append(rng.random() > true.slip)
            else:
                row.append(rng.random() < true.guess)
                if rng.random() < true.learn:
                    knows = True
        sequences.append(row)

    fitted = bkt.fit_em(sequences, iterations=200)
    assert fitted.learn == pytest.approx(true.learn, abs=0.08)
    assert fitted.slip == pytest.approx(true.slip, abs=0.08)
    assert fitted.guess == pytest.approx(true.guess, abs=0.10)
    assert fitted.prior == pytest.approx(true.prior, abs=0.10)


def test_em_converges_early_when_parameters_stop_moving() -> None:
    sequences = [[True, True, False, True] for _ in range(30)]
    few = bkt.fit_em(sequences, iterations=500)
    many = bkt.fit_em(sequences, iterations=1000)
    assert few == many
