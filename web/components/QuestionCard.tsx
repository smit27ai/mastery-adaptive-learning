"use client";

import { motion } from "motion/react";
import type { NextQuestion, SubmitResult } from "@/lib/api";

interface Props {
  data: NextQuestion;
  selected: string | null;
  result: SubmitResult | null;
  submitting: boolean;
  onSelect: (option: string) => void;
  onSubmit: () => void;
  onNext: () => void;
}

function difficultyLabel(d: number): string {
  if (d <= -1.5) return "very easy";
  if (d <= -0.5) return "easy";
  if (d < 0.5) return "medium";
  if (d < 1.5) return "hard";
  return "very hard";
}

export function QuestionCard({
  data,
  selected,
  result,
  submitting,
  onSelect,
  onSubmit,
  onNext,
}: Props) {
  const { question } = data;
  const locked = result !== null;

  return (
    <section className="rounded-xl border border-edge bg-panel p-6">
      <header className="mb-4 flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded-full bg-accent/15 px-2.5 py-1 font-medium text-accent">
          {question.concept_name}
        </span>
        <span className="rounded-full border border-edge px-2.5 py-1 text-muted">
          {difficultyLabel(question.difficulty)}
        </span>
        <span className="rounded-full border border-edge px-2.5 py-1 font-mono text-muted">
          predicted {Math.round(data.predicted_p_correct * 100)}%
        </span>
      </header>

      {/*
        Transform-only entrance, no opacity fade. If an animation stalls or never runs
        (a throttled tab, a device that drops requestAnimationFrame, reduced-motion),
        a fade from opacity 0 leaves the question unreadable. A stalled translate just
        leaves it a few pixels off. Text must never depend on an animation completing.
      */}
      <motion.h1
        key={question.id}
        initial={{ y: 8 }}
        animate={{ y: 0 }}
        transition={{ duration: 0.2 }}
        className="mb-6 text-xl font-medium leading-snug text-white"
      >
        {question.text}
      </motion.h1>

      <div className="grid gap-2.5 sm:grid-cols-2">
        {question.options.map((option) => {
          const isSelected = selected === option;
          const isRight = locked && option === result.correct_answer;
          const isWrongPick = locked && isSelected && !result.correct;

          // `enabled:` matters: CSS :hover still matches a disabled button, so a plain
          // hover: rule would paint the option under the cursor with the same accent
          // border that means "your selection" - during a demo that reads as a second
          // answer being chosen.
          let tone = "border-edge bg-ink enabled:hover:border-accent/60";
          if (isRight) tone = "border-good bg-good/10";
          else if (isWrongPick) tone = "border-bad bg-bad/10";
          else if (isSelected) tone = "border-accent bg-accent/10";

          return (
            <button
              key={option}
              type="button"
              disabled={locked || submitting}
              onClick={() => onSelect(option)}
              className={`rounded-lg border px-4 py-3 text-left text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-accent/70 disabled:cursor-default ${tone}`}
            >
              <span className="text-white">{option}</span>
              {isRight && <span className="ml-2 text-xs text-good">correct</span>}
              {isWrongPick && <span className="ml-2 text-xs text-bad">your answer</span>}
            </button>
          );
        })}
      </div>

      <div className="mt-6 flex items-center gap-3">
        {!locked ? (
          <button
            type="button"
            onClick={onSubmit}
            disabled={!selected || submitting}
            className="rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-white transition-opacity disabled:opacity-40"
          >
            {submitting ? "Checking..." : "Submit"}
          </button>
        ) : (
          <button
            type="button"
            onClick={onNext}
            className="rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-white"
          >
            Next question
          </button>
        )}
      </div>

      {/* Same rule as the heading: no height:"auto" and no opacity fade, so the
          feedback the learner most needs to read is never hidden by a stalled animation. */}
      {/* No AnimatePresence wrapper: there is no exit animation to wait for, and
          mode="wait" would keep the *previous* question's feedback on screen until that
          exit finished - stale feedback is worse than no transition. */}
      {result && (
        <motion.div
          key={`result-${question.id}`}
          initial={{ y: -6 }}
          animate={{ y: 0 }}
          transition={{ duration: 0.22 }}
        >
          <p
            className={`mt-5 rounded-lg border px-4 py-3 text-sm ${
              result.correct
                ? "border-good/40 bg-good/10 text-good"
                : "border-warn/40 bg-warn/10 text-warn"
            }`}
          >
            {result.explanation}
          </p>
          {result.anomaly_flag && (
            <p className="mt-2 rounded-lg border border-bad/40 bg-bad/10 px-4 py-2 text-xs text-bad">
              Flagged: {result.anomaly_flag}. Your instructor sees this signal too.
            </p>
          )}
        </motion.div>
      )}

      <footer className="mt-6 border-t border-edge pt-4">
        <p className="text-xs leading-relaxed text-muted">
          <span className="font-medium text-muted/90">Why this question? </span>
          {data.why}
        </p>
        <p className="mt-1 font-mono text-[11px] text-muted/60">
          policy: {data.policy} &middot; model: {data.model_version}
        </p>
      </footer>
    </section>
  );
}
