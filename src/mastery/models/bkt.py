"""Bayesian Knowledge Tracing.

A two-state hidden Markov model per concept. The learner is either in the "knows it"
state or the "does not know it" state; we never observe which, we only observe
correct/incorrect answers. Four parameters per concept:

    prior  P(knows it before any practice)
    learn  P(transition from not-knowing to knowing after one attempt)
    slip   P(answers wrong | knows it)
    guess  P(answers right | does not know it)

Interpretable, cheap, and it always works - which is why it is the last line in the
inference fallback chain.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BKTParams:
    prior: float = 0.25
    learn: float = 0.15
    slip: float = 0.10
    guess: float = 0.20

    def validated(self) -> BKTParams:
        clamp = lambda x: min(max(x, 1e-4), 1 - 1e-4)  # noqa: E731
        return BKTParams(
            prior=clamp(self.prior),
            learn=clamp(self.learn),
            # slip + guess >= 1 makes the model degenerate (answers become anti-informative)
            slip=clamp(min(self.slip, 0.45)),
            guess=clamp(min(self.guess, 0.45)),
        )


def predict_correct(mastery: float, params: BKTParams) -> float:
    """P(next answer correct) given current mastery."""
    p = params.validated()
    return mastery * (1 - p.slip) + (1 - mastery) * p.guess


def update(mastery: float, correct: bool, params: BKTParams) -> float:
    """One Bayesian update: posterior after seeing an answer, then the learning transition."""
    p = params.validated()

    if correct:
        num = mastery * (1 - p.slip)
        den = num + (1 - mastery) * p.guess
    else:
        num = mastery * p.slip
        den = num + (1 - mastery) * (1 - p.guess)

    posterior = num / den if den > 1e-12 else mastery
    # The attempt itself is a learning opportunity.
    return posterior + (1 - posterior) * p.learn


def replay(sequence: list[bool], params: BKTParams) -> float:
    """Run a whole history through the model. Used to rebuild state after a cache miss."""
    p = params.validated()
    mastery = p.prior
    for correct in sequence:
        mastery = update(mastery, correct, p)
    return mastery


def _forward_backward(
    seq: list[bool], p: BKTParams
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Standard HMM forward-backward over the two latent states (0=unknown, 1=known).

    Returns (gamma, xi_unknown_to_known) where
        gamma[t] = (P(unknown at t), P(known at t))  given the whole sequence
        xi[t]    = (P(unknown at t and unknown at t+1), P(unknown at t and known at t+1))

    Alphas are normalised at each step, which keeps long sequences out of underflow.
    """
    n = len(seq)
    # Emission: probability of the observation given each latent state.
    emit = [((p.guess if c else 1 - p.guess), ((1 - p.slip) if c else p.slip)) for c in seq]

    alpha: list[tuple[float, float]] = []
    a0, a1 = (1 - p.prior) * emit[0][0], p.prior * emit[0][1]
    scale = a0 + a1 or 1e-300
    alpha.append((a0 / scale, a1 / scale))
    for t in range(1, n):
        prev0, prev1 = alpha[-1]
        # No forgetting: once known, always known.
        a0 = prev0 * (1 - p.learn) * emit[t][0]
        a1 = (prev0 * p.learn + prev1) * emit[t][1]
        scale = a0 + a1 or 1e-300
        alpha.append((a0 / scale, a1 / scale))

    beta: list[tuple[float, float]] = [(1.0, 1.0)] * n
    for t in range(n - 2, -1, -1):
        nxt0, nxt1 = beta[t + 1]
        b0 = (1 - p.learn) * emit[t + 1][0] * nxt0 + p.learn * emit[t + 1][1] * nxt1
        b1 = emit[t + 1][1] * nxt1
        scale = b0 + b1 or 1e-300
        beta[t] = (b0 / scale, b1 / scale)

    gamma: list[tuple[float, float]] = []
    for t in range(n):
        g0 = alpha[t][0] * beta[t][0]
        g1 = alpha[t][1] * beta[t][1]
        total = g0 + g1 or 1e-300
        gamma.append((g0 / total, g1 / total))

    xi: list[tuple[float, float]] = []
    for t in range(n - 1):
        stay = alpha[t][0] * (1 - p.learn) * emit[t + 1][0] * beta[t + 1][0]
        move = alpha[t][0] * p.learn * emit[t + 1][1] * beta[t + 1][1]
        known = alpha[t][1] * emit[t + 1][1] * beta[t + 1][1]
        total = stay + move + known or 1e-300
        xi.append((stay / total, move / total))

    return gamma, xi


def fit_em(
    sequences: list[list[bool]],
    *,
    iterations: int = 60,
    tol: float = 1e-6,
    init: BKTParams | None = None,
) -> BKTParams:
    """Fit the four BKT parameters by Expectation-Maximisation (Baum-Welch).

    E-step: forward-backward gives the posterior probability of being in the "knows it"
    state at every step. M-step: re-estimate the four parameters from those soft counts.

        prior = mean posterior of knowing it at t=0
        learn = expected unknown->known transitions / expected time spent unknown
        guess = expected correct answers while unknown / expected time unknown
        slip  = expected wrong answers while known / expected time known

    Iterating until the parameters stop moving is what makes this EM rather than a
    single heuristic pass.
    """
    params = (init or BKTParams()).validated()
    sequences = [s for s in sequences if s]
    if not sequences:
        return params

    for _ in range(iterations):
        prior_sum = 0.0
        learn_num = learn_den = 0.0
        slip_num = slip_den = 0.0
        guess_num = guess_den = 0.0

        for seq in sequences:
            gamma, xi = _forward_backward(seq, params)
            prior_sum += gamma[0][1]

            for t, correct in enumerate(seq):
                p_unknown, p_known = gamma[t]
                guess_den += p_unknown
                slip_den += p_known
                if correct:
                    guess_num += p_unknown
                else:
                    slip_num += p_known

            for stay, move in xi:
                learn_num += move
                learn_den += stay + move

        updated = BKTParams(
            prior=prior_sum / len(sequences),
            learn=(learn_num / learn_den) if learn_den > 1e-12 else params.learn,
            slip=(slip_num / slip_den) if slip_den > 1e-12 else params.slip,
            guess=(guess_num / guess_den) if guess_den > 1e-12 else params.guess,
        ).validated()

        moved = max(
            abs(updated.prior - params.prior),
            abs(updated.learn - params.learn),
            abs(updated.slip - params.slip),
            abs(updated.guess - params.guess),
        )
        params = updated
        if moved < tol:
            break

    return params
