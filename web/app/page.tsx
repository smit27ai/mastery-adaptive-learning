"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "motion/react";

import { MasteryBars } from "@/components/MasteryBars";
import { QuestionCard } from "@/components/QuestionCard";
import {
  ApiError,
  api,
  session,
  type MasteryEntry,
  type NextQuestion,
  type SubmitResult,
} from "@/lib/api";

const DEMO_EMAIL = "student@demo.local";
const DEMO_PASSWORD = "demo12345";

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [current, setCurrent] = useState<NextQuestion | null>(null);
  const [mastery, setMastery] = useState<MasteryEntry[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [result, setResult] = useState<SubmitResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [answered, setAnswered] = useState(0);

  // Response time is a real feature the model consumes, so it is measured from when the
  // question actually appeared rather than estimated on the server.
  const shownAt = useRef<number>(Date.now());

  const loadQuestion = useCallback(
    async (authToken: string, sid?: string) => {
      setLoading(true);
      setError(null);
      try {
        const next = await api.nextQuestion(authToken, sid);
        setCurrent(next);
        setMastery(next.mastery);
        setSelected(null);
        setResult(null);
        shownAt.current = Date.now();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Something went wrong.");
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const signIn = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const auth = await api.login(DEMO_EMAIL, DEMO_PASSWORD);
      session.set(auth.access_token);
      setToken(auth.access_token);
      const started = await api.startSession(auth.access_token);
      setSessionId(started.session_id);
      await loadQuestion(auth.access_token, started.session_id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed.");
      setLoading(false);
    }
  }, [loadQuestion]);

  useEffect(() => {
    const existing = session.get();
    if (existing) {
      setToken(existing);
      // A stored token can be expired; falling back to a fresh sign-in keeps the demo
      // from dead-ending on a stale localStorage value.
      api
        .startSession(existing)
        .then((started) => {
          setSessionId(started.session_id);
          return loadQuestion(existing, started.session_id);
        })
        .catch(() => {
          session.clear();
          void signIn();
        });
    } else {
      void signIn();
    }
  }, [loadQuestion, signIn]);

  async function handleSubmit() {
    if (!token || !current || !selected) return;
    setSubmitting(true);
    try {
      const outcome = await api.submitAnswer(token, {
        question_id: current.question.id,
        answer: selected,
        response_time_ms: Math.min(Date.now() - shownAt.current, 1_000_000),
        session_id: sessionId,
      });
      setResult(outcome);
      setAnswered((n) => n + 1);

      // Update the bar for the concept just practised, straight from the response, so
      // the animation fires immediately rather than after another round trip.
      setMastery((previous) =>
        previous.map((entry) =>
          entry.concept_id === outcome.concept_id
            ? {
                ...entry,
                mastery: outcome.mastery_after,
                attempts: entry.attempts + 1,
              }
            : entry,
        ),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit your answer.");
    } finally {
      setSubmitting(false);
    }
  }

  function handleNext() {
    if (token) void loadQuestion(token, sessionId);
  }

  const delta = result ? result.mastery_after - result.mastery_before : null;

  return (
    <main className="mx-auto min-h-screen max-w-5xl px-5 py-10">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-white">Mastery</h1>
          <p className="mt-1 text-sm text-muted">
            The next question is chosen from what the model believes you know.
          </p>
        </div>
        <div className="text-right font-mono text-xs text-muted">
          <div>answered: {answered}</div>
          {sessionId && <div className="text-muted/50">session {sessionId.slice(0, 8)}</div>}
        </div>
      </header>

      {error && (
        <div className="mb-6 rounded-lg border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
          <p>{error}</p>
          <button
            type="button"
            onClick={() => void signIn()}
            className="mt-2 rounded border border-bad/40 px-3 py-1 text-xs"
          >
            Retry
          </button>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div>
          {loading && !current ? (
            <div className="rounded-xl border border-edge bg-panel p-6">
              <motion.p
                animate={{ opacity: [0.55, 1, 0.55] }}
                transition={{ repeat: Infinity, duration: 1.4 }}
                className="text-sm text-muted"
              >
                Loading your knowledge state...
              </motion.p>
            </div>
          ) : current ? (
            <QuestionCard
              data={current}
              selected={selected}
              result={result}
              submitting={submitting}
              onSelect={setSelected}
              onSubmit={() => void handleSubmit()}
              onNext={handleNext}
            />
          ) : null}
        </div>

        <aside>
          <MasteryBars
            mastery={mastery}
            highlightConceptId={result?.concept_id ?? null}
            delta={delta}
          />
          <p className="mt-4 px-1 text-[11px] leading-relaxed text-muted/60">
            Mastery is a latent quantity: it is never observed directly, only inferred
            from your answers, your speed and how long ago you last saw the concept.
          </p>
        </aside>
      </div>
    </main>
  );
}
