"""Test fixtures: an isolated in-memory database and an authenticated HTTP client."""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from mastery.api.main import app
from mastery.common.security import hash_password
from mastery.db.base import Base, Concept, Question, User
from mastery.db.cache import cache
from mastery.db.session import get_db


@pytest_asyncio.fixture
async def db_engine():  # type: ignore[no-untyped-def]
    # StaticPool keeps every connection pointed at the same in-memory database.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(db_engine):  # type: ignore[no-untyped-def]
    return async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def seeded(session_factory) -> dict:  # type: ignore[no-untyped-def]
    """A minimal curriculum: two concepts, six questions, one student, one instructor."""
    async with session_factory() as db:
        concepts = [
            Concept(name="Fractions", bkt_prior=0.3, bkt_learn=0.2, bkt_slip=0.1, bkt_guess=0.2),
            Concept(name="Algebra", bkt_prior=0.2, bkt_learn=0.15, bkt_slip=0.1, bkt_guess=0.2),
        ]
        db.add_all(concepts)
        await db.flush()

        for concept in concepts:
            for i, difficulty in enumerate((-1.5, 0.0, 1.5)):
                db.add(
                    Question(
                        concept_id=concept.id,
                        text=f"{concept.name} item {i}",
                        options=["a", "b", "c", "d"],
                        correct_answer="a",
                        irt_difficulty=difficulty,
                        irt_discrimination=1.0,
                        p_value=0.5,
                    )
                )

        student = User(
            email="s@test.local", password_hash=hash_password("password123"), role="student"
        )
        teacher = User(
            email="t@test.local", password_hash=hash_password("password123"), role="instructor"
        )
        db.add_all([student, teacher])
        await db.commit()
        return {"student_id": student.id, "instructor_id": teacher.id}


@pytest_asyncio.fixture
async def client(session_factory, seeded) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    await cache.connect()
    from mastery.models.registry import registry

    registry.load()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def student_token(client: AsyncClient) -> str:
    response = await client.post(
        "/auth/login", json={"email": "s@test.local", "password": "password123"}
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


@pytest_asyncio.fixture
async def instructor_token(client: AsyncClient) -> str:
    response = await client.post(
        "/auth/login", json={"email": "t@test.local", "password": "password123"}
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


@pytest.fixture
def auth():  # type: ignore[no-untyped-def]
    return lambda token: {"Authorization": f"Bearer {token}"}
