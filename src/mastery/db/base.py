"""SQLAlchemy ORM models - the tables described in the architecture."""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="student")
    cohort_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    attempts: Mapped[list["Attempt"]] = relationship(back_populates="user")


class Concept(Base):
    """A skill / topic. Concepts form a shallow hierarchy (Algebra > Quadratics)."""

    __tablename__ = "concepts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("concepts.id"), nullable=True)
    difficulty_prior: Mapped[float] = mapped_column(Float, default=0.5)

    # BKT parameters, fitted offline per concept
    bkt_prior: Mapped[float] = mapped_column(Float, default=0.25)
    bkt_learn: Mapped[float] = mapped_column(Float, default=0.15)
    bkt_slip: Mapped[float] = mapped_column(Float, default=0.10)
    bkt_guess: Mapped[float] = mapped_column(Float, default=0.20)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    concept_id: Mapped[int] = mapped_column(ForeignKey("concepts.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON, default=list)
    correct_answer: Mapped[str] = mapped_column(String(255))

    # IRT 2PL parameters, fitted offline
    irt_difficulty: Mapped[float] = mapped_column(Float, default=0.0)
    irt_discrimination: Mapped[float] = mapped_column(Float, default=1.0)
    p_value: Mapped[float] = mapped_column(Float, default=0.5)  # fraction answered correctly


class Attempt(Base):
    """Source of truth. Append-only - everything else can be rebuilt from this table."""

    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    concept_id: Mapped[int] = mapped_column(ForeignKey("concepts.id"), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    is_correct: Mapped[bool] = mapped_column(Boolean)
    response_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="attempts")

    __table_args__ = (Index("ix_attempts_user_time", "user_id", "created_at"),)


class MasterySnapshot(Base):
    """Time series of inferred mastery. Lets you draw the learning curve."""

    __tablename__ = "mastery_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    concept_id: Mapped[int] = mapped_column(ForeignKey("concepts.id"), index=True)
    mastery_prob: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_mastery_user_concept_time", "user_id", "concept_id", "created_at"),)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    questions_attempted: Mapped[int] = mapped_column(Integer, default=0)


class PredictionLog(Base):
    """Every prediction with the features that produced it.

    Without this table there is no drift detection and no retraining signal.
    """

    __tablename__ = "predictions_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    model_version: Mapped[str] = mapped_column(String(50), index=True)
    policy: Mapped[str] = mapped_column(String(50))
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    predicted_prob: Mapped[float] = mapped_column(Float)
    actual_outcome: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnomalyFlag(Base):
    __tablename__ = "anomaly_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(50))  # guessing | disengaged | cheating
    severity: Mapped[float] = mapped_column(Float, default=0.5)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
