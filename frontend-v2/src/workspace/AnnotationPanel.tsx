// The paper's annotation above its text (Paper view): the Annotate action, its progress, then
// the fields as a specimen label, each found value a button that shows its next occurrence in
// the text. The curator can correct the values (one a line per field) and go back to the
// model's. Every value is model or curator text: rendered as React text only.
import { useEffect, useId, useRef, useState } from "react";
import { errorText } from "../api/client";
import type { AnnotationOut, AnnotationValues, StepOut } from "../api/types";
import { GlassButton } from "../ui/GlassButton";
import {
  annotateReason,
  hitsOf,
  linesOf,
  sameValues,
  shownPositions,
  valuesIn,
  valuesOf,
  valuesProblem,
  type HitAt,
} from "./annotation";

type Props = {
  annotation: AnnotationOut;
  /** An annotate step is running (or was just started and the steps do not show it yet). */
  running: boolean;
  /** The newest annotate step as the steps show it (fresher than the annotation's own). */
  step: StepOut | undefined;
  /** The occurrence shown in the text. */
  at: HitAt | null;
  /** Shows the value's next occurrence; returns its index. */
  onShow: (field: string, value: string) => number;
  onStart: () => Promise<void>;
  onSave: (values: AnnotationValues) => Promise<unknown>;
  onReset: () => Promise<unknown>;
};

export default function AnnotationPanel(props: Props) {
  const { annotation, running, step } = props;
  const hintId = useId();
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  // What a screen reader is told after an action (kept mounted, so each change is said).
  const [said, setSaid] = useState("");

  async function start() {
    setError(null);
    setStarting(true);
    try {
      await props.onStart();
    } catch (err) {
      setError(`Not started: ${errorText(err)}`);
    } finally {
      setStarting(false);
    }
  }

  const newest = step ?? annotation.step ?? undefined;
  const failedStep = newest?.status === "failed" ? newest : null;

  let body;
  if (running || starting) {
    body = (
      <p className="pv-ann__state" role="status">
        <span className="state badge badge--dashed">Annotating…</span>
      </p>
    );
  } else if (annotation.values !== null) {
    body = <Fields {...props} failedStep={failedStep} say={setSaid} />;
  } else {
    body = (
      <div className="pv-ann__start">
        <GlassButton
          tint="clear"
          size="sm"
          describedBy={failedStep ? undefined : hintId}
          onClick={() => void start()}
        >
          {failedStep ? "Try again" : "Annotate"}
        </GlassButton>
        {failedStep ? (
          <p className="pv-ann__problem">{`Annotation failed: ${annotateReason(failedStep.error_class)}`}</p>
        ) : (
          <p id={hintId} className="pv-ann__hint">
            A model on this server suggests organism, place and compound names.
          </p>
        )}
      </div>
    );
  }

  return (
    <section className="pv-ann" aria-label="Annotation">
      {body}
      {error !== null && (
        <p className="pv-ann__problem" role="alert">
          {error}
        </p>
      )}
      <p className="visually-hidden" role="status" aria-live="polite">
        {said}
      </p>
    </section>
  );
}

function Fields({
  annotation,
  at,
  onShow,
  onSave,
  onReset,
  failedStep,
  say,
}: Props & { failedStep: StepOut | null; say: (text: string) => void }) {
  const values = annotation.values!;
  const positions = shownPositions(annotation);
  const curated = annotation.curated !== null;
  const labelOf = (key: string) => annotation.fields.find((f) => f.key === key)?.label ?? key;
  const filled = annotation.fields.filter((f) => valuesIn(values, f.key).length > 0);
  const [draft, setDraft] = useState<Record<string, string> | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const editButton = useRef<HTMLButtonElement>(null);
  const form = useRef<HTMLFormElement>(null);
  const editing = draft !== null;
  const wasEditing = useRef(false);

  useEffect(() => {
    if (editing) {
      // the form starts at its top (its hint and first label in view), in the first box
      const panel = form.current?.closest<HTMLElement>(".pv-ann");
      if (panel) panel.scrollTop = 0;
      form.current?.querySelector("textarea")?.focus({ preventScroll: true });
    }
    else if (wasEditing.current) editButton.current?.focus();
    wasEditing.current = editing;
  }, [editing]);

  /** Shows the next occurrence and says where the walk stands ("Taxus brevifolia: 2 of 5"). */
  function show(field: string, value: string, count: number) {
    const index = onShow(field, value);
    say(`${value}: ${index + 1} of ${count}`);
  }

  function edit() {
    setProblem(null);
    setDraft(Object.fromEntries(annotation.fields.map((f) => [f.key, linesOf(valuesIn(values, f.key))])));
  }

  async function save() {
    if (!draft || busy) return;
    const next: AnnotationValues = Object.fromEntries(
      annotation.fields.map((f) => [f.key, valuesOf(Object.hasOwn(draft, f.key) ? draft[f.key]! : "")]),
    );
    const why = valuesProblem(next, labelOf);
    if (why) {
      setProblem(why);
      return;
    }
    if (sameValues(next, values)) {
      setDraft(null);
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      await onSave(next);
      setDraft(null);
      say("Saved");
    } catch (err) {
      setProblem(`Not saved: ${errorText(err)}`);
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    if (busy || !window.confirm("Drop your corrections and show the model's values?")) return;
    setBusy(true);
    try {
      await onReset();
      say("Model values shown");
    } catch (err) {
      say(`Not reset: ${errorText(err)}`);
    } finally {
      setBusy(false);
    }
  }

  if (editing) {
    const hint = "pv-ann-lines";
    return (
      <form
        ref={form}
        className="pv-ann__form"
        aria-label="Correct the annotation"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape" && !busy) {
            e.stopPropagation();
            setDraft(null);
          }
        }}
      >
        <p id={hint} className="pv-ann__hint">
          One value a line.
        </p>
        <div className="pv-ann__fields">
          {annotation.fields.map((f) => {
            const id = `pv-ann-${f.key}`;
            const text = Object.hasOwn(draft, f.key) ? draft[f.key]! : "";
            return (
              <div key={f.key} className="pv-ann__field">
                <label className="mono-label pv-ann__field-label" htmlFor={id}>
                  {f.label}
                </label>
                <textarea
                  id={id}
                  className="pv-ann__input"
                  rows={Math.min(6, Math.max(1, text.split("\n").length))}
                  aria-describedby={hint}
                  spellCheck={false}
                  value={text}
                  disabled={busy}
                  onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                />
              </div>
            );
          })}
        </div>
        {problem !== null && (
          <p className="pv-ann__problem" role="alert">
            {problem}
          </p>
        )}
        <div className="pv-ann__actions">
          <GlassButton tint="green" size="sm" type="submit" disabled={busy}>
            Save
          </GlassButton>
          <GlassButton tint="clear" size="sm" disabled={busy} onClick={() => setDraft(null)}>
            Cancel
          </GlassButton>
        </div>
      </form>
    );
  }

  return (
    <>
      <div className="pv-ann__label">
        <p className="pv-ann__head">
          <span>{curated ? "Curated" : "Model suggestion"}</span>
          {annotation.model && <span className="pv-ann__model">{annotation.model}</span>}
        </p>
        {filled.length === 0 ? (
          <p className="pv-ann__none">Nothing found</p>
        ) : (
          <dl className="pv-ann__list">
            {filled.map((f) => (
              <div key={f.key} className="pv-ann__row">
                <dt className="pv-ann__key">{f.label}</dt>
                <dd className="pv-ann__values">
                  {valuesIn(values, f.key).map((v) => {
                    const count = hitsOf(positions, f.key, v).length;
                    if (count === 0) {
                      return (
                        <span key={v} className="pv-ann__value pv-ann__value--absent">
                          {v}
                          <span className="pv-ann__count" aria-hidden="true">
                            0
                          </span>
                          <span className="visually-hidden"> (not in the text)</span>
                        </span>
                      );
                    }
                    const shown = at?.field === f.key && at.value === v;
                    return (
                      <button
                        key={v}
                        type="button"
                        className={shown ? "pv-ann__value pv-ann__value--shown" : "pv-ann__value"}
                        aria-current={shown || undefined}
                        onClick={() => show(f.key, v, count)}
                      >
                        {v}
                        <span className="pv-ann__count" aria-hidden="true">
                          {count}
                        </span>
                        <span className="visually-hidden">{` (${count} in the text)`}</span>
                      </button>
                    );
                  })}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </div>
      {failedStep && (
        <p className="pv-ann__problem">
          {`The last run failed: ${annotateReason(failedStep.error_class)}`}
        </p>
      )}
      <div className="pv-ann__actions">
        <GlassButton ref={editButton} tint="clear" size="sm" disabled={busy} onClick={edit}>
          Edit
        </GlassButton>
        {curated && (
          <GlassButton tint="clear" size="sm" disabled={busy} onClick={() => void reset()}>
            Reset to model
          </GlassButton>
        )}
      </div>
    </>
  );
}
