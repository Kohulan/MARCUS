import { useQueries, useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { api, errorText } from "../api/client";
import { depictQuery, useReplyUrl } from "../api/depictions";
import {
  asEngine,
  firstRunNote,
  layoutInfo,
  layoutPrediction,
  layoutTemplate,
  orientationTemplate,
  TEMPLATE_ENGINES,
  usableTemplate,
  type Template,
} from "../api/engines";
import { useSaveCuration } from "../api/queries";
import type {
  DepictReply,
  Engine,
  OverlayAnswer,
  OverlayReply,
  PredictionOut,
  SegmentOut,
  StepOut,
} from "../api/types";
import { GlassButton } from "../ui/GlassButton";
import SegmentedControl, { type SegmentedOption } from "../ui/SegmentedControl";
import Switch from "../ui/Switch";
import { Modal } from "../ui/modal";
import ProgressBar, { useHeldAfter } from "../ui/ProgressBar";
import { END_HOLD_MS } from "../ui/progressMotion";
import Smiles from "../ui/Smiles";
import SpecimenLabel from "../ui/SpecimenLabel";
import StateBadge from "../ui/StateBadge";
import Structure from "../ui/Structure";
import { useToast } from "../ui/Toasts";
import { drawable, ocsrSteps } from "./cardState";
import { SegmentEditor } from "./SegmentEditor";
import {
  engineRows,
  enginesToRun,
  tooManyText,
  useDifferences,
  useEngineRuns,
  useSimilarity,
  type CompareStep,
  type CompareTarget,
  type EngineRow,
  type MarkMode,
} from "./useCompare";
import { resultWord } from "./rgroups";
import "./compare.css";

export type CompareProps = {
  target: CompareTarget;
  /** The target's predictions, newest first. */
  predictions: PredictionOut[];
  /** Its OCSR steps, newest first. */
  steps: CompareStep[];
  /** "Edit and use": open the editor on this answer (segments only). */
  onEdit?: ((p: PredictionOut) => void) | undefined;
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
 * pairwise Tanimoto similarity, what the drawings mark (Differences, from the start: the atoms
 * where an answer differs from another, orange; Common part; Off), and "Use this one". Opening it starts every engine not read and not running, at once; a
 * failed engine has its own Retry.
 */
export default function Compare({
  target,
  predictions,
  steps,
  onPick,
  onEdit,
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
  // What the drawings mark, over every structure drawn, DECIMER's R-group answer ([R1]) too
  // (owner, 2026-11-26). Differences from the start when two or more different answers are
  // drawn (owner, 2026-11-26); with fewer there is nothing to mark.
  const drawn = rows.filter((r) => r.prediction !== null && drawable(r.prediction));
  const canMark = new Set(drawn.map((r) => r.prediction!.smiles)).size >= 2;
  // Marks on (a porcelain switch) and which ones (Differences | Common part): owner, 2026-11-27
  const [marksOn, setMarksOn] = useState(true);
  const [kind, setKind] = useState<MarkKind>("differences");
  const mark: MarkMode = canMark && marksOn ? kind : "off";
  const part = useDifferences(
    drawn.map((r) => r.prediction!.smiles),
    mark,
  );

  // "Use coordinates" of MolScribe and MolNexTR (old papers; never MolParser, which has no image
  // positions) (on at every opening; this dialog only). On: the
  // engine's drawing uses its own positions from the image, and it can be the template of the
  // others (MolScribe first). Off, or a molfile without the image's positions: the normal layout,
  // and no template.
  // MolScribe's paper layout (its positions on the image, kept also when its answer is
  // invalid) comes first: every answer is drawn on it, MolScribe's own too, and its "Use
  // coordinates" switches it off with the rest.
  const [coords, setCoords] = useState<Readonly<Record<string, boolean>>>({});
  const coordsOn = (engine: string) => coords[engine] !== false;
  const shared = orientationTemplate(predictions, coords);
  const layoutOf = layoutPrediction(predictions);
  /** The engine's own positions from the image: its layout, else its molfile's. */
  const ownTemplate = (r: EngineRow): Template | null => {
    if (layoutOf && r.engine === layoutOf.engine) return layoutTemplate(layoutOf);
    const p = r.prediction;
    return p && usableTemplate(p) ? p : null;
  };
  const templateOf = (r: EngineRow): Template | null =>
    TEMPLATE_ENGINES.includes(r.engine) ? (coordsOn(r.engine) ? ownTemplate(r) : null) : shared;

  // "Show on paper" (a paper's structure only): each answer over the crop at the drawing's own
  // positions. Offered when the layout sits on the ink (its fit within 4 % of a bond length);
  // else off, with the reason. An uploaded image has no overlay.
  const fit = layoutInfo(layoutOf?.layout);
  const paperWhy =
    target.kind !== "segment"
      ? "Papers only"
      : fit === null
        ? "No positions read"
        : !fit.overlay
          ? "Fit too poor"
          : null;
  const [paper, setPaper] = useState(false);
  const onPaper = paper && paperWhy === null;
  const drawnIds = drawn.map((r) => r.prediction!.id).join(",");
  const overlay = useQuery({
    queryKey: ["overlay", target.id, layoutOf?.id ?? null, drawnIds],
    queryFn: ({ signal }): Promise<OverlayReply> => api.segmentOverlay(target.id, { signal }),
    enabled: onPaper,
    staleTime: Infinity,
    retry: false,
  });
  const overlayOf = (r: EngineRow): OverlayAnswer | null => {
    if (!onPaper || !overlay.data || !r.prediction) return null;
    const found = overlay.data.answers.find((a) => a.prediction_id === r.prediction!.id);
    return found?.atoms && found.bonds ? found : null;
  };

  // Every drawing from /tools/depict, each with its own template (the toggles decide), and with
  // its marks. A drawing waits for the marks, so it is asked for once.
  const depicts = useQueries({
    queries: drawn.map((r) => ({
      ...depictQuery(r.prediction!.smiles, null, undefined, templateOf(r), part.of(r.prediction!.smiles)),
      enabled: part.settled,
    })),
  });
  const depictOf = (r: EngineRow) => {
    const i = drawn.indexOf(r);
    return i < 0 ? undefined : depicts[i];
  };

  const toolErrors = [...pairs.map((p) => p.error), part.error, ...depicts.map((q) => q.error)];
  const message =
    tooManyText(runError) ??
    (runError !== null ? `Not started: ${errorText(runError)}` : null) ??
    toolErrors.map(tooManyText).find((t) => t !== null) ??
    (onPaper && overlay.isError ? "Not shown on paper" : null) ??
    (part.error ? (mark === "common" ? "Common part unavailable" : "Differences unavailable") : null) ??
    (part.none ? (mark === "common" ? "No common part" : "No differences") : null) ??
    (part.rough ? "Rough marks: the structures are large" : null);

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
                  {TEMPLATE_ENGINES.includes(r.engine) && (r.prediction?.molfile || ownTemplate(r)) && (
                    <span className="cmp-table__toggle">
                      <GlassButton
                        tint="clear"
                        size="sm"
                        label={`Use coordinates, ${r.label}`}
                        disabled={!ownTemplate(r)}
                        pressed={ownTemplate(r) !== null && coordsOn(r.engine)}
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
                {/* under the crop: each answer drawn over it (owner, 2026-11-27) */}
                <div className="cmp-table__onpaper">
                  <GlassButton
                    tint="clear"
                    size="sm"
                    disabled={paperWhy !== null}
                    pressed={onPaper}
                    onClick={() => setPaper((p) => !p)}
                  >
                    Show on paper
                  </GlassButton>
                  {paperWhy !== null && <span className="cmp__why">{paperWhy}</span>}
                </div>
              </td>
              {rows.map((r) => (
                <td key={r.engine} className="cmp-table__figure">
                  {overlayOf(r) ? (
                    <OnPaper
                      answer={overlayOf(r)!}
                      view={overlay.data!}
                      src={api.segmentImageUrl(target.id)}
                      label={r.label}
                    />
                  ) : (
                    <Drawing row={r} depict={depictOf(r)} />
                  )}
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
                    <>
                      <GlassButton
                        tint="green"
                        size="sm"
                        label={`Use this one, ${r.label}`}
                        onClick={() => onPick(r.prediction!)}
                      >
                        Use this one
                      </GlassButton>
                      {onEdit && (
                        <GlassButton
                          tint="clear"
                          size="sm"
                          label={`Edit and use, ${r.label}`}
                          onClick={() => onEdit(r.prediction!)}
                        >
                          Edit and use
                        </GlassButton>
                      )}
                    </>
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
          <div className="cmp__marks" role="group" aria-label="Mark in the drawings">
            <Switch label="Marks" checked={canMark && marksOn} disabled={!canMark} onChange={setMarksOn} />
            <SegmentedControl
              label="What to mark"
              value={kind}
              options={MARK_KINDS}
              onChange={setKind}
              disabled={mark === "off"}
            />
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

type MarkKind = Exclude<MarkMode, "off">;

/** What the marks show; each knob takes its marks' own colour (the drawings' glows), so the
 * control is its own legend. */
const MARK_KINDS: readonly SegmentedOption<MarkKind>[] = [
  { value: "differences", label: "Differences", tone: { fill: "var(--orange)", ink: "var(--on-orange)", dot: "var(--orange)" } },
  { value: "common", label: "Common part", tone: { fill: "var(--common)", ink: "var(--ink)", dot: "var(--common)" } },
];

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

/**
 * One answer over the paper's crop, at the drawing's own positions (the crop's pixels): its
 * bonds in green, dashed to an atom the drawing did not place, and an orange ring on each atom
 * where the answer differs from the others. A missing or extra part shows against the ink.
 */
function OnPaper({
  answer,
  view,
  src,
  label,
}: {
  answer: OverlayAnswer;
  view: OverlayReply;
  src: string;
  label: string;
}) {
  const atoms = answer.atoms ?? [];
  const stroke = Math.max(view.bond * 0.07, 1.5);
  const lines: { key: string; x1: number; y1: number; x2: number; y2: number; loose: boolean }[] = [];
  for (const [a, b, order] of answer.bonds ?? []) {
    const p = atoms[a];
    const q = atoms[b];
    if (!p || !q) continue;
    const loose = !p[3] || !q[3];
    const length = Math.hypot(q[0] - p[0], q[1] - p[1]) || 1;
    // a double or triple bond: parallel lines, one stroke apart
    const count = order >= 3 ? 3 : order === 2 ? 2 : 1;
    const nx = (-(q[1] - p[1]) / length) * stroke * 1.4;
    const ny = ((q[0] - p[0]) / length) * stroke * 1.4;
    for (let k = 0; k < count; k++) {
      const shift = k - (count - 1) / 2;
      lines.push({
        key: `${a}-${b}-${k}`,
        x1: p[0] + nx * shift,
        y1: p[1] + ny * shift,
        x2: q[0] + nx * shift,
        y2: q[1] + ny * shift,
        loose,
      });
    }
  }
  return (
    <div className="structure cmp-paper">
      <svg
        role="img"
        aria-label={`On paper, ${label}`}
        viewBox={`0 0 ${view.width} ${view.height}`}
        preserveAspectRatio="xMidYMid meet"
      >
        <image href={src} width={view.width} height={view.height} className="cmp-paper__crop" />
        {lines.map((l) => (
          <line
            key={l.key}
            className={`cmp-paper__bond${l.loose ? " cmp-paper__bond--loose" : ""}`}
            x1={l.x1}
            y1={l.y1}
            x2={l.x2}
            y2={l.y2}
            strokeWidth={stroke}
            strokeDasharray={l.loose ? `${stroke * 2} ${stroke * 2}` : undefined}
          />
        ))}
        {answer.marks.map((i) =>
          atoms[i] ? (
            <circle
              key={i}
              className="cmp-paper__mark"
              cx={atoms[i][0]}
              cy={atoms[i][1]}
              r={view.bond * 0.28}
              strokeWidth={stroke}
            />
          ) : null,
        )}
      </svg>
    </div>
  );
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
  // "Edit and use": the editor takes Compare's place, on that engine's answer (owner, 2026-11-27)
  const [editing, setEditing] = useState<PredictionOut | null>(null);
  const pick = (p: PredictionOut) => {
    onClose();
    // DECIMER's R-group answer ([R1], [X]) is kept as it is: the server takes it (R tokens only),
    // CDK draws it and Build structures reads its labels (owner, 2026-11-26).
    save(segment.id, {
      status: "accepted",
      structure: { smiles: p.smiles, molfile: p.molfile ?? null },
    }).then(
      () => onSaved?.(),
      (err: unknown) => toast(`Not saved: ${errorText(err)}`, "error"),
    );
  };
  if (editing !== null) {
    return (
      <SegmentEditor
        paperId={paperId}
        paperEngine={paperEngine}
        segment={segment}
        start={{ smiles: editing.smiles, molfile: editing.molfile ?? null, engine: editing.engine }}
        accept
        onSaved={onSaved}
        onClose={onClose}
      />
    );
  }
  return (
    <Compare
      target={{ kind: "segment", id: segment.id }}
      predictions={segment.predictions}
      steps={own}
      onPick={pick}
      onEdit={setEditing}
      onStarted={onStarted}
      onClose={onClose}
      tag={tag}
      handDrawn={paperEngine === "decimer-hand"}
    />
  );
}
