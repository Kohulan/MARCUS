import { Fragment, memo, useCallback, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { useSteps, useText } from "../api/queries";
import { reasonText } from "../api/reasons";
import { isPaperBusy, isStepActive } from "../api/status";
import type { AnnotationHit, StepOut } from "../api/types";
import { GlassButton } from "../ui/GlassButton";
import { usePrefersReducedMotion } from "../ui/motion";
import { saveBlob } from "../ui/saveBlob";
import AnnotationPanel from "./AnnotationPanel";
import {
  blockRanges,
  hitsOf,
  newestAnnotate,
  nextHit,
  shownPositions,
  splitMarks,
  type HitAt,
  type Span,
} from "./annotation";
import { doclingBlocks, type TextBlock } from "./doclingText";
import { newestFirst } from "./pageFailures";
import { useAnnotation, useAnnotationActions } from "./useAnnotation";

const NO_BLOCKS: TextBlock[] = [];
const NO_STEPS: StepOut[] = [];
const NO_RANGES = new Map<number, Span[]>();

/** Scrolls `container` so `el` sits in its middle (an occurrence keeps text around it). */
function scrollToMiddle(container: HTMLElement | null, el: Element | null, smooth: boolean) {
  if (!container || !el) return;
  const c = container.getBoundingClientRect();
  const r = el.getBoundingClientRect();
  const top = container.scrollTop + (r.top - c.top) - (c.height - r.height) / 2;
  if (typeof container.scrollTo === "function") {
    container.scrollTo({ top, behavior: smooth ? "smooth" : "auto" });
  } else {
    container.scrollTop = top;
  }
}

/**
 * One block of the text: plain, or cut into pieces with the annotation's values marked
 * (`<mark>` elements around React text nodes; never HTML from the text). The current
 * occurrence carries data-current, so it can be scrolled to.
 */
const Block = memo(function Block({
  block,
  spans,
  current,
}: {
  block: TextBlock;
  spans: Span[] | undefined;
  current: Span | null;
}) {
  const content =
    spans || current
      ? splitMarks(block.text, spans ?? [], current).map((p, i) =>
          p.mark ? (
            <mark
              key={i}
              className={p.current ? "pv-mark pv-mark--current" : "pv-mark"}
              data-current={p.current || undefined}
            >
              {p.text}
            </mark>
          ) : (
            <Fragment key={i}>{p.text}</Fragment>
          ),
        )
      : block.text;
  return block.kind === "heading" ? (
    <h3 className="pv-text__heading">{content}</h3>
  ) : (
    <p className="pv-text__para">{content}</p>
  );
});

/** The paper's newest docling step. */
const newestDocling = (steps: StepOut[]): StepOut | undefined =>
  newestFirst(steps.filter((s) => s.kind === "docling"))[0];

/** "alkaloids.pdf" → "alkaloids.txt": one trailing ".pdf" (any case) gives way to ".txt". */
const textFileName = (displayName: string) => `${displayName.replace(/\.pdf$/i, "")}.txt`;

/** Saves the blocks, joined by blank lines, as `<name>.txt`. */
function download(blocks: TextBlock[], name: string) {
  const text = blocks.map((b) => b.text).join("\n\n");
  saveBlob(new Blob([text], { type: "text/plain;charset=utf-8" }), textFileName(name));
}

/**
 * The middle column of the Paper view: the paper's text from Docling, its download, and its
 * annotation (Annotate, then the values, marked in the text). The text file can be large: it
 * is asked for only here (the Paper view is open) and only once the docling step is done, or
 * when the paper has no docling step and is not being worked on (the server answers 404 if it
 * has none). The annotation sits above the text, which scrolls on its own, so a value can be
 * clicked again (its next occurrence) while the text shows the last one.
 */
export default function TextColumn({
  paperId,
  displayName,
  paperStatus,
  onStarted,
}: {
  paperId: string;
  displayName: string;
  paperStatus: string;
  /** After an annotation started: the live stream opens again, the steps are read. */
  onStarted: () => void;
}) {
  const headId = useId();
  const reduce = usePrefersReducedMotion();
  const scroller = useRef<HTMLDivElement>(null);
  // The workspace's steps query (cached, no second request): until it has answered, a
  // failed or running docling step cannot be told from none.
  const stepsQuery = useSteps(paperId);
  const known = stepsQuery.data !== undefined || stepsQuery.isError;
  const steps = stepsQuery.data?.steps ?? NO_STEPS;
  const docling = newestDocling(steps);
  const failed = docling?.status === "failed";
  const waiting =
    !known ||
    (docling === undefined ? isPaperBusy(paperStatus) : isStepActive(docling.status));
  const text = useText(paperId, !failed && !waiting);
  const blocks = useMemo(() => (text.data ? doclingBlocks(text.data) : NO_BLOCKS), [text.data]);

  const annotation = useAnnotation(paperId, steps).data;
  const actions = useAnnotationActions(paperId, onStarted);
  const annStep = newestAnnotate(steps);
  // The step a start made, until the steps show it (then its own status says).
  const [startedId, setStartedId] = useState<string | null>(null);
  const running =
    (annStep !== undefined && isStepActive(annStep.status)) ||
    (startedId !== null && !steps.some((s) => s.id === startedId));
  const values = annotation?.values ?? null;
  const positions = useMemo(() => (annotation ? shownPositions(annotation) : {}), [annotation]);
  const ranges = useMemo(
    () => (values ? blockRanges(values, positions) : NO_RANGES),
    [values, positions],
  );
  const [at, setAt] = useState<HitAt | null>(null);
  const hit: AnnotationHit | undefined = at
    ? hitsOf(positions, at.field, at.value)[at.index]
    : undefined;

  const show = useCallback(
    (field: string, value: string): number => {
      const index = nextHit(at, field, value, hitsOf(positions, field, value).length);
      setAt({ field, value, index });
      return index;
    },
    [at, positions],
  );
  const start = useCallback(async () => {
    const out = await actions.start();
    if (out.step_id !== null) setStartedId(out.step_id);
  }, [actions]);

  // A click (or the annotation changing under it) brings the shown occurrence into view.
  useLayoutEffect(() => {
    if (!at) return;
    scrollToMiddle(scroller.current, scroller.current?.querySelector("[data-current]") ?? null, !reduce);
  }, [at, hit, reduce]);

  const notReady = waiting || (text.error instanceof ApiError && text.error.status === 404);
  let body;
  if (failed) {
    body = (
      <p className="pv-text__state">{`The text could not be read: ${reasonText(docling.error_class)}`}</p>
    );
  } else if (notReady) {
    body = <p className="pv-text__state">The text of this paper is not ready</p>;
  } else if (text.isError) {
    body = (
      <div className="pv-text__state">
        <p>The text could not be loaded.</p>
        <GlassButton tint="clear" size="sm" onClick={() => void text.refetch()}>
          Try again
        </GlassButton>
      </div>
    );
  } else if (!text.data) {
    body = (
      <p className="pv-text__state" role="status">
        Loading the text…
      </p>
    );
  } else if (blocks.length === 0) {
    body = <p className="pv-text__state">No text was found in this paper.</p>;
  } else {
    body = (
      <div className="pv-text__body">
        {blocks.map((b, i) => (
          <Block
            key={i}
            block={b}
            spans={ranges.get(i)}
            current={hit && hit[0] === i ? [hit[1], hit[2]] : null}
          />
        ))}
      </div>
    );
  }

  return (
    <section className="pv-col pv-col--text" aria-labelledby={headId}>
      <div className="pv-cap">
        <h2 id={headId} className="pv-cap__title">
          Text
        </h2>
        {blocks.length > 0 && (
          <GlassButton tint="clear" size="sm" onClick={() => download(blocks, displayName)}>
            Download text
          </GlassButton>
        )}
      </div>
      {blocks.length > 0 && annotation?.available && (
        <AnnotationPanel
          annotation={annotation}
          running={running}
          step={annStep}
          at={at}
          onShow={show}
          onStart={start}
          onSave={actions.save}
          onReset={actions.reset}
        />
      )}
      {/* Scrolls on its own; focusable, so the keys scroll it too. */}
      <div className="pv-text" ref={scroller} tabIndex={0} role="group" aria-label="Paper text">
        {body}
      </div>
    </section>
  );
}
