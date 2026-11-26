import { useQueries, type UseQueryResult } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { api, errorText } from "../api/client";
import { depictQuery, useReplyUrl } from "../api/depictions";
import {
  asEngine,
  firstRunNote,
  orientationTemplate,
  TEMPLATE_ENGINES,
  usableTemplate,
} from "../api/engines";
import { useSaveCuration } from "../api/queries";
import type { DepictReply, Engine, PredictionOut, SegmentOut, StepOut } from "../api/types";
import { GlassButton } from "../ui/GlassButton";
import { Modal } from "../ui/modal";
import ProgressBar, { useHeldAfter } from "../ui/ProgressBar";
import { END_HOLD_MS } from "../ui/progressMotion";
import Smiles from "../ui/Smiles";
import SpecimenLabel from "../ui/SpecimenLabel";
import StateBadge from "../ui/StateBadge";
import Structure from "../ui/Structure";
import { useToast } from "../ui/Toasts";
import { drawable, ocsrSteps } from "./cardState";
import {
  engineRows,
  enginesToRun,
  tooManyText,
  useCommonPart,
  useEngineRuns,
  useSimilarity,
  type CompareStep,
  type CompareTarget,
  type EngineRow,
} from "./useCompare";
import { resultWord } from "./rgroups";
import "./compare.css";

export type CompareProps = {
  target: CompareTarget;
  /** The target's predictions, newest first. */
  predictions: PredictionOut[];
  /** Its OCSR steps, newest first. */
  steps: CompareStep[];
  /** "Use this one". */
  onPick: (p: PredictionOut) => void;
  /** After an engine start was accepted: the page reopens its own live stream. */
  onStarted: () => void;
  /** Given: Compare is a modal dialog (Close, Esc, the backdrop). Without: a page section. */
  onClose?: (() => void) | undefined;
  /** The structure's `[nn]` tag, beside the title. */
  tag?: string | undefined;
  /** As a page section (no `onClose`): a control at the end of the head (the page's Close). */
  headAction?: ReactNode;
  /** The paper or image was uploaded with DECIMER hand-drawn: Hand-drawn starts on. */
  handDrawn?: boolean | undefined;
};

/**
 * Compare engines: the image the engines read (the paper's crop, or the uploaded image), then
 * each engine's result side by side (drawing, SMILES, validity), the
 * pairwise Tanimoto similarity, "Show common part" (the MCS highlighted in every drawing),
 * and "Use this one". Opening it starts every engine not read and not running, at once; a
 * failed engine has its own Retry.
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
  handDrawn = false,
}: CompareProps) {
  const titleId = useId();
  const closeButton = useRef<HTMLButtonElement>(null);
  const { requested, batch, sending, error: runError, run } = useEngineRuns(target, steps, onStarted);
  // The DECIMER column shows the hand-drawn model while this is on: on opening, on only where
  // the upload chose DECIMER hand-drawn.
  const [hand, setHand] = useState(handDrawn);
  const rows = useMemo(
    () => engineRows(predictions, steps, requested, hand),
    [predictions, steps, requested, hand],
  );
  const toggleHand = () => {
    const on = !hand;
    setHand(on);
    // On: read it now unless it is read or running (its first run loads the model).
    if (on) run(enginesToRun(engineRows(predictions, steps, requested, true)).filter((e) => e === "decimer-hand"));
  };
  // Opening starts the engines not read yet, once (the ref holds across a strict-mode remount).
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current) return;
    opened.current = true;
    run(enginesToRun(rows));
  }, [run, rows]);
  // The last start: engines read (or failed) of those it started; the bar stays on its full
  // figure for a moment once every one has answered.
  const batchRows = rows.filter((r) => batch.includes(r.engine));
  const batchDone = batchRows.filter((r) => r.state !== "reading").length;
  const batchRunning = batch.length > 0 && (sending || batchDone < batchRows.length);
  const showBatch = useHeldAfter(batchRunning, END_HOLD_MS) && batchRows.length > 0;
  const pairs = useSimilarity(rows);
  // The common part of every structure drawn, DECIMER's R-group answer ([R1]) too: its molfile
  // comes from CDK, as in v1 (owner, 2026-11-26).
  const drawn = rows.filter((r) => r.prediction !== null && drawable(r.prediction));
  const canCommon = new Set(drawn.map((r) => r.prediction!.smiles)).size >= 2;
  const [common, setCommon] = useState(false);
  const part = useCommonPart(
    drawn.map((r) => r.prediction!),
    common,
  );

  // "Use coordinates" of MolScribe and MolNexTR (old papers; never MolParser, which has no image
  // positions) (on at every opening; this dialog only). On: the
  // engine's drawing uses its own positions from the image, and it can be the template of the
  // others (MolScribe first). Off, or a molfile without the image's positions: the normal layout,
  // and no template.
  const [coords, setCoords] = useState<Readonly<Record<string, boolean>>>({});
  const coordsOn = (engine: string) => coords[engine] !== false;
  const shared = orientationTemplate(predictions, coords);
  const templateOf = (r: EngineRow): PredictionOut | null =>
    TEMPLATE_ENGINES.includes(r.engine)
      ? coordsOn(r.engine) && usableTemplate(r.prediction)
        ? r.prediction
        : null
      : shared;

  // Every drawing from /tools/depict, each with its own template (the toggles decide), and with
  // the common part when it is shown. DECIMER's R-group scaffold ([R1], invalid for RDKit) is
  // drawn too (CDK reads it; owner, 2026-11-26), never highlighted (the highlight is RDKit's).
  const depicts = useQueries({
    queries: drawn.map((r) =>
      depictQuery(
        r.prediction!.smiles,
        r.prediction!.valid ? part.highlight : null,
        part.renew,
        templateOf(r),
      ),
    ),
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
              <th scope="col" className="cmp-table__engine cmp-table__source">
                <span className="cmp-table__name">{target.kind === "image" ? "Image" : "Paper"}</span>
              </th>
              {rows.map((r, i) => (
                <th key={colKey(r, i)} scope="col" className="cmp-table__engine">
                  <span className="cmp-table__name">{r.label}</span>
                  {r.prediction && (
                    <span className="cmp-table__version">{r.prediction.engine_version}</span>
                  )}
                  {i === 0 && (
                    <span className="cmp-table__toggle">
                      <GlassButton tint="clear" size="sm" pressed={hand} onClick={toggleHand}>
                        Hand-drawn
                      </GlassButton>
                    </span>
                  )}
                  {TEMPLATE_ENGINES.includes(r.engine) && r.prediction?.molfile && (
                    <span className="cmp-table__toggle">
                      <GlassButton
                        tint="clear"
                        size="sm"
                        label={`Use coordinates, ${r.label}`}
                        disabled={!usableTemplate(r.prediction)}
                        pressed={usableTemplate(r.prediction) && coordsOn(r.engine)}
                        onClick={() => setCoords((c) => ({ ...c, [r.engine]: !coordsOn(r.engine) }))}
                      >
                        Use coordinates
                      </GlassButton>
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Drawing</th>
              {/* What the engines read, beside their drawings (one cell down the column). */}
              <td rowSpan={4} className="cmp-table__figure cmp-table__source">
                <Structure
                  src={target.kind === "image" ? api.imageUrl(target.id) : api.segmentImageUrl(target.id)}
                  alt={target.kind === "image" ? "The uploaded image" : "Crop from the paper"}
                />
              </td>
              {rows.map((r) => (
                <td key={r.engine} className="cmp-table__figure">
                  <Drawing row={r} depict={depictOf(r)} />
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
                  {/* offered engines only: an old paper's MolNexTR shows its result, no Retry */}
                  {r.state === "failed" && asEngine(r.engine) !== null && (
                    <span className="cmp-result__retry">
                      <GlassButton
                        tint="clear"
                        size="sm"
                        label={`Retry, ${r.label}`}
                        disabled={sending}
                        onClick={() => run([r.engine as Engine])}
                      >
                        Retry
                      </GlassButton>
                    </span>
                  )}
                </td>
              ))}
            </tr>
            <tr>
              <td className="cmp-table__corner" />
              {rows.map((r) => (
                <td key={r.engine} className="cmp-table__use">
                  {r.prediction && drawable(r.prediction) && (
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
              disabled={!canCommon}
              pressed={common && canCommon}
              onClick={() => setCommon((c) => !c)}
            >
              Show common part
            </GlassButton>
          </div>
          {showBatch && (
            <div className="cmp__run">
              <ProgressBar
                value={batchDone / batchRows.length}
                label="Engines"
                valueText={`Engines read, ${batchDone} of ${batchRows.length}`}
                active={batchRunning}
                size="sm"
              />
              <p className="cmp__run-line">{`Running engines ${batchDone}/${batchRows.length}`}</p>
            </div>
          )}
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

/** A column's key: the DECIMER column keeps its own whichever model it shows (the toggle in
 * its head keeps focus). */
const colKey = (r: EngineRow, i: number) => (i === 0 ? "decimer-column" : r.engine);

function resultText(r: EngineRow): ReactNode {
  if (r.prediction) return resultWord(r.prediction);
  if (r.state === "reading") {
    const note = firstRunNote(r.engine);
    return (
      <>
        Reading…
        <ProgressBar value={null} label={`Reading, ${r.label}`} size="sm" className="cmp-result__bar" />
        {note && <span className="cmp-result__note">{note}</span>}
      </>
    );
  }
  if (r.state === "failed") return `Failed: ${r.reason}`;
  return <StateBadge state="not-read" />;
}

function resultTone(r: EngineRow): string {
  if (r.prediction) return r.prediction.valid ? "valid" : "invalid";
  return r.state;
}

/** One engine's drawing: a /tools/depict reply. */
function Drawing({
  row,
  depict,
}: {
  row: EngineRow;
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
  if (!drawable(p) || !depict) return <Structure src={null} failed alt="" />;
  return <ReplyDrawing query={depict} alt={`Structure, ${row.label}`} />;
}

function ReplyDrawing({ query, alt }: { query: UseQueryResult<DepictReply>; alt: string }) {
  const src = useReplyUrl(query.data);
  return <Structure src={src} failed={query.isError} alt={alt} />;
}

/**
 * Compare for a segment of the paper workspace: its predictions and OCSR steps, and "Use
 * this one" accepts that engine's structure (curationBody keeps the note; the curated
 * molfile is replaced, so it never describes another structure). Closes on a pick; a save
 * that fails says so.
 */
export function SegmentCompare({
  paperId,
  paperEngine,
  segment,
  steps,
  tag,
  onStarted,
  onClose,
  onSaved,
}: {
  paperId: string;
  /** The engine the paper was uploaded with (DECIMER hand-drawn: Hand-drawn starts on). */
  paperEngine: string;
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
    // DECIMER's R-group answer ([R1], [X]) RDKit cannot read: saved as CDK's molfile of it,
    // which RDKit reads with its R atoms (as v1 did; owner, 2026-11-26).
    const structure = p.valid
      ? Promise.resolve({ smiles: p.smiles, molfile: p.molfile ?? null })
      : api.smilesToMolfile(p.smiles).then((molfile) => ({ smiles: null, molfile }));
    structure
      .then((s) => save(segment.id, { status: "accepted", structure: s }))
      .then(
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
      handDrawn={paperEngine === "decimer-hand"}
    />
  );
}
