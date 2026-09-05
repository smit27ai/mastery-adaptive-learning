"""Post-deploy verification.

Checks a running deployment the way a user would, over HTTPS, from outside. CI proves
the image works in CI's own network; this proves the thing you actually shipped works,
which is a different claim.

    python scripts/verify_deployment.py https://your-api.up.railway.app
    python scripts/verify_deployment.py https://your-api.up.railway.app \
        --origin https://your-app.vercel.app

Exits non-zero if any check fails, so it can gate a release.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from dataclasses import dataclass, field

import httpx

TIMEOUT = 30.0


@dataclass
class Report:
    passed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    warned: list[tuple[str, str]] = field(default_factory=list)

    def ok(self, name: str, detail: str = "") -> None:
        self.passed.append(f"{name}{f' - {detail}' if detail else ''}")
        print(f"  PASS  {name}{f' - {detail}' if detail else ''}")

    def fail(self, name: str, detail: str) -> None:
        self.failed.append((name, detail))
        print(f"  FAIL  {name} - {detail}")

    def warn(self, name: str, detail: str) -> None:
        self.warned.append((name, detail))
        print(f"  WARN  {name} - {detail}")


def section(title: str) -> None:
    print(f"\n{title}")


def check_liveness(client: httpx.Client, report: Report) -> None:
    section("Liveness")
    try:
        started = time.perf_counter()
        response = client.get("/health")
        elapsed_ms = (time.perf_counter() - started) * 1000
    except httpx.HTTPError as exc:
        report.fail("/health", f"unreachable: {exc}")
        return

    if response.status_code != 200:
        report.fail("/health", f"HTTP {response.status_code}")
        return

    body = response.json()
    report.ok("/health", f"{body.get('status')}, model {body.get('version')}, {elapsed_ms:.0f}ms")

    # A response served by anything other than this app means the URL points elsewhere.
    server = response.headers.get("x-powered-by", "")
    if server:
        report.warn("server identity", f"x-powered-by: {server} - is this really the API?")


def check_readiness(client: httpx.Client, report: Report) -> None:
    section("Readiness")
    try:
        response = client.get("/ready")
    except httpx.HTTPError as exc:
        report.fail("/ready", f"unreachable: {exc}")
        return

    body = response.json()
    checks = body.get("checks", {})

    if checks.get("database") == "ok":
        report.ok("database", "connected")
    else:
        report.fail("database", str(checks.get("database")))

    if checks.get("models") == "ok":
        report.ok("models", "loaded")
    else:
        report.fail("models", str(checks.get("models")))

    cache = str(checks.get("cache", ""))
    if "redis" in cache:
        report.ok("cache", cache)
    else:
        # Not a failure: the app is designed to run without Redis, just slower.
        report.warn("cache", f"{cache} - fine, but mastery is recomputed on every miss")


def check_docs(client: httpx.Client, report: Report) -> None:
    section("API surface")
    try:
        spec = client.get("/openapi.json").json()
    except (httpx.HTTPError, ValueError) as exc:
        report.fail("/openapi.json", str(exc))
        return

    paths = set(spec.get("paths", {}))
    required = {"/next-question", "/submit-answer", "/auth/login", "/auth/register"}
    missing = required - paths
    if missing:
        report.fail("routes", f"missing {sorted(missing)}")
    else:
        report.ok("routes", f"{len(paths)} paths published")


def check_auth(client: httpx.Client, report: Report) -> str | None:
    section("Authentication")
    email = f"verify-{uuid.uuid4().hex[:10]}@check.local"
    password = "verification-password-123"

    try:
        response = client.post("/auth/register", json={"email": email, "password": password})
    except httpx.HTTPError as exc:
        report.fail("register", str(exc))
        return None

    if response.status_code != 201:
        report.fail("register", f"HTTP {response.status_code}: {response.text[:200]}")
        return None
    token = str(response.json()["access_token"])
    report.ok("register", "new account issued a token")

    # A wrong password must be rejected: the check that the auth layer is real.
    rejected = client.post("/auth/login", json={"email": email, "password": "wrong-password"})
    if rejected.status_code == 401:
        report.ok("bad password", "rejected with 401")
    else:
        report.fail("bad password", f"expected 401, got {rejected.status_code}")

    # And an unauthenticated call to a protected route must not succeed.
    anonymous = httpx.get(f"{client.base_url}/next-question", timeout=TIMEOUT)
    if anonymous.status_code in (401, 403):
        report.ok("protected route", f"anonymous access refused ({anonymous.status_code})")
    else:
        report.fail("protected route", f"anonymous got HTTP {anonymous.status_code}")

    return token


def check_learning_loop(client: httpx.Client, report: Report, token: str, rounds: int) -> None:
    section(f"Adaptive loop ({rounds} questions)")
    headers = {"Authorization": f"Bearer {token}"}
    moved = False

    for i in range(1, rounds + 1):
        try:
            served = client.get("/next-question", headers=headers).json()
        except (httpx.HTTPError, ValueError) as exc:
            report.fail(f"question {i}", str(exc))
            return

        question = served.get("question")
        if not question:
            report.fail(f"question {i}", f"no question in response: {str(served)[:200]}")
            return

        outcome = client.post(
            "/submit-answer",
            headers=headers,
            json={
                "question_id": question["id"],
                # The first option is a real answer; whether it is correct is up to the
                # item, which is what we want - both branches get exercised.
                "answer": question["options"][0],
                "response_time_ms": 6000,
            },
        )
        if outcome.status_code != 200:
            report.fail(f"answer {i}", f"HTTP {outcome.status_code}: {outcome.text[:200]}")
            return

        body = outcome.json()
        delta = body["mastery_after"] - body["mastery_before"]
        if abs(delta) > 1e-9:
            moved = True
        print(
            f"        {i}. {question['concept_name']:<22}"
            f"predicted {served['predicted_p_correct']:>5.0%}  "
            f"{'right' if body['correct'] else 'wrong':<6}"
            f"{body['mastery_before']:.2f} -> {body['mastery_after']:.2f}"
        )

    if moved:
        report.ok("mastery updates", "inference is running, not returning constants")
    else:
        report.fail("mastery updates", "mastery never changed across the run")


def check_cors(client: httpx.Client, report: Report, origin: str) -> None:
    section("CORS")
    try:
        response = client.options(
            "/next-question",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
    except httpx.HTTPError as exc:
        report.fail("preflight", str(exc))
        return

    allowed = response.headers.get("access-control-allow-origin")
    if allowed == origin:
        report.ok("preflight", f"{origin} allowed")
    elif allowed == "*":
        report.warn("preflight", "wildcard origin - tighten CORS_ORIGINS before you rely on this")
    else:
        report.fail(
            "preflight",
            f"{origin} not allowed (got {allowed!r}) - set CORS_ORIGINS on the API",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="API base URL, e.g. https://api.up.railway.app")
    parser.add_argument("--origin", help="Frontend origin to check CORS against")
    parser.add_argument("--rounds", type=int, default=5, help="Questions to answer")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    print(f"Verifying {base}")

    report = Report()
    with httpx.Client(base_url=base, timeout=TIMEOUT, follow_redirects=True) as client:
        check_liveness(client, report)
        if report.failed:
            print("\nAPI is not reachable; skipping the remaining checks.")
            return 1

        check_readiness(client, report)
        check_docs(client, report)
        token = check_auth(client, report)
        if token:
            check_learning_loop(client, report, token, args.rounds)
        if args.origin:
            check_cors(client, report, args.origin.rstrip("/"))

    print(
        f"\n{len(report.passed)} passed, {len(report.failed)} failed, {len(report.warned)} warnings"
    )
    for name, detail in report.failed:
        print(f"  FAILED: {name} - {detail}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
