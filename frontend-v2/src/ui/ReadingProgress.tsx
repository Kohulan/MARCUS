import { faCheck } from "@fortawesome/free-solid-svg-icons";
import { useState } from "react";
import type { ReadingProgress as Model } from "../workspace/readingProgress";
import Icon from "./Icon";
import ProgressBar from "./ProgressBar";
import "./ui.css";

/**
 * What a reading bar shows of `model` (readingProgress), or null for no bar. A finished read
 * keeps its full bar when `keepDone` and it was read while shown here; otherwise a done paper
 * has no bar.
 */
export function useShownProgress(
  model: Model | null,
  { keepDone = false }: { keepDone?: boolean } = {},
): Model | null {
  const [seen, setSeen] = useState(false);
  if (model !== null && model.stage !== "done" && !seen) setSeen(true);
  if (model === null || model.stage !== "done") return model;
  return keepDone && seen ? model : null;
}

/**
 * A paper's read as the progress bar (ProgressBar: the fill eases, the percentage counts up
 * beside it, never back during a run) with the stage in words. The full form lists the
 * stages, done ones ticked, the current one marked; `announce` adds a polite status that
 * changes with the stage only, never with a count or a percent. `compact` is the tool home's
 * row: a thin bar and one short line. The model is shown as given.
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
  const bar = (
    <ProgressBar
      value={progress.fraction}
      label={label}
      valueText={progress.valueText}
      active={progress.stage !== "done" && progress.fraction !== 1}
      size={compact ? "sm" : "md"}
    />
  );

  if (compact) {
    return (
      <div className="rp rp--compact">
        {bar}
        {progress.line ? <p className="rp__line">{progress.line}</p> : null}
      </div>
    );
  }

  const queue = queueNote || null;
  const waiting = progress.stage === "waiting";
  return (
    <div className={`rp rp--${progress.stage}`}>
      <div className="rp__head">
        {waiting ? (
          <p className="rp__line rp__line--current">{queue ?? progress.line}</p>
        ) : progress.stages.length > 0 ? (
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
        ) : null}
        {queue && !waiting ? <p className="rp__queue">{queue}</p> : null}
      </div>
      {bar}
      {announce ? (
        <p className="visually-hidden" role="status" aria-live="polite">
          {progress.said}
        </p>
      ) : null}
    </div>
  );
}
