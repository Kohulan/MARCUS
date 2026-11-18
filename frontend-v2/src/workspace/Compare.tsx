import { useQueries, type UseQueryResult } from "@tanstack/react-query";
import { useId, useMemo, useRef, useState, type ReactNode } from "react";
import { api, errorText } from "../api/client";
import { useDepiction } from "../api/depictions";
import { asEngine } from "../api/engines";
import { useSaveCuration } from "../api/queries";
import type { DepictReply, PredictionOut, SegmentOut, StepOut } from "../api/types";
import { GlassButton } from "../ui/GlassButton";
import { Modal } from "../ui/modal";
import Smiles from "../ui/Smiles";
import SpecimenLabel from "../ui/SpecimenLabel";
import StateBadge from "../ui/StateBadge";
import Structure from "../ui/Structure";
import { useToast } from "../ui/Toasts";
import { ocsrSteps } from "./cardState";
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
  /** Given: Compare is a modal dialog (Close, Esc, the backdrop). Without: a page section. */
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
  const closeButton = useRef<HTMLButtonElement>(null);
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
    (runError !== null ? `Not started: ${errorText(runError)}` : null) ??
    toolErrors.map(tooManyText).find((t) => t !== null) ??
    (common && part.errors.length > 0 ? "Common part unavailable" : null) ??
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
                    <span className="cmp-table__none">
                      <span aria-hidden="true">–</span>
                      <span className="visually-hidden">None</span>
                    </span>
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
              pressed={common && canCommon}
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
    <Modal
      className="cmp cmp--dialog"
      labelledBy={titleId}
      onClose={onClose}
      first={closeButton}
      backdropClose
    >
      <div className="cmp__head">
        {title}
        <GlassButton ref={closeButton} tint="clear" size="sm" onClick={onClose}>
          Close
        </GlassButton>
      </div>
      {body}
    </Modal>
  );
}

function resultText(r: EngineRow): ReactNode {
  if (r.prediction) return r.prediction.valid ? "Valid" : "Invalid";
  if (r.state === "reading") return "Reading…";
  if (r.state === "failed") return `Failed: ${r.reason}`;
  return <StateBadge state="not-read" />;
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
  // Not read yet: the word in the blank too (the Result row says it to a screen reader).
  if (!p)
    return (
      <div className={`cmp-blank cmp-blank--${row.state}${row.state === "failed" ? " hatch" : ""}`}>
        {row.state === "idle" && (
          <span aria-hidden="true">
            <StateBadge state="not-read" />
          </span>
        )}
      </div>
    );
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
  const { src, failed, retry } = useDepiction(api.depictionUrl(segmentId, prediction.id, engine));
  return <Structure src={src} failed={failed} onRetry={retry ?? undefined} alt={alt} />;
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
  onSaved,
}: {
  paperId: string;
  segment: SegmentOut;
  /** The paper's steps (the segment's own are picked here). */
  steps: StepOut[];
  tag: string;
  onStarted: () => void;
  onClose: () => void;
  /** After a "Use this one" save landed (the card may have lost the button focus was on). */
  onSaved?: (() => void) | undefined;
}) {
  const { save } = useSaveCuration(paperId);
  const toast = useToast();
  const own = useMemo(() => ocsrSteps(segment, steps), [segment, steps]);
  const pick = (p: PredictionOut) => {
    onClose();
    save(segment.id, {
      status: "accepted",
      structure: { smiles: p.smiles, molfile: p.molfile ?? null },
    }).then(
      () => onSaved?.(),
      (err: unknown) => toast(`Not saved: ${errorText(err)}`, "error"),
    );
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
