"""The learning loop, kept out of the router so it can be unit-tested without HTTP.

Two operations matter:
    choose_next_question - infer mastery, score candidates, let the bandit choose
    record_answer        - persist the attempt, update mastery, check for anomalies
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mastery.common.config import get_settings
from mastery.common.logging import get_logger
from mastery.db.base import (
    AnomalyFlag,
    Attempt,
    Concept,
    MasterySnapshot,
    PredictionLog,
    Question,
)
from mastery.db.cache import cache
from mastery.features.builder import Interaction, ItemMeta, as_utc, build_features
from mastery.models import anomaly, bkt
from mastery.models.bandit import Candidate, TutorPolicy
from mastery.models.registry import registry

log = get_logger(__name__)

MASTERY_TTL = 3600
CANDIDATE_POOL = 12


def params_of(concept: Concept) -> bkt.BKTParams:
    return bkt.BKTParams(
        prior=concept.bkt_prior,
        learn=concept.bkt_learn,
        slip=concept.bkt_slip,
        guess=concept.bkt_guess,
    ).validated()


def streak_of(history: list[Interaction]) -> int:
    """Signed run length of the most recent outcome."""
    if not history:
        return 0
    latest = history[-1].is_correct
    count = 0
    for row in reversed(history):
        if row.is_correct != latest:
            break
        count += 1
    return count if latest else -count


async def load_history(db: AsyncSession, user_id: int, limit: int = 200) -> list[Interaction]:
    result = await db.execute(
        select(Attempt)
        .where(Attempt.user_id == user_id)
        .order_by(Attempt.created_at.desc(), Attempt.id.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    return [
        Interaction(
            question_id=r.question_id,
            concept_id=r.concept_id,
            is_correct=r.is_correct,
            response_time_ms=r.response_time_ms,
            hints_used=r.hints_used,
            created_at=as_utc(r.created_at),
        )
        for r in reversed(rows)
    ]


async def all_concepts(db: AsyncSession) -> list[Concept]:
    result = await db.execute(select(Concept).order_by(Concept.id))
    return list(result.scalars().all())


async def get_mastery_map(
    db: AsyncSession, user_id: int, concepts: list[Concept]
) -> dict[int, float]:
    """Current mastery per concept.

    Cache first. On a miss, rebuild from the attempt log by replaying BKT, which is why
    `attempts` must stay append-only: it is the only thing that cannot be regenerated.
    """
    key = f"mastery:{user_id}"
    cached = await cache.get_json(key)
    if cached:
        return {int(k): float(v) for k, v in cached.items()}

    history = await load_history(db, user_id)
    by_concept: dict[int, list[bool]] = {}
    for row in history:
        by_concept.setdefault(row.concept_id, []).append(row.is_correct)

    mastery = {c.id: bkt.replay(by_concept.get(c.id, []), params_of(c)) for c in concepts}
    await cache.set_json(key, {str(k): v for k, v in mastery.items()}, MASTERY_TTL)
    return mastery


async def invalidate_mastery(user_id: int) -> None:
    await cache.delete(f"mastery:{user_id}")


async def choose_next_question(
    db: AsyncSession, user_id: int, *, session_id: str | None = None
) -> tuple[Question, Concept, dict[int, float], float, str, str]:
    """Return (question, concept, mastery map, predicted p_correct, policy name, reason)."""
    settings = get_settings()
    concepts = await all_concepts(db)
    if not concepts:
        raise LookupError("No concepts seeded. Run `make seed`.")

    history = await load_history(db, user_id)
    mastery = await get_mastery_map(db, user_id, concepts)
    concept_by_id = {c.id: c for c in concepts}

    # Avoid immediately repeating anything from the last few questions.
    recent_ids = {r.question_id for r in history[-5:]}
    result = await db.execute(select(Question).order_by(func.random()).limit(CANDIDATE_POOL * 3))
    pool = list(result.scalars().all())
    if not pool:
        raise LookupError("No questions seeded. Run `make seed`.")
    filtered = [q for q in pool if q.id not in recent_ids]
    pool = (filtered or pool)[:CANDIDATE_POOL]

    now = datetime.now(UTC)
    # "This sitting" proxy: attempts in the last hour. Fatigue and momentum both show up
    # on that timescale, and it needs no session join.
    session_attempts = sum(
        1 for r in history if (now - as_utc(r.created_at)).total_seconds() <= 3600
    )

    candidates: list[Candidate] = []
    feature_cache: dict[int, dict[str, float]] = {}
    for q in pool:
        item = ItemMeta(
            question_id=q.id,
            concept_id=q.concept_id,
            irt_difficulty=q.irt_difficulty,
            irt_discrimination=q.irt_discrimination,
            p_value=q.p_value,
        )
        feats = build_features(history, item, now=now, session_attempts=session_attempts)
        feature_cache[q.id] = feats
        probability, _model_used = registry.predict(
            feats,
            mastery.get(q.concept_id, 0.25),
            params_of(concept_by_id[q.concept_id]),
        )
        candidates.append(
            Candidate(
                question_id=q.id,
                concept_id=q.concept_id,
                difficulty=q.irt_difficulty,
                predicted_p_correct=probability,
            )
        )

    policy = TutorPolicy(
        target_success_rate=settings.target_success_rate,
        exploration_rate=settings.exploration_rate,
        policy="thompson",
    )
    chosen, policy_name, reason = policy.select(candidates, streak=streak_of(history))
    question = next(q for q in pool if q.id == chosen.question_id)

    # Log the prediction with the exact features that produced it. Without this row there
    # is no drift detection and no retraining signal later.
    db.add(
        PredictionLog(
            user_id=user_id,
            question_id=question.id,
            model_version=registry.version,
            policy=policy_name,
            features=feature_cache[question.id],
            predicted_prob=chosen.predicted_p_correct,
        )
    )
    await db.commit()

    return (
        question,
        concept_by_id[question.concept_id],
        mastery,
        chosen.predicted_p_correct,
        policy_name,
        reason,
    )


async def record_answer(
    db: AsyncSession,
    user_id: int,
    question: Question,
    concept: Concept,
    *,
    answer: str,
    response_time_ms: int,
    hints_used: int,
    session_id: str | None,
) -> tuple[bool, float, float, str | None]:
    """Return (correct, mastery_before, mastery_after, anomaly_type)."""
    correct = answer.strip().casefold() == question.correct_answer.strip().casefold()
    history = await load_history(db, user_id)
    params = params_of(concept)

    concept_history = [r.is_correct for r in history if r.concept_id == concept.id]
    mastery_before = bkt.replay(concept_history, params)
    mastery_after = bkt.update(mastery_before, correct, params)

    db.add(
        Attempt(
            user_id=user_id,
            question_id=question.id,
            concept_id=concept.id,
            session_id=session_id,
            is_correct=correct,
            response_time_ms=response_time_ms,
            hints_used=hints_used,
        )
    )
    db.add(
        MasterySnapshot(
            user_id=user_id,
            concept_id=concept.id,
            mastery_prob=mastery_after,
            model_version=registry.version,
        )
    )

    latest = Interaction(
        question_id=question.id,
        concept_id=concept.id,
        is_correct=correct,
        response_time_ms=response_time_ms,
        hints_used=hints_used,
        created_at=datetime.now(UTC),
    )
    flag = anomaly.detect([*history, latest], latest)
    flag_type: str | None = None
    if flag is not None:
        flag_type, severity, evidence = flag
        db.add(AnomalyFlag(user_id=user_id, type=flag_type, severity=severity, evidence=evidence))

    # Close the loop on the prediction we logged when this question was served.
    pending = (
        await db.execute(
            select(PredictionLog)
            .where(
                PredictionLog.user_id == user_id,
                PredictionLog.question_id == question.id,
                PredictionLog.actual_outcome.is_(None),
            )
            .order_by(PredictionLog.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if pending is not None:
        pending.actual_outcome = correct

    await db.commit()
    await invalidate_mastery(user_id)

    log.info(
        "answer.recorded",
        user_id=user_id,
        question_id=question.id,
        correct=correct,
        mastery_before=round(mastery_before, 4),
        mastery_after=round(mastery_after, 4),
        anomaly=flag_type,
    )
    return correct, mastery_before, mastery_after, flag_type
