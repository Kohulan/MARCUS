// A scaffold's R-group rows, read by the local R-group model (by itself once the scaffold and the
// page's text are read, or by hand): its progress or failure, the rows as a table (one row per
// compound, one column per label), then a small action (Run again).
// Every value is model text: rendered as React text only, and marked as output to check.
import { useState } from "react";
import { errorText } from "../api/client";
import type { RgroupRow } from "../api/types";
import { GlassButton } from "../ui/GlassButton";
import {
  compoundCount,
  isRgroupActive,
  RGROUP_NOTE,
  rgroupFailure,
  rgroupProgress,
  UNLABELLED,
} from "./rgroups";
import { useRgroupReading } from "./useRgroupRows";
import "./rgroupRows.css";

type Props = {
  /** The prediction the rows belong to (the scaffold shown). */
  predictionId: string;
  /** Its R-group labels: the columns until the server names its own. */
  labels: readonly string[];
  /** "[03]": names the table for a screen reader. */
  tag: string;
  /** The card's size: the table scrolls inside a short box. */
  compact?: boolean;
};

const cell = (row: RgroupRow, label: string): string =>
  Object.hasOwn(row.groups, label) ? (row.groups[label] ?? "") : "";

/** Nothing where the deployment cannot read R-groups and nothing was read before. */
export default function RgroupRows({ predictionId, labels, tag, compact = false }: Props) {
  const { available, extraction, pending, start } = useRgroupReading(predictionId);
  const [starting, setStarting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  // about to start by itself: as good as queued
  const status = extraction?.status ?? (pending ? "queued" : "none");
  const rows = extraction?.rows ?? null;
  // Only unlabelled points (*): nothing the model can be asked for (the server answers 409).
  const askable = labels.some((label) => label !== UNLABELLED);
  if ((!available || !askable) && rows === null) return null;

  const active = starting || isRgroupActive(status);
  const columns = extraction?.labels.length ? extraction.labels : labels;

  async function run() {
    setProblem(null);
    setStarting(true);
    try {
      await start(rows !== null);
    } catch (err) {
      setProblem(`Not started: ${errorText(err, "starts")}`);
    } finally {
      setStarting(false);
    }
  }

  const action = rows !== null ? "Run again" : status === "failed" ? "Try again" : "Extract R-groups";
  const said = active
    ? rgroupProgress(status === "none" ? "queued" : status)
    : status === "done" && rows !== null
      ? `R-groups read: ${compoundCount(rows.length)}`
      : status === "failed"
        ? rgroupFailure(extraction?.error ?? null)
        : "";

  return (
    <section className={compact ? "rg rg--compact" : "rg"} aria-label={`R-groups of ${tag}`}>
      {rows !== null && rows.length > 0 && (
        <div
          className="rg__scroll"
          role="region"
          aria-label={`R-group table of ${tag}`}
          tabIndex={0}
        >
          <table className="specimen rg__table">
            <caption className="specimen__head rg__caption">{RGROUP_NOTE}</caption>
            <thead>
              <tr>
                <th scope="col">Compound</th>
                {columns.map((label) => (
                  <th key={label} scope="col">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={`${i}:${row.compound}`}>
                  <th scope="row">{row.compound}</th>
                  {columns.map((label) => (
                    <td key={label}>{cell(row, label)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows !== null && rows.length === 0 && (
        <p className="rg__note">No R-group definitions found on the page.</p>
      )}
      {rows !== null && extraction?.truncated && (
        <p className="rg__note">Cut short: later rows are missing.</p>
      )}
      {status === "failed" && !active && (
        <p className="rg__problem">{rgroupFailure(extraction?.error ?? null)}</p>
      )}
      <div className="rg__bar">
        {active ? (
          <span className="state badge badge--dashed">
            {rgroupProgress(status === "none" ? "queued" : status)}
          </span>
        ) : (
          available &&
          askable && (
            <GlassButton tint="clear" size="sm" onClick={() => void run()}>
              {action}
            </GlassButton>
          )
        )}
      </div>
      {problem !== null && (
        <p className="rg__problem" role="alert">
          {problem}
        </p>
      )}
      <p className="visually-hidden" role="status" aria-live="polite">
        {said}
      </p>
    </section>
  );
}
