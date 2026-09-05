"use client";

/**
 * The centrepiece of the live demo.
 *
 * A grader answers five questions and watches these bars move. Two details do the work:
 * the bar animates from its previous width rather than snapping, and the concept that
 * just changed is highlighted with its delta, so the cause and the effect are visible in
 * the same glance.
 */

import { AnimatePresence, motion } from "motion/react";
import type { MasteryEntry } from "@/lib/api";

function barColor(value: number): string {
  if (value >= 0.8) return "bg-good";
  if (value >= 0.5) return "bg-accent";
  if (value >= 0.3) return "bg-warn";
  return "bg-bad";
}

interface Props {
  mastery: MasteryEntry[];
  highlightConceptId?: number | null;
  delta?: number | null;
}

export function MasteryBars({ mastery, highlightConceptId, delta }: Props) {
  const overall =
    mastery.length > 0
      ? mastery.reduce((sum, m) => sum + m.mastery, 0) / mastery.length
      : 0;

  return (
    <section
      className="rounded-xl border border-edge bg-panel p-5"
      aria-label="Your mastery by concept"
    >
      <header className="mb-4 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
          Your knowledge state
        </h2>
        <motion.span
          key={overall.toFixed(3)}
          initial={{ opacity: 0.4 }}
          animate={{ opacity: 1 }}
          className="font-mono text-sm text-muted"
        >
          overall {(overall * 100).toFixed(0)}%
        </motion.span>
      </header>

      <ul className="space-y-3">
        {mastery.map((entry) => {
          const isHighlighted = entry.concept_id === highlightConceptId;
          const pct = Math.round(entry.mastery * 100);

          return (
            <li key={entry.concept_id}>
              <div className="mb-1 flex items-baseline justify-between gap-2">
                <span
                  className={`text-sm ${isHighlighted ? "font-semibold text-white" : "text-muted"}`}
                >
                  {entry.concept_name}
                </span>

                <span className="flex items-baseline gap-2 font-mono text-xs">
                  <AnimatePresence>
                    {isHighlighted && delta != null && Math.abs(delta) > 0.001 && (
                      <motion.span
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -6 }}
                        className={delta > 0 ? "text-good" : "text-bad"}
                      >
                        {delta > 0 ? "+" : ""}
                        {(delta * 100).toFixed(0)}
                      </motion.span>
                    )}
                  </AnimatePresence>
                  <span className={isHighlighted ? "text-white" : "text-muted"}>
                    {pct}%
                  </span>
                </span>
              </div>

              <div
                className="h-2.5 overflow-hidden rounded-full bg-ink"
                role="progressbar"
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${entry.concept_name} mastery`}
              >
                <motion.div
                  className={`h-full rounded-full ${barColor(entry.mastery)}`}
                  initial={false}
                  animate={{ width: `${pct}%` }}
                  transition={{ type: "spring", stiffness: 120, damping: 20 }}
                />
              </div>

              <p className="mt-1 text-[11px] text-muted/70">
                {entry.attempts === 0
                  ? "not yet assessed - showing the population prior"
                  : `${entry.attempts} attempt${entry.attempts === 1 ? "" : "s"}`}
              </p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
