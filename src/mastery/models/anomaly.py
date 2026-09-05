"""Cheap online anomaly rules.

The full project trains Isolation Forest and an autoencoder offline; these rules are the
real-time tripwires that run inside the request path, where a 200ms budget rules out
anything heavy. They flag the three behaviours an instructor actually cares about.
"""

from __future__ import annotations

from mastery.features.builder import Interaction

RAPID_ANSWER_MS = 1500
SLOW_ANSWER_MS = 300_000


def detect(history: list[Interaction], latest: Interaction) -> tuple[str, float, dict] | None:
    """Return (type, severity, evidence) or None."""
    recent = history[-8:]

    # Guessing: answering faster than it is possible to read the question, and mostly wrong.
    fast = [r for r in recent if 0 < r.response_time_ms < RAPID_ANSWER_MS]
    if len(fast) >= 4:
        accuracy = sum(1 for r in fast if r.is_correct) / len(fast)
        if accuracy < 0.4:
            return (
                "guessing",
                min(0.4 + 0.1 * len(fast), 1.0),
                {"fast_answers": len(fast), "accuracy": round(accuracy, 3)},
            )

    # Disengagement: a long wrong streak, or walking away mid-question.
    wrong_streak = 0
    for row in reversed(recent):
        if row.is_correct:
            break
        wrong_streak += 1
    if wrong_streak >= 5:
        return ("disengaged", min(0.3 + 0.1 * wrong_streak, 1.0), {"wrong_streak": wrong_streak})

    if latest.response_time_ms > SLOW_ANSWER_MS:
        return (
            "disengaged",
            0.4,
            {"response_time_ms": latest.response_time_ms, "reason": "idle"},
        )

    # Suspicious: perfect accuracy at implausible speed on hard items.
    if len(recent) >= 5 and all(r.is_correct for r in recent):
        times = [r.response_time_ms for r in recent if r.response_time_ms > 0]
        if times and sum(times) / len(times) < RAPID_ANSWER_MS:
            return (
                "cheating",
                0.6,
                {
                    "mean_response_time_ms": int(sum(times) / len(times)),
                    "correct_streak": len(recent),
                },
            )

    return None
