import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { api, errorText } from "../api/client";
import { depictionKey } from "../api/depictionKey";
import { useDepiction } from "../api/depictions";
import { engineName } from "../api/engines";
import { useSaveCuration } from "../api/queries";
import type { PredictionOut, SegmentOut } from "../api/types";
import { GlassButton } from "../ui/GlassButton";
import Kbd from "../ui/Kbd";
import { usePrefersReducedMotion } from "../ui/motion";
import Smiles from "../ui/Smiles";
import SpecimenLabel from "../ui/SpecimenLabel";
import Stamp from "../ui/Stamp";
import StateBadge from "../ui/StateBadge";
import Structure from "../ui/Structure";
import { structureTag } from "../ui/tag";
import { useFocusRescue } from "../ui/focus";
import { useToast } from "../ui/Toasts";
import {
  hasDrawing,
  metaText,
  sentence,
  shownStructure,
  STATE_WORD,
  type CardState,
} from "./cardState";
import KeyHelp from "./KeyHelp";
import { boxStyle } from "./pageBox";
import StructureActions from "./StructureActions";
import { useReviewKeys } from "./useReviewKeys";
import type { ReviewRow } from "./useReviewRows";
import type { Workspace } from "./useWorkspace";
import "./focus.css";

/** After A or R the stamp lands (160 ms), then focus mode moves on (none under reduced motion). */
const ADVANCE_MS = 250;

type Decision = "accepted" | "rejected";

/** A blank note is no note. */
const noteOf = (text: string): string | null => (text.trim() === "" ? null : text);

export type FocusModeProps = {
  ws: Workspace;
  rows: ReviewRow[];
  segment: SegmentOut;
  /** Back to the grid; the grid then focuses this segment's card. */
  onClose: (segmentId: string) => void;
};

/**
 * Focus mode: one structure large, its crop, its page with the box, SMILES, the engines'
 * predictions, a note and the decision, all from the keyboard (useReviewKeys). A or R
 * lands the stamp, then moves on to the next structure still to check.
 */
export default function FocusMode({ ws, rows, segment, onClose }: FocusModeProps) {
  const paper = ws.paper!;
  const { setSelection } = ws;
  const { save } = useSaveCuration(paper.id);
  const toast = useToast();
  const reduce = usePrefersReducedMotion();
  const root = useRef<HTMLElement>(null);
  const [help, setHelp] = useState(false);
  const [draft, setDraft] = useState<{ id: string; text: string } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rowsRef = useRef(rows);
  rowsRef.current = rows;

  const id = segment.id;
  const index = rows.findIndex((r) => r.segmentId === id);
  const row = rows[index];
  const tag = structureTag(row?.n ?? index + 1);
  // The save is optimistic (useSaveCuration): a decision is in the row at once.
  const state: CardState = row?.state ?? "to-check";
  // A decision made on this structure while it is shown lands its stamp (as on a card).
  const [shownAt, setShownAt] = useState({ id, state });
  if (shownAt.id !== id) setShownAt({ id, state });
  const landed = shownAt.id === id && shownAt.state !== state;
  const stored = segment.curation?.note ?? null;
  // A structure to accept: a curated one or a valid prediction.
  const drawable = hasDrawing(segment);
  const text = draft !== null && draft.id === id ? draft.text : (stored ?? "");

  const clearTimer = () => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
  };
  useEffect(() => clearTimer, []);

  // Into view and focused on open, so the keys work at once and the region is announced.
  useEffect(() => {
    const el = root.current;
    el?.focus({ preventScroll: true });
    el?.scrollIntoView?.({ block: "start" }); // the bar at the top, the decision in view
  }, []);

  const go = useCallback(
    (to: string) => {
      clearTimer();
      setSelection(to);
    },
    [setSelection],
  );

  // After a move (a marker click turns that marker into the current one, a step can disable
  // the focused button), the keyboard stays in focus mode instead of falling to the page.
  useFocusRescue(root, [id, drawable]);

  /**
   * The review keys act only inside the region (useReviewKeys), so a step or decision made
   * with focus elsewhere (a click that leaves focus on the page body) brings it back.
   */
  const holdFocus = () => {
    const el = root.current;
    if (el && !el.contains(document.activeElement)) el.focus({ preventScroll: true });
  };

  const step = (by: -1 | 1) => {
    holdFocus();
    const to = rows[index + by];
    if (to) go(to.segmentId);
  };

  /** The next structure still to check after `from` (wrapping round), skipping decided ones. */
  const advance = (from: string) => {
    timer.current = null;
    const list = rowsRef.current;
    const at = list.findIndex((r) => r.segmentId === from);
    for (let k = 1; k < list.length; k++) {
      const r = list[(at + k + list.length) % list.length]!;
      if (r.segmentId === from) continue;
      if (r.state === "to-check") {
        go(r.segmentId);
        return;
      }
    }
  };

  const decide = (status: Decision) => {
    if (status === "accepted" && !drawable) return; // nothing to accept (ruling on F7 M2)
    holdFocus();
    const typed = text;
    // curationBody keeps an edited smiles and molfile; the note goes with the decision. A
    // failed save rolls the row back.
    save(id, { status, note: noteOf(text) }).then(
      () => dropDraft(id, typed),
      (err: unknown) => toast(`Not saved: ${errorText(err)}`, "error"),
    );
    clearTimer();
    if (reduce) advance(id);
    else timer.current = setTimeout(() => advance(id), ADVANCE_MS);
  };

  /** Drops this segment's draft once it is saved, unless it was typed on meanwhile. */
  const dropDraft = (segmentId: string, saved: string) =>
    setDraft((d) => (d !== null && d.id === segmentId && d.text === saved ? null : d));

  const saveNote = () => {
    const next = noteOf(text);
    if (next === stored) return;
    const typed = text;
    save(id, { note: next }).then(
      () => dropDraft(id, typed),
      (err: unknown) => toast(`Note not saved: ${errorText(err)}`, "error"),
    );
  };

  const noteKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== "Escape") return;
    // Esc leaves the note (saving it on blur); the next Esc goes back to the grid.
    e.preventDefault();
    root.current?.focus({ preventScroll: true });
  };

  // Opening the editor or Compare cancels the move after A or R: they work on this structure
  // (the workspace pins the dialog to it; the review keys hold while it is open).
  const openEditor = () => {
    clearTimer();
    ws.openEditor(id);
  };
  const openCompare = () => {
    clearTimer();
    ws.openCompare(id);
  };

  // The keys act only while focus is inside this region. While Keys, Compare or the editor
  // is open, the keys are theirs (ui/keysHeld, one DOM check in useReviewKeys): these run
  // only with none of them open. Each closes itself.
  useReviewKeys(root, {
    accept: () => decide("accepted"),
    reject: () => decide("rejected"),
    edit: openEditor,
    compare: openCompare,
    prev: () => step(-1),
    next: () => step(1),
    close: () => onClose(id),
    help: () => setHelp(true),
  });

  const left = rows.filter((r) => r.state === "to-check").length;

  const depictionUrl = drawable ? api.depictionUrl(id, depictionKey(segment)) : null;
  const depiction = useDepiction(depictionUrl);
  const shown = shownStructure(segment, paper.engine);
  const { smiles, edited } = shown;
  const meta = metaText(shown);
  const curation = segment.curation;
  const rejected = state === "rejected";

  return (
    <section
      ref={root}
      className="fm"
      aria-label={`Focus ${tag}`}
      tabIndex={-1}
      // A dialog whose opener is gone gives focus back here (ui/modal), so the keys stay live.
      data-focus-home=""
    >
      <div className="fm-bar">
        <GlassButton tint="clear" size="sm" onClick={() => onClose(id)}>
          Grid <Kbd>Esc</Kbd>
        </GlassButton>
        <p className="fm-bar__where">
          <span className="fm-bar__tag">{`${tag} · Page ${segment.page + 1}`}</span>
          <span className="fm-bar__of">{`${index + 1} of ${rows.length}`}</span>
        </p>
        <StateBadge state={state} />
        <p className="fm-bar__left" role="status">
          {left === 0 ? "None left to check" : `${left} to check`}
        </p>
        {/* The region's name changes with each step, but focus stays on it: say where. */}
        <p className="visually-hidden" role="status">
          {`${tag} · Page ${segment.page + 1} · ${STATE_WORD[state]}`}
        </p>
        <div className="fm-bar__nav">
          <button
            type="button"
            className="fm-step"
            aria-label="Previous structure"
            disabled={index <= 0}
            onClick={() => step(-1)}
          >
            <span aria-hidden="true">←</span>
          </button>
          <button
            type="button"
            className="fm-step"
            aria-label="Next structure"
            disabled={index >= rows.length - 1}
            onClick={() => step(1)}
          >
            <span aria-hidden="true">→</span>
          </button>
          <button
            type="button"
            className="fm-keys"
            aria-haspopup="dialog"
            onClick={() => setHelp(true)}
          >
            Keys <Kbd>?</Kbd>
          </button>
        </div>
      </div>

      <div className="fm-body">
        <div className="fm-main">
          <div className="fm-figures">
            <div className="fm-drawing">
              <Structure
                src={depiction.src}
                failed={!drawable || depiction.failed}
                onRetry={drawable ? (depiction.retry ?? undefined) : undefined}
                alt={`Structure ${tag}`}
                crossed={rejected}
              />
              {(state === "accepted" || state === "rejected") && (
                <span className="fm-stamp">
                  <Stamp key={state} state={state} size="lg" animate={landed} />
                </span>
              )}
            </div>
            <figure className="fm-crop">
              <Structure src={api.segmentImageUrl(id)} alt={`Crop ${tag}`} crossed={rejected} />
              <figcaption className="fm-crop__cap">Crop</figcaption>
            </figure>
          </div>

          <div className="fm-facts">
            {smiles !== null && <Smiles value={smiles} struck={rejected} />}
            {meta !== null && <p className="fm-meta">{meta}</p>}
            {state === "failed" && row?.reason && <p className="fm-reason">{sentence(row.reason)}</p>}
          </div>

          {/* The decision row right under the structure, above the fold. */}
          <div className="fm-actions glassbed">
            <GlassButton
              tint="green"
              disabled={!drawable}
              onClick={() => decide("accepted")}
            >
              Accept <Kbd>A</Kbd>
            </GlassButton>
            <GlassButton tint="clear" onClick={() => decide("rejected")}>
              Reject <Kbd>R</Kbd>
            </GlassButton>
            <GlassButton tint="clear" hasPopup="dialog" onClick={openEditor}>
              Edit <Kbd>E</Kbd>
            </GlassButton>
            <GlassButton tint="clear" hasPopup="dialog" onClick={openCompare}>
              Compare <Kbd>C</Kbd>
            </GlassButton>
          </div>

          {segment.predictions.length > 0 && (
            <SpecimenLabel title="Engines" rows={engineRows(segment.predictions)} />
          )}

          <label className="fm-note">
            <span className="fm-note__label">Note</span>
            <textarea
              className="fm-note__field"
              rows={2}
              value={text}
              onChange={(e) => setDraft({ id, text: e.target.value })}
              onBlur={saveNote}
              onKeyDown={noteKey}
            />
          </label>

          {/* Molfile, image, PubChem (the SMILES has its own Copy). Edit and Compare are in
              the row above, with their keys. */}
          <div>
            <StructureActions
              name={paper.display_name}
              n={row?.n ?? index + 1}
              smiles={smiles}
              curatedMolfile={curation?.molfile ?? null}
              predictionMolfile={edited ? null : shown.molfile}
              depictionUrl={depictionUrl}
            />
          </div>
        </div>

        <FocusPage
          paperId={paper.id}
          pages={paper.pages}
          segment={segment}
          segments={ws.segments}
          rows={rows}
          tag={tag}
          onPick={(to) => {
            holdFocus();
            go(to);
          }}
        />
      </div>

      {help && <KeyHelp onClose={() => setHelp(false)} />}
    </section>
  );
}

/** The newest prediction of each engine (predictions come newest first). */
function engineRows(predictions: PredictionOut[]): [string, ReactNode][] {
  const seen = new Set<string>();
  const out: [string, ReactNode][] = [];
  for (const p of predictions) {
    if (seen.has(p.engine)) continue;
    seen.add(p.engine);
    out.push([
      engineName(p.engine),
      <span className="fm-pred" key={p.id}>
        <code className="fm-pred__smiles">{p.smiles}</code>
        <span className={p.valid ? "fm-pred__meta" : "fm-pred__meta fm-pred__meta--bad"}>
          {`${p.valid ? "Valid" : "Invalid"} · ${p.engine_version}`}
        </span>
      </span>,
    ]);
  }
  return out;
}

/**
 * The page image, scaled to its column, with the structure's box drawn as its marker and
 * `[nn]` tag (placed as in the Paper view: pageBox). The page's other structures carry
 * quiet markers; clicking one opens it.
 */
function FocusPage({
  paperId,
  pages,
  segment,
  segments,
  rows,
  tag,
  onPick,
}: {
  paperId: string;
  pages: number | null;
  segment: SegmentOut;
  segments: SegmentOut[];
  rows: ReviewRow[];
  tag: string;
  onPick: (segmentId: string) => void;
}) {
  const src = api.pageImageUrl(paperId, segment.page);
  const [size, setSize] = useState<{ src: string; w: number; h: number } | null>(null);
  const natural = size !== null && size.src === src ? size : null;
  const [x0, y0, x1, y1] = segment.bbox;

  const onPage = useMemo(() => {
    const byId = new Map(rows.map((r) => [r.segmentId, r]));
    return segments
      .filter((s) => s.page === segment.page)
      .map((s) => ({ segment: s, row: byId.get(s.id) }));
  }, [segments, rows, segment.page]);

  const box = (s: SegmentOut) => boxStyle(s.bbox, natural!.w, natural!.h);

  const label = `Page ${segment.page + 1}`;
  return (
    <div className="fm-page">
      <p className="fm-page__cap">
        <span aria-hidden="true">+</span>
        <span>{pages ? `${label} of ${pages} · 300 DPI` : `${label} · 300 DPI`}</span>
        <span aria-hidden="true">+</span>
      </p>
      <div className="fm-page__sheet">
        <img
          className="fm-page__img"
          src={src}
          alt={label}
          decoding="async"
          onLoad={(e) =>
            setSize({ src, w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })
          }
        />
        {natural &&
          onPage.map(({ segment: s, row }) => {
            const current = s.id === segment.id;
            const state = row?.state ?? "to-check";
            const t = structureTag(row?.n ?? 0);
            const cls = `fm-marker fm-marker--${state}${current ? " fm-marker--current" : ""}`;
            return current ? (
              <span key={s.id} className={cls} style={box(s)} data-testid={`marker-${s.id}`}>
                <span className="fm-marker__tag">{t}</span>
              </span>
            ) : (
              <button
                key={s.id}
                type="button"
                className={cls}
                style={box(s)}
                data-testid={`marker-${s.id}`}
                aria-label={`Open ${t}`}
                onClick={() => onPick(s.id)}
              >
                <span className="fm-marker__tag" aria-hidden="true">
                  {t}
                </span>
              </button>
            );
          })}
      </div>
      <p className="fm-bbox">{`BBOX ${tag}  X0 ${x0} · Y0 ${y0} · X1 ${x1} · Y1 ${y1} PX`}</p>
    </div>
  );
}
