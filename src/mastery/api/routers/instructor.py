"""Instructor-facing endpoints. Everything here is gated behind the instructor role."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mastery.api.deps import require_instructor
from mastery.common.schemas import AnomalyOut, CohortOverview, StudentRisk
from mastery.db.base import AnomalyFlag, Attempt, User
from mastery.db.session import get_db
from mastery.services import tutor

router = APIRouter(
    prefix="/instructor",
    tags=["instructor"],
    dependencies=[Depends(require_instructor)],
)


def _risk_score(overall_mastery: float, attempts: int, recent_accuracy: float) -> float:
    """Interim heuristic risk score.

    Phase 6 replaces this with the XGBoost risk model plus SHAP attributions; the endpoint
    contract stays the same so the dashboard does not have to change.
    """
    low_mastery = 1.0 - overall_mastery
    inactivity = 1.0 if attempts < 5 else 0.0
    return round(min(0.6 * low_mastery + 0.3 * (1.0 - recent_accuracy) + 0.1 * inactivity, 1.0), 4)


@router.get("/cohort/overview", response_model=CohortOverview)
async def cohort_overview(db: AsyncSession = Depends(get_db)) -> CohortOverview:
    students = list((await db.execute(select(User).where(User.role == "student"))).scalars().all())
    concepts = await tutor.all_concepts(db)
    total_attempts = (await db.execute(select(func.count(Attempt.id)))).scalar_one()

    rows: list[StudentRisk] = []
    for student in students:
        mastery = await tutor.get_mastery_map(db, student.id, concepts)
        history = await tutor.load_history(db, student.id)
        overall = sum(mastery.values()) / len(mastery) if mastery else 0.0
        recent = history[-10:]
        recent_accuracy = sum(1 for r in recent if r.is_correct) / len(recent) if recent else 0.0
        weakest = min(mastery.items(), key=lambda kv: kv[1])[0] if mastery else None
        weakest_name = next((c.name for c in concepts if c.id == weakest), None)

        rows.append(
            StudentRisk(
                user_id=student.id,
                email=student.email,
                overall_mastery=round(overall, 4),
                risk_score=_risk_score(overall, len(history), recent_accuracy),
                weakest_concept=weakest_name,
                attempts=len(history),
            )
        )

    rows.sort(key=lambda r: r.risk_score, reverse=True)
    mean_mastery = sum(r.overall_mastery for r in rows) / len(rows) if rows else 0.0

    return CohortOverview(
        total_students=len(rows),
        total_attempts=int(total_attempts),
        mean_mastery=round(mean_mastery, 4),
        students=rows,
    )


@router.get("/students/at-risk", response_model=list[StudentRisk])
async def at_risk(threshold: float = 0.5, db: AsyncSession = Depends(get_db)) -> list[StudentRisk]:
    overview = await cohort_overview(db)
    return [s for s in overview.students if s.risk_score >= threshold]


@router.get("/anomalies", response_model=list[AnomalyOut])
async def anomalies(limit: int = 50, db: AsyncSession = Depends(get_db)) -> list[AnomalyOut]:
    result = await db.execute(
        select(AnomalyFlag).order_by(AnomalyFlag.created_at.desc()).limit(limit)
    )
    return [
        AnomalyOut(
            user_id=f.user_id,
            type=f.type,
            severity=f.severity,
            evidence=f.evidence or {},
            created_at=f.created_at,
        )
        for f in result.scalars().all()
    ]
