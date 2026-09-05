"""Seed a small demo curriculum plus a simulated learner.

Real training uses ASSISTments / RIIID / EdNet. This seed exists so that `make serve`
produces a working adaptive demo on a clean machine within a minute, and so the tests
have deterministic content to run against.

Run with:  python -m mastery.data.seed
"""

from __future__ import annotations

import asyncio
import random

from sqlalchemy import func, select

from mastery.common.logging import configure_logging, get_logger
from mastery.common.security import hash_password
from mastery.db.base import Concept, Question, User
from mastery.db.session import SessionLocal, init_db

log = get_logger(__name__)

# name, bkt_prior, bkt_learn, bkt_slip, bkt_guess
CONCEPTS: list[tuple[str, float, float, float, float]] = [
    ("Fractions", 0.30, 0.18, 0.10, 0.22),
    ("Linear Equations", 0.22, 0.15, 0.12, 0.20),
    ("Quadratic Equations", 0.15, 0.12, 0.14, 0.18),
    ("Probability", 0.20, 0.14, 0.12, 0.25),
    ("Derivatives", 0.12, 0.10, 0.15, 0.16),
]

# concept name -> (question text, options, correct answer, irt difficulty)
QUESTIONS: dict[str, list[tuple[str, list[str], str, float]]] = {
    "Fractions": [
        ("What is 1/2 + 1/4?", ["1/6", "2/6", "3/4", "1/8"], "3/4", -2.0),
        ("Simplify 6/8.", ["3/4", "2/3", "4/6", "1/2"], "3/4", -1.5),
        ("What is 2/3 of 27?", ["9", "12", "18", "21"], "18", -0.5),
        ("Solve 3/4 divided by 2/5.", ["6/20", "15/8", "8/15", "5/6"], "15/8", 0.8),
        ("If 5/x = 2/7, what is x?", ["14/5", "35/2", "10/7", "7/10"], "35/2", 1.6),
    ],
    "Linear Equations": [
        ("Solve 2x = 10.", ["3", "5", "8", "20"], "5", -2.2),
        ("Solve x + 7 = 12.", ["4", "5", "19", "-5"], "5", -1.8),
        ("Solve 3x - 4 = 11.", ["3", "5", "7", "15"], "5", -0.6),
        ("Solve 2(x + 3) = 4x - 2.", ["2", "4", "-4", "8"], "4", 0.9),
        (
            "Solve the system: x + y = 7, x - y = 1.",
            ["(3,4)", "(4,3)", "(5,2)", "(6,1)"],
            "(4,3)",
            1.8,
        ),
    ],
    "Quadratic Equations": [
        (
            "What are the roots of x^2 - 4 = 0?",
            ["0 and 4", "2 and -2", "1 and 4", "-4 only"],
            "2 and -2",
            -1.2,
        ),
        (
            "Factorise x^2 + 5x + 6.",
            ["(x+2)(x+3)", "(x+1)(x+6)", "(x-2)(x-3)", "(x+5)(x+1)"],
            "(x+2)(x+3)",
            -0.3,
        ),
        ("Discriminant of x^2 + 2x + 5?", ["-16", "16", "24", "4"], "-16", 0.7),
        ("Sum of roots of 2x^2 - 6x + 1 = 0?", ["3", "-3", "1/2", "6"], "3", 1.4),
        (
            "For which k does x^2 + kx + 9 have equal roots?",
            ["3", "6 or -6", "9", "0"],
            "6 or -6",
            2.2,
        ),
    ],
    "Probability": [
        ("Probability of heads on a fair coin?", ["0", "1/4", "1/2", "1"], "1/2", -2.1),
        ("Probability of rolling a 4 on a fair die?", ["1/2", "1/3", "1/6", "1/4"], "1/6", -1.4),
        ("Two coins tossed. P(exactly one head)?", ["1/4", "1/2", "3/4", "1/3"], "1/2", -0.2),
        (
            "A bag has 3 red, 5 blue. P(red then red), no replacement?",
            ["9/64", "3/28", "1/4", "6/56"],
            "3/28",
            1.1,
        ),
        ("P(A)=0.4, P(B)=0.5, independent. P(A or B)?", ["0.9", "0.7", "0.2", "0.65"], "0.7", 1.9),
    ],
    "Derivatives": [
        ("d/dx of x^2?", ["x", "2x", "x^3/3", "2"], "2x", -1.6),
        ("d/dx of 5x + 3?", ["5", "5x", "3", "8"], "5", -1.9),
        ("d/dx of sin(x)?", ["cos(x)", "-cos(x)", "-sin(x)", "tan(x)"], "cos(x)", -0.4),
        ("d/dx of x*e^x?", ["e^x", "(x+1)e^x", "x e^x", "e^x/x"], "(x+1)e^x", 1.2),
        ("d/dx of ln(3x^2)?", ["2/x", "1/(3x^2)", "6x", "3/x"], "2/x", 2.0),
    ],
}

DEMO_USERS = [
    ("student@demo.local", "demo12345", "student"),
    ("instructor@demo.local", "demo12345", "instructor"),
]


async def seed() -> None:
    rng = random.Random(42)
    await init_db()

    async with SessionLocal() as db:
        existing = (await db.execute(select(func.count(Concept.id)))).scalar_one()
        if existing:
            log.info("seed.skipped", reason="concepts already present", count=existing)
            return

        concept_rows: dict[str, Concept] = {}
        for name, prior, learn, slip, guess in CONCEPTS:
            concept = Concept(
                name=name,
                difficulty_prior=0.5,
                bkt_prior=prior,
                bkt_learn=learn,
                bkt_slip=slip,
                bkt_guess=guess,
            )
            db.add(concept)
            concept_rows[name] = concept
        await db.flush()

        n_questions = 0
        for name, items in QUESTIONS.items():
            for text, options, answer, difficulty in items:
                shuffled = options[:]
                rng.shuffle(shuffled)
                db.add(
                    Question(
                        concept_id=concept_rows[name].id,
                        text=text,
                        options=shuffled,
                        correct_answer=answer,
                        irt_difficulty=difficulty,
                        irt_discrimination=round(rng.uniform(0.8, 1.6), 2),
                        # A rough population p-value implied by the item difficulty.
                        p_value=round(1.0 / (1.0 + pow(2.718281828, difficulty)), 3),
                    )
                )
                n_questions += 1

        for email, password, role in DEMO_USERS:
            db.add(User(email=email, password_hash=hash_password(password), role=role))

        await db.commit()

    log.info(
        "seed.complete",
        concepts=len(CONCEPTS),
        questions=n_questions,
        users=len(DEMO_USERS),
    )


def main() -> None:
    configure_logging("INFO", json_output=False)
    asyncio.run(seed())


if __name__ == "__main__":
    main()
