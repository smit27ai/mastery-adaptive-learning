"""End-to-end API tests: the thin slice must actually work over HTTP."""

from httpx import AsyncClient


async def test_health_is_public(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_ready_reports_each_dependency(client: AsyncClient) -> None:
    response = await client.get("/ready")
    body = response.json()
    assert set(body["checks"]) == {"database", "cache", "models"}
    assert body["checks"]["models"] == "ok"


async def test_metrics_endpoint_exposes_prometheus_text(client: AsyncClient) -> None:
    await client.get("/health")
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "mastery_requests_total" in response.text


async def test_register_then_login(client: AsyncClient) -> None:
    created = await client.post(
        "/auth/register", json={"email": "new@test.local", "password": "password123"}
    )
    assert created.status_code == 201
    assert created.json()["role"] == "student"

    duplicate = await client.post(
        "/auth/register", json={"email": "new@test.local", "password": "password123"}
    )
    assert duplicate.status_code == 409


async def test_login_with_wrong_password_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/login", json={"email": "s@test.local", "password": "wrong-password"}
    )
    assert response.status_code == 401


async def test_next_question_requires_auth(client: AsyncClient) -> None:
    assert (await client.get("/next-question")).status_code == 401


async def test_next_question_returns_a_full_payload(
    client: AsyncClient, student_token: str, auth
) -> None:
    response = await client.get("/next-question", headers=auth(student_token))
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["question"]["text"]
    assert len(body["question"]["options"]) == 4
    assert 0.0 <= body["predicted_p_correct"] <= 1.0
    assert body["why"]
    assert body["policy"] == "thompson"
    assert len(body["mastery"]) == 2  # two seeded concepts


async def test_full_learning_loop_moves_mastery(
    client: AsyncClient, student_token: str, auth
) -> None:
    headers = auth(student_token)
    served = (await client.get("/next-question", headers=headers)).json()
    question_id = served["question"]["id"]

    submitted = await client.post(
        "/submit-answer",
        headers=headers,
        json={"question_id": question_id, "answer": "a", "response_time_ms": 8000},
    )
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()

    assert body["correct"] is True
    assert body["mastery_after"] > body["mastery_before"]
    assert body["explanation"]


async def test_wrong_answer_lowers_mastery(client: AsyncClient, student_token: str, auth) -> None:
    headers = auth(student_token)
    served = (await client.get("/next-question", headers=headers)).json()

    body = (
        await client.post(
            "/submit-answer",
            headers=headers,
            json={
                "question_id": served["question"]["id"],
                "answer": "d",
                "response_time_ms": 9000,
            },
        )
    ).json()
    assert body["correct"] is False
    assert body["mastery_after"] < body["mastery_before"]


async def test_mastery_endpoint_reflects_recorded_attempts(
    client: AsyncClient, student_token: str, auth, seeded
) -> None:
    headers = auth(student_token)
    for _ in range(4):
        served = (await client.get("/next-question", headers=headers)).json()
        await client.post(
            "/submit-answer",
            headers=headers,
            json={
                "question_id": served["question"]["id"],
                "answer": "a",
                "response_time_ms": 7000,
            },
        )

    response = await client.get(f"/mastery/{seeded['student_id']}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["overall"] > 0
    assert sum(entry["attempts"] for entry in body["mastery"]) == 4


async def test_students_cannot_read_another_learners_mastery(
    client: AsyncClient, student_token: str, auth, seeded
) -> None:
    response = await client.get(f"/mastery/{seeded['instructor_id']}", headers=auth(student_token))
    assert response.status_code == 403


async def test_instructor_routes_are_role_gated(
    client: AsyncClient, student_token: str, instructor_token: str, auth
) -> None:
    assert (
        await client.get("/instructor/cohort/overview", headers=auth(student_token))
    ).status_code == 403

    allowed = await client.get("/instructor/cohort/overview", headers=auth(instructor_token))
    assert allowed.status_code == 200
    assert allowed.json()["total_students"] == 1


async def test_submitting_an_unknown_question_is_404(
    client: AsyncClient, student_token: str, auth
) -> None:
    response = await client.post(
        "/submit-answer",
        headers=auth(student_token),
        json={"question_id": 999999, "answer": "a", "response_time_ms": 1000},
    )
    assert response.status_code == 404


async def test_invalid_payload_is_rejected_by_validation(
    client: AsyncClient, student_token: str, auth
) -> None:
    response = await client.post(
        "/submit-answer",
        headers=auth(student_token),
        json={"question_id": 1, "answer": "a", "response_time_ms": -5},
    )
    assert response.status_code == 422


async def test_guessing_is_flagged(client: AsyncClient, student_token: str, auth) -> None:
    """Five fast wrong answers should trip the guessing detector."""
    headers = auth(student_token)
    flags = []
    for _ in range(6):
        served = (await client.get("/next-question", headers=headers)).json()
        body = (
            await client.post(
                "/submit-answer",
                headers=headers,
                json={
                    "question_id": served["question"]["id"],
                    "answer": "d",
                    "response_time_ms": 400,
                },
            )
        ).json()
        flags.append(body["anomaly_flag"])

    assert any(f in {"guessing", "disengaged"} for f in flags)
