"""Pydantic request/response schemas. These are the API contract - typed at the boundary."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------- Auth ----------
class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="student", pattern="^(student|instructor)$")


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    role: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    role: str
    cohort_id: str | None = None


# ---------- Learning loop ----------
class MasteryEntry(BaseModel):
    concept_id: int
    concept_name: str
    mastery: float = Field(ge=0.0, le=1.0)
    attempts: int


class QuestionOut(BaseModel):
    id: int
    concept_id: int
    concept_name: str
    text: str
    options: list[str]
    difficulty: float


class NextQuestionResponse(BaseModel):
    question: QuestionOut
    mastery: list[MasteryEntry]
    why: str = Field(description="Human-readable reason this question was selected")
    policy: str = Field(description="Which selection policy fired")
    predicted_p_correct: float
    model_version: str


class SubmitAnswerRequest(BaseModel):
    question_id: int
    answer: str
    response_time_ms: int = Field(ge=0, le=1_000_000)
    hints_used: int = Field(default=0, ge=0, le=10)
    session_id: str | None = None


class SubmitAnswerResponse(BaseModel):
    correct: bool
    correct_answer: str
    mastery_before: float
    mastery_after: float
    concept_id: int
    concept_name: str
    explanation: str
    anomaly_flag: str | None = None


class MasteryResponse(BaseModel):
    user_id: int
    mastery: list[MasteryEntry]
    overall: float
    model_version: str
    computed_at: datetime


class SessionStartResponse(BaseModel):
    session_id: str
    started_at: datetime


# ---------- Instructor ----------
class StudentRisk(BaseModel):
    user_id: int
    email: str
    overall_mastery: float
    risk_score: float
    weakest_concept: str | None
    attempts: int


class CohortOverview(BaseModel):
    total_students: int
    total_attempts: int
    mean_mastery: float
    students: list[StudentRisk]


class AnomalyOut(BaseModel):
    user_id: int
    type: str
    severity: float
    evidence: dict
    created_at: datetime


# ---------- Ops ----------
class HealthResponse(BaseModel):
    status: str
    version: str


class ReadyResponse(BaseModel):
    ready: bool
    checks: dict[str, str]
