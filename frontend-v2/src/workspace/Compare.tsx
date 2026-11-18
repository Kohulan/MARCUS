import { useQueries, type UseQueryResult } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { api } from "../api/client";
import { useDepiction } from "../api/depictions";
import { asEngine } from "../api/engines";
import { useSaveCuration } from "../api/queries";
import type { DepictReply, PredictionOut, SegmentOut, StepOut } from "../api/types";
import { GlassButton } from "../ui/GlassButton";
import Smiles from "../ui/Smiles";
import SpecimenLabel from "../ui/SpecimenLabel";
import Structure from "../ui/Structure";
import { structureTag } from "../ui/tag";
import { useToast } from "../ui/Toasts";
import { ocsrSteps } from "./cardState";
import { trapTab } from "./KeyHelp";
import { errorDetail } from "./useCardActions";
import type { ReviewRow } from "./useReviewRows";
import type { Workspace } from "./useWorkspace";
import {
  depictQuery,
  engineRows,
  enginesToRun,
  tooManyText,
  useCommonPart,
  useReplyUrl,
  useRunAll,
  useSimilarity,
  type CompareStep,
  type CompareTarget,
  type EngineRow,
} from "./useCompare";
import "./compare.css";

export type CompareProps = {
  target: CompareTarget;
  /** The target's predictions, newest first. */
  predictions: PredictionOut[];
  /** Its OCSR steps, newest first. */
  steps: CompareStep[];
  /** "Use this one". */
  onPick: (p: PredictionOut) => void;
  /** After "Run all engines" was accepted: the page reopens its own live stream. */
  onStarted: () => void;
  /** Given: Compare is a modal dialog (Close, Esc, a focus trap). Without: a page section. */
  onClose?: (() => void) | undefined;
  /** The structure's `[nn]` tag, beside the title. */
  tag?: string | undefined;
  /** As a page section (no `onClose`): a control at the end of the head (the page's Close). */
  headAction?: ReactNode;
};

/**
 * Compare engines: each engine's result side by side (drawing, SMILES, validity), the
 * pairwise Tanimoto similarity, "Show common part" (the MCS highlighted in every drawing),
 * "Run all engines" for the ones not read yet, and "Use this one".
 */
export default function Compare({
  target,
  predictions,
  steps,
  onPick,
  onStarted,
  onClose,
  tag,
  headAction,
}: CompareProps) {
  const titleId = useId();
  const { requested, sending, error: runError, runAll } = useRunAll(target, steps, onStarted);
  const rows = useMemo(
    () => engineRows(predictions, steps, requested),
    [predictions, steps, requested],
  );
  const toRun = enginesToRun(rows);
  const pairs = useSimilarity(rows);
  const validSmiles = rows.filter((r) => r.prediction?.valid).map((r) => r.prediction!.smiles);
  const canCommon = new Set(validSmiles).size >= 2;
  const [common, setCommon] = useState(false);
  const part = useCommonPart(validSmiles, common);

  // Drawings from /tools/depict: every one with the common part, and an image job's always
  // (a segment's plain drawing is its stored depiction, free of the tools bucket).
  const viaTools = (r: EngineRow) =>
    r.prediction?.valid === true &&
    (part.highlight !== null || target.kind === "image" || asEngine(r.engine) === null);
  const drawn = rows.filter(viaTools);
  const depicts = useQueries({
    queries: drawn.map((r) => depictQuery(r.prediction!.smiles, part.highlight)),
  });
  const depictOf = (r: EngineRow) => {
    const i = drawn.indexOf(r);
    return i < 0 ? undefined : depicts[i];
  };

  const toolErrors = [
    ...pairs.map((p) => p.error),
    ...part.errors,
    ...depicts.map((q) => q.error),
  ];
  const message =
    tooManyText(runError) ??
    (runError !== null ? `Not started: ${errorDetail(runError)}` : null) ??
    toolErrors.map(tooManyText).find((t) => t !== null) ??
    (part.none ? "No common part" : null);

  const title = (
    <h2 id={titleId} className="cmp__title">
      Compare engines
      {tag && <span className="cmp__tag">{tag}</span>}
    </h2>
  );

  const body = (
    <>
      <div className="cmp__scroll">
        <table className="cmp-table">
          <caption className="visually-hidden">Engines</caption>
          <thead>
            <tr>
              <td className="cmp-table__corner" />
              {rows.map((r) => (
                <th key={r.engine} scope="col" className="cmp-table__engine">
                  <span className="cmp-table__name">{r.label}</span>
                  {r.prediction && (
                    <span className="cmp-table__version">{r.prediction.engine_version}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Drawing</th>
              {rows.map((r) => (
                <td key={r.engine} className="cmp-table__figure">
                  <Drawing row={r} target={target} depict={depictOf(r)} />
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row">SMILES</th>
              {rows.map((r) => (
                <td key={r.engine}>
                  {r.prediction && r.prediction.smiles !== "" ? (
                    <Smiles value={r.prediction.smiles} />
                  ) : (
                    <span className="cmp-table__none">None</span>
                  )}
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row">Result</th>
              {rows.map((r) => (
                <td key={r.engine} className={`cmp-result cmp-result--${resultTone(r)}`}>
                  {resultText(r)}
                </td>
              ))}
            </tr>
            <tr>
              <td className="cmp-table__corner" />
              {rows.map((r) => (
                <td key={r.engine} className="cmp-table__use">
                  {r.prediction?.valid && (
                    <GlassButton
                      tint="green"
                      size="sm"
                      label={`Use this one, ${r.label}`}
                      onClick={() => onPick(r.prediction!)}
                    >
                      Use this one
                    </GlassButton>
                  )}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      <div className="cmp__foot">
        {pairs.length > 0 && (
          <div className="cmp__similarity">
            <SpecimenLabel
              title="Similarity"
              rows={pairs.map((p): [string, ReactNode] => [
                `${p.a} · ${p.b}`,
                <span key="v" className="cmp-score">
                  {p.value !== null ? p.value.toFixed(2) : p.error ? "Unavailable" : "…"}
                </span>,
              ])}
            />
          </div>
        )}
        <div className="cmp__side">
          <div className="cmp__actions glassbed">
            <GlassButton
              tint="clear"
              size="sm"
              disabled={toRun.length === 0 || sending}
              onClick={() => runAll(toRun)}
            >
              Run all engines
            </GlassButton>
            <GlassButton
              tint="clear"
              size="sm"
              disabled={!canCommon}
              pressed={common}
              onClick={() => setCommon((c) => !c)}
            >
              Show common part
            </GlassButton>
          </div>
          <p className="cmp__msg" role="status">
            {message}
          </p>
        </div>
      </div>
    </>
  );

  if (!onClose) {
    return (
      <section className="cmp cmp--inline" aria-labelledby={titleId}>
        <div className="cmp__head">
          {title}
          {headAction}
        </div>
        {body}
      </section>
    );
  }
  return (
    <CompareDialog titleId={titleId} title={title} onClose={onClose}>
      {body}
    </CompareDialog>
  );
}

/**
 * The modal frame: focus moves in (to Close), Tab stays inside, Esc or Close closes it and
 * focus goes back. Keys pressed inside stop here, so a page's own shortcuts (the review keys
 * of focus mode) never act on the structure underneath.
 */
function CompareDialog({
  titleId,
  title,
  onClose,
  children,
}: {
  titleId: string;
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
}) {
  const box = useRef<HTMLDivElement>(null);
  const close = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const before = document.activeElement;
    close.current?.focus();
    return () => {
      if (before instanceof HTMLElement && before.isConnected) before.focus();
    };
  }, []);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    e.stopPropagation();
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
      return;
    }
    trapTab(e, box.current);
  };

  return (
    <div className="cmp-scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={box}
        className="cmp"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={onKeyDown}
      >
        <div className="cmp__head">
          {title}
          <button ref={close} type="button" className="cmp__close" onClick={onClose}>
            Close
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function resultText(r: EngineRow): string {
  if (r.prediction) return r.prediction.valid ? "Valid" : "Invalid";
  if (r.state === "reading") return "Reading…";
  if (r.state === "failed") return `Failed: ${r.reason}`;
  return "Not read yet";
}

function resultTone(r: EngineRow): string {
  if (r.prediction) return r.prediction.valid ? "valid" : "invalid";
  return r.state;
}

/** One engine's drawing: the stored depiction (segments) or a /tools/depict reply. */
function Drawing({
  row,
  target,
  depict,
}: {
  row: EngineRow;
  target: CompareTarget;
  depict: UseQueryResult<DepictReply> | undefined;
}) {
  const p = row.prediction;
  if (!p) return <div className={`cmp-blank cmp-blank--${row.state}`} />;
  if (!p.valid) return <Structure src={null} failed alt="" />;
  if (depict) return <ReplyDrawing query={depict} alt={`Structure, ${row.label}`} />;
  return <StoredDrawing segmentId={target.id} prediction={p} alt={`Structure, ${row.label}`} />;
}

function ReplyDrawing({ query, alt }: { query: UseQueryResult<DepictReply>; alt: string }) {
  const src = useReplyUrl(query.data);
  return <Structure src={src} failed={query.isError} alt={alt} />;
}

function StoredDrawing({
  segmentId,
  prediction,
  alt,
}: {
  segmentId: string;
  prediction: PredictionOut;
  alt: string;
}) {
  const engine = asEngine(prediction.engine) ?? undefined;
  const { src, failed } = useDepiction(api.depictionUrl(segmentId, prediction.id, engine));
  return <Structure src={src} failed={failed} alt={alt} />;
}

/**
 * Compare for a segment of the paper workspace: its predictions and OCSR steps, and "Use
 * this one" accepts that engine's structure (curationBody keeps the note; the curated
 * molfile is replaced, so it never describes another structure). Closes on a pick; a save
 * that fails says so.
 */
export function SegmentCompare({
  paperId,
  segment,
  steps,
  tag,
  onStarted,
  onClose,
}: {
  paperId: string;
  segment: SegmentOut;
  /** The paper's steps (the segment's own are picked here). */
  steps: StepOut[];
  tag: string;
  onStarted: () => void;
  onClose: () => void;
}) {
  const { save } = useSaveCuration(paperId);
  const toast = useToast();
  const own = useMemo(() => ocsrSteps(segment, steps), [segment, steps]);
  const pick = (p: PredictionOut) => {
    onClose();
    save(segment.id, {
      status: "accepted",
      structure: { smiles: p.smiles, molfile: p.molfile ?? null },
    }).catch((err: unknown) => toast(`Not saved: ${errorDetail(err)}`, "error"));
  };
  return (
    <Compare
      target={{ kind: "segment", id: segment.id }}
      predictions={segment.predictions}
      steps={own}
      onPick={pick}
      onStarted={onStarted}
      onClose={onClose}
      tag={tag}
    />
  );
}

/** Compare opened from a card (grid or Paper view): the segment by id, its `[nn]` tag. */
export function CardCompare({
  ws,
  rows,
  segmentId,
  onStarted,
  onClose,
}: {
  ws: Workspace;
  rows: ReviewRow[];
  segmentId: string;
  onStarted: () => void;
  onClose: () => void;
}) {
  const segment = ws.segments.find((s) => s.id === segmentId);
  const n = rows.find((r) => r.segmentId === segmentId)?.n;
  if (!ws.paper || !segment || n === undefined) return null;
  return (
    <SegmentCompare
      paperId={ws.paper.id}
      segment={segment}
      steps={ws.steps}
      tag={structureTag(n)}
      onStarted={onStarted}
      onClose={onClose}
    />
  );
}
