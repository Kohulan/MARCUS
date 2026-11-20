import { faCheck } from "@fortawesome/free-solid-svg-icons";
import type { ReadingProgress as Model, Stage } from "../workspace/readingProgress";
import Icon from "./Icon";
import ProgressBar, { useAnnotateEstimate } from "./ProgressBar";
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

function shortLine(p: Model): string {
  const current = p.stages.find((s) => s.state === "current");
  if (p.stage === "waiting") return "Waiting";
  if (!current || p.stage === "annotating") return "";
  return current.count ? `${current.label} ${current.count}` : current.label;
}

/**
 * A paper's read as the progress bar (ProgressBar: the fill eases, the percentage counts up
 * beside it, never back during a run) with the stage in words. The full form lists the
 * stages, done ones ticked, the current one marked; `announce` adds a polite status that
 * changes with the stage only, never with a count or a percent. `compact` is the tool home's
 * row: a thin bar and one short line. An annotate run, whose model reports no progress,
 * shows the time-based estimate (useAnnotateEstimate) unless the model gives a figure.
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
  const annotating = progress.stage === "annotating";
  const estimate = useAnnotateEstimate(annotating && progress.fraction === null);
  const value = annotating ? (progress.fraction ?? estimate ?? 0) : progress.fraction;
  const bar = (
    <ProgressBar
      value={value}
      label={label}
      valueText={progress.valueText}
      active={progress.stage !== "done" && value !== 1}
      size={compact ? "sm" : "md"}
      estimated={annotating}
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
