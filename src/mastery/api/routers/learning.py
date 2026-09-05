"""The core learning loop: start a session, get a question, submit an answer."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mastery.api.deps import current_user
from mastery.common.schemas import (
    MasteryEntry,
    MasteryResponse,
    NextQuestionResponse,
    QuestionOut,
    SessionStartResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
)
from mastery.db.base import Concept, Question, Session, User
from mastery.db.session import get_db
from mastery.models.registry import registry
from mastery.services import tutor

router = APIRouter(tags=["learning"])


def _mastery_entries(
    mastery: dict[int, float], concepts: list[Concept], counts: dict[int, int]
) -> list[MasteryEntry]:
    return [
        MasteryEntry(
            concept_id=c.id,
            concept_name=c.name,
            mastery=round(mastery.get(c.id, c.bkt_prior), 4),
            attempts=counts.get(c.id, 0),
        )
        for c in concepts
    ]


@router.post("/session/start", response_model=SessionStartResponse)
async def start_session(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> SessionStartResponse:
    session = Session(id=uuid.uuid4().hex, user_id=user.id)
    db.add(session)
    await db.commit()
    return SessionStartResponse(session_id=session.id, started_at=session.started_at)


@router.get("/next-question", response_model=NextQuestionResponse)
async def next_question(
    session_id: str | None = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> NextQuestionResponse:
    try:
        question, concept, mastery, p_correct, policy, why = await tutor.choose_next_question(
            db, user.id, session_id=session_id
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    concepts = await tutor.all_concepts(db)
    history = await tutor.load_history(db, user.id)
    counts: dict[int, int] = {}
    for row in history:
        counts[row.concept_id] = counts.get(row.concept_id, 0) + 1

    return NextQuestionResponse(
        question=QuestionOut(
            id=question.id,
            concept_id=concept.id,
            concept_name=concept.name,
            text=question.text,
            options=list(question.options or []),
            difficulty=question.irt_difficulty,
        ),
        mastery=_mastery_entries(mastery, concepts, counts),
        why=why,
        policy=policy,
        predicted_p_correct=round(p_correct, 4),
        model_version=registry.version,
    )


@router.post("/submit-answer", response_model=SubmitAnswerResponse)
async def submit_answer(
    body: SubmitAnswerRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SubmitAnswerResponse:
    question = (
        await db.execute(select(Question).where(Question.id == body.question_id))
    ).scalar_one_or_none()
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    concept = (
        await db.execute(select(Concept).where(Concept.id == question.concept_id))
    ).scalar_one_or_none()
    if concept is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concept not found")

    correct, before, after, flag = await tutor.record_answer(
        db,
        user.id,
        question,
        concept,
        answer=body.answer,
        response_time_ms=body.response_time_ms,
        hints_used=body.hints_used,
        session_id=body.session_id,
    )

    delta = after - before
    explanation = (
        f"Correct. Your {concept.name} mastery moved {before:.0%} to {after:.0%} "
        f"(+{delta:.0%})."
        if correct
        else f"Not quite. Your {concept.name} mastery is now {after:.0%}; "
        f"expect an easier item next."
    )

    return SubmitAnswerResponse(
        correct=correct,
        correct_answer=question.correct_answer,
        mastery_before=round(before, 4),
        mastery_after=round(after, 4),
        concept_id=concept.id,
        concept_name=concept.name,
        explanation=explanation,
        anomaly_flag=flag,
    )


@router.get("/mastery/{user_id}", response_model=MasteryResponse)
async def get_mastery(
    user_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> MasteryResponse:
    if user.id != user_id and user.role != "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Cannot read another learner's mastery"
        )

    concepts = await tutor.all_concepts(db)
    mastery = await tutor.get_mastery_map(db, user_id, concepts)
    history = await tutor.load_history(db, user_id)
    counts: dict[int, int] = {}
    for row in history:
        counts[row.concept_id] = counts.get(row.concept_id, 0) + 1

    entries = _mastery_entries(mastery, concepts, counts)
    overall = sum(e.mastery for e in entries) / len(entries) if entries else 0.0

    return MasteryResponse(
        user_id=user_id,
        mastery=entries,
        overall=round(overall, 4),
        model_version=registry.version,
        computed_at=datetime.now(UTC),
    )
