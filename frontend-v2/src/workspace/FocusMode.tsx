import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { api, ApiError } from "../api/client";
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
import { useToast } from "../ui/Toasts";
import { hasDrawing, shownPrediction, type CardState } from "./cardState";
import KeyHelp from "./KeyHelp";
import { useReviewKeys } from "./useReviewKeys";
import type { ReviewRow } from "./useReviewRows";
import type { Workspace } from "./useWorkspace";
import "./focus.css";

/** After A or R the stamp lands (160 ms), then focus mode moves on (none under reduced motion). */
export const ADVANCE_MS = 250;

type Decision = "accepted" | "rejected";
type Landed = { id: string; status: Decision; seq: number };

const detail = (err: unknown) => (err instanceof ApiError ? err.detail : "Something went wrong.");

/** A blank note is no note. */
const noteOf = (text: string): string | null => (text.trim() === "" ? null : text);

export type FocusModeProps = {
  ws: Workspace;
  rows: ReviewRow[];
  segment: SegmentOut;
  /** Back to the grid; the grid then focuses this segment's card. */
  onClose: (segmentId: string) => void;
  /** E and the Edit button. F11 fills it (the Ketcher editor); until then E does nothing. */
  onEdit?: ((segmentId: string) => void) | undefined;
  /** C and the Compare button. F10 fills it (compare engines); until then C does nothing. */
  onCompare?: ((segmentId: string) => void) | undefined;
};

/**
 * Focus mode: one structure large, its crop, its page with the box, SMILES, the engines'
 * predictions, a note and the decision, all from the keyboard (useReviewKeys). A or R
 * lands the stamp, then moves on to the next structure still to check.
 */
export default function FocusMode({ ws, rows, segment, onClose, onEdit, onCompare }: FocusModeProps) {
  const paper = ws.paper!;
  const { setSelection } = ws;
  const { save } = useSaveCuration(paper.id);
  const toast = useToast();
  const reduce = usePrefersReducedMotion();
  const root = useRef<HTMLElement>(null);
  const [help, setHelp] = useState(false);
  const [landed, setLanded] = useState<Landed | null>(null);
  const [draft, setDraft] = useState<{ id: string; text: string } | null>(null);
  const seq = useRef(0);
  const pending = useRef(new Set<string>()); // decided, save not answered yet
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rowsRef = useRef(rows);
  rowsRef.current = rows;

  const id = segment.id;
  const index = rows.findIndex((r) => r.segmentId === id);
  const row = rows[index];
  const tag = structureTag(row?.n ?? index + 1);
  const mine = landed !== null && landed.id === id ? landed : null;
  const state: CardState = mine?.status ?? row?.state ?? "to-check";
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

  const step = (by: -1 | 1) => {
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
      if (r.segmentId === from || pending.current.has(r.segmentId)) continue;
      if (r.state === "to-check") {
        go(r.segmentId);
        return;
      }
    }
  };

  const decide = (status: Decision) => {
    if (status === "accepted" && !drawable) return; // nothing to accept (ruling on F7 M2)
    const n = ++seq.current;
    setLanded({ id, status, seq: n });
    pending.current.add(id);
    // curationBody keeps an edited smiles and molfile; the note goes with the decision.
    save(id, { status, note: noteOf(text) }).then(
      () => pending.current.delete(id),
      (err: unknown) => {
        pending.current.delete(id);
        setLanded((l) => (l !== null && l.seq === n ? null : l));
        toast(`Not saved: ${detail(err)}`, "error");
      },
    );
    clearTimer();
    if (reduce) advance(id);
    else timer.current = setTimeout(() => advance(id), ADVANCE_MS);
  };

  const saveNote = () => {
    const next = noteOf(text);
    if (next === stored) return;
    save(id, { note: next }).catch((err: unknown) => toast(`Note not saved: ${detail(err)}`, "error"));
  };

  const noteKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== "Escape") return;
    // Esc leaves the note (saving it on blur); the next Esc goes back to the grid.
    e.preventDefault();
    root.current?.focus({ preventScroll: true });
  };

  useReviewKeys({
    accept: () => !help && decide("accepted"),
    reject: () => !help && decide("rejected"),
    edit: () => !help && onEdit?.(id),
    compare: () => !help && onCompare?.(id),
    prev: () => !help && step(-1),
    next: () => !help && step(1),
    close: () => (help ? setHelp(false) : onClose(id)),
    help: () => setHelp((h) => !h),
  });

  const left = rows.filter(
    (r) => (r.segmentId === id ? state : r.state) === "to-check",
  ).length;

  const depiction = useDepiction(drawable ? api.depictionUrl(id, depictionKey(segment)) : null);
  const prediction = shownPrediction(segment, paper.engine);
  const curation = segment.curation;
  const smiles = curation?.smiles ?? (curation?.molfile ? null : (prediction?.smiles ?? null));
  const edited = Boolean(curation?.smiles || curation?.molfile);
  const rejected = state === "rejected";

  return (
    <section ref={root} className="fm" aria-label={`Focus ${tag}`} tabIndex={-1}>
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
                alt={`Structure ${tag}`}
                crossed={rejected}
              />
              {(state === "accepted" || state === "rejected") && (
                <span className="fm-stamp">
                  <Stamp
                    key={mine ? `landed-${mine.seq}` : "shown"}
                    state={state}
                    size="lg"
                    animate={mine !== null}
                  />
                </span>
              )}
            </div>
            <figure className="fm-crop">
              <Structure src={api.segmentImageUrl(id)} alt={`Crop ${tag}`} crossed={rejected} />
              <figcaption className="fm-crop__cap">Crop</figcaption>
            </figure>
          </div>

          <div className="fm-facts">
            {smiles !== null && smiles !== "" && <Smiles value={smiles} struck={rejected} />}
            {(edited || prediction) && (
              <p className="fm-meta">
                {edited
                  ? "Edited"
                  : `${engineName(prediction!.engine)} · ${prediction!.valid ? "Valid" : "Invalid"}`}
              </p>
            )}
            {state === "failed" && row?.reason && <p className="fm-reason">{sentence(row.reason)}</p>}
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
            {/* F11 hooks the editor in through onEdit, F10 the comparison through onCompare. */}
            {onEdit && (
              <GlassButton tint="clear" onClick={() => onEdit(id)}>
                Edit <Kbd>E</Kbd>
              </GlassButton>
            )}
            {onCompare && (
              <GlassButton tint="clear" onClick={() => onCompare(id)}>
                Compare <Kbd>C</Kbd>
              </GlassButton>
            )}
          </div>
        </div>

        <PageWithBoxes
          paperId={paper.id}
          pages={paper.pages}
          segment={segment}
          segments={ws.segments}
          rows={rows}
          currentState={state}
          tag={tag}
          onPick={go}
        />
      </div>

      {help && <KeyHelp onClose={() => setHelp(false)} />}
    </section>
  );
}

function sentence(text: string): string {
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}.`;
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

const pct = (v: number, total: number) => `${+((v * 100) / total).toFixed(3)}%`;
const clamp = (v: number, max: number) => Math.min(Math.max(v, 0), max);

/**
 * The page image, scaled to its column, with the structure's box drawn as its marker and
 * `[nn]` tag. `bbox` is [x0, y0, x1, y1] in pixels of the 300 DPI page PNG, which is the
 * image served, so the box is placed in percent of the image's natural size. The page's
 * other structures carry quiet markers; clicking one opens it.
 */
function PageWithBoxes({
  paperId,
  pages,
  segment,
  segments,
  rows,
  currentState,
  tag,
  onPick,
}: {
  paperId: string;
  pages: number | null;
  segment: SegmentOut;
  segments: SegmentOut[];
  rows: ReviewRow[];
  currentState: CardState;
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

  const box = (s: SegmentOut): CSSProperties | undefined => {
    if (!natural) return undefined;
    const [a, b, c, d] = s.bbox;
    const left = clamp(Math.min(a, c), natural.w);
    const top = clamp(Math.min(b, d), natural.h);
    const right = clamp(Math.max(a, c), natural.w);
    const bottom = clamp(Math.max(b, d), natural.h);
    return {
      "--l": pct(left, natural.w),
      "--t": pct(top, natural.h),
      "--w": pct(right - left, natural.w),
      "--h": pct(bottom - top, natural.h),
    } as CSSProperties;
  };

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
            const state = current ? currentState : (row?.state ?? "to-check");
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
