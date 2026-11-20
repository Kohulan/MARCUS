import { faCheck } from "@fortawesome/free-solid-svg-icons";
import { useState } from "react";
import { climb, type Climb, type ReadingProgress as Model, type Stage } from "../workspace/readingProgress";
import Icon from "./Icon";
import "./ui.css";

/** The stage's name, said once when the stage changes (never on a new count). */
const SAID: Record<Stage, string> = {
  waiting: "Waiting",
  checking: "Checking PDF",
  pages: "Reading pages",
  structures: "Reading structures",
  text: "Reading the text",
  finishing: "Finishing",
  annotating: "", // the badge and the annotation panel say it
  done: "Done",
};

/** The highest figure so far in this run (readingProgress climb); null stays indeterminate. */
function useClimbing(fraction: number | null, busy: boolean): number | null {
  const [state, setState] = useState<Climb>({ max: fraction ?? 0, busy });
  const next = climb(state, fraction, busy);
  if (next !== state) setState(next); // during render: no extra frame
  return fraction === null ? null : next.max;
}

function shortLine(p: Model): string {
  const current = p.stages.find((s) => s.state === "current");
  if (p.stage === "waiting") return "Waiting";
  if (!current || p.stage === "annotating") return "";
  return current.count ? `${current.label} ${current.count}` : current.label;
}

/**
 * A paper's read as a native <progress> (its value and max are the bar's ARIA value; the
 * fill is drawn by CSS on the element's pseudo-parts, so no style attribute) with the stage
 * in words. The full form lists the stages, done ones ticked, the current one marked;
 * `announce` adds a polite status that changes with the stage only. `compact` is the tool
 * home's row: a thin bar and one short line. The figure never moves back during a run.
 */
export default function ReadingProgress({
  progress,
  label,
  queueNote,
  announce = false,
  compact = false,
}: {
  progress: Model;
  /** The bar's accessible name. */
  label: string;
  /** "About 3 min in the queue": the line while waiting, then beside the stages. */
  queueNote?: string | null | undefined;
  announce?: boolean;
  compact?: boolean;
}) {
  const shown = useClimbing(progress.fraction, progress.stage !== "done");
  const value = shown === null ? undefined : Math.round(shown * 100);
  const bar = (
    <progress
      className="rp__bar"
      max={100}
      value={value}
      aria-label={label}
      aria-valuetext={progress.valueText}
    />
  );

  if (compact) {
    const line = shortLine(progress);
    return (
      <div className="rp rp--compact">
        {bar}
        {line ? <p className="rp__line">{line}</p> : null}
      </div>
    );
  }

  const queue = queueNote || null;
  return (
    <div className={`rp rp--${progress.stage}`}>
      <div className="rp__head">
        {progress.stage === "waiting" ? (
          <p className="rp__line rp__line--current">{queue ?? "Waiting"}</p>
        ) : progress.stage === "annotating" ? null : (
          <ol className="rp__stages" aria-label="Stages">
            {progress.stages.map((s) => (
              <li
                key={s.key}
                className={`rp__stage rp__stage--${s.state}`}
                aria-current={s.state === "current" ? "step" : undefined}
              >
                {s.state === "done" ? <Icon icon={faCheck} className="rp__tick" /> : null}
                {s.label}
                {s.count ? <span className="rp__count">{` ${s.count}`}</span> : null}
              </li>
            ))}
          </ol>
        )}
        {queue && progress.stage !== "waiting" ? <p className="rp__queue">{queue}</p> : null}
      </div>
      {bar}
      {announce ? (
        <p className="visually-hidden" role="status" aria-live="polite">
          {SAID[progress.stage]}
        </p>
      ) : null}
    </div>
  );
}
