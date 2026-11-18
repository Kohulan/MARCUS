import {
  memo,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
  type RefObject,
} from "react";
import { api } from "../api/client";
import { depictionKey } from "../api/depictionKey";
import { useDepiction } from "../api/depictions";
import { asEngine, ENGINES, engineName } from "../api/engines";
import type { CurationStatus, Engine, SegmentOut } from "../api/types";
import { GlassButton } from "../ui/GlassButton";
import Kbd from "../ui/Kbd";
import Smiles from "../ui/Smiles";
import Stamp from "../ui/Stamp";
import StateBadge from "../ui/StateBadge";
import Structure from "../ui/Structure";
import { structureTag } from "../ui/tag";
import { enginesDiffer, hasDrawing, shownPrediction, type CardState } from "./cardState";
import "./grid.css";

// Depictions load only for cards near the viewport: one IntersectionObserver for the whole
// grid (200 cards), a margin of about two screens, and a card once seen keeps its drawing.
// Without IntersectionObserver (jsdom, old engines) every card counts as near.
const seen = new WeakMap<Element, () => void>();
let observer: IntersectionObserver | null = null;

function nearObserver(): IntersectionObserver | null {
  if (typeof IntersectionObserver === "undefined") return null;
  observer ??= new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        seen.get(entry.target)?.();
        observer?.unobserve(entry.target);
        seen.delete(entry.target);
      }
    },
    { rootMargin: "1200px 0px" },
  );
  return observer;
}

function useNearViewport(ref: RefObject<Element | null>): boolean {
  const [near, setNear] = useState(() => nearObserver() === null);
  useEffect(() => {
    const el = ref.current;
    const io = nearObserver();
    if (near || !el || !io) return;
    seen.set(el, () => setNear(true));
    io.observe(el);
    return () => {
      io.unobserve(el);
      seen.delete(el);
    };
  }, [near, ref]);
  return near;
}

const WORD: Record<CardState, string> = {
  accepted: "Accepted",
  rejected: "Rejected",
  "to-check": "To check",
  reading: "Reading…",
  failed: "Failed",
  "not-read": "Not read yet",
};

export type StructureCardProps = {
  segment: SegmentOut;
  /** 1-based position in (page, idx) order: the `[nn]` tag. */
  n: number;
  /** Position in the shown list (for Shift-click ranges). */
  index: number;
  state: CardState;
  /** The paper's engine (wire value). */
  paperEngine: string;
  /** There is a structure to accept (a curated one or a valid prediction). */
  canAccept: boolean;
  /** For a failed card: the reason (reasonText) and the engine that failed. */
  reason: string | null;
  failedEngine: string | null;
  selected: boolean;
  /** The focused segment (`?s=`). */
  current: boolean;
  onToggle: (index: number, range: boolean) => void;
  onOpen: (segmentId: string) => void;
  onDecide: (segmentId: string, status: CurationStatus) => void;
  onRun: (segmentId: string, engine: Engine) => void;
};

/**
 * One structure on the review grid (board: "In the tool: review"): the tag row, the drawing
 * (or its crop), SMILES, engine and validity, the note's first line, and the actions of its
 * state. Memoised: a 200-card grid re-renders only the cards whose props changed.
 */
function StructureCard({
  segment,
  n,
  index,
  state,
  paperEngine,
  canAccept,
  reason,
  failedEngine,
  selected,
  current,
  onToggle,
  onOpen,
  onDecide,
  onRun,
}: StructureCardProps) {
  const ref = useRef<HTMLElement>(null);
  const near = useNearViewport(ref);
  const drawable = hasDrawing(segment);
  const [crop, setCrop] = useState(false);
  const showCrop = crop || !drawable;
  const depiction = useDepiction(
    near && !showCrop ? api.depictionUrl(segment.id, depictionKey(segment)) : null,
  );
  // A decision made while the card is on screen lands its stamp (signature interaction).
  const firstState = useRef(state);
  const landed = state !== firstState.current;

  const tag = structureTag(n);
  const where = `${tag} · Page ${segment.page + 1}`;
  const curation = segment.curation;
  const prediction = shownPrediction(segment, paperEngine);
  const smiles = curation?.smiles ?? (curation?.molfile ? null : (prediction?.smiles ?? null));
  const edited = Boolean(curation?.smiles || curation?.molfile);
  const note = curation?.note?.split(/\r?\n/, 1)[0]?.trim() ?? "";
  const rejected = state === "rejected";

  const ownKey = (e: KeyboardEvent<HTMLElement>) => {
    if (e.key === "Enter" && e.target === e.currentTarget) {
      e.preventDefault();
      onOpen(segment.id);
    }
  };
  const doubleClick = (e: MouseEvent<HTMLElement>) => {
    if ((e.target as Element).closest("button, input, a")) return;
    onOpen(segment.id);
  };

  const classes = ["card", `card--${state}`];
  if (selected) classes.push("card--selected");

  return (
    <article
      ref={ref}
      className={classes.join(" ")}
      tabIndex={0}
      aria-label={`${where}, ${WORD[state]}`}
      aria-current={current ? "true" : undefined}
      data-segment-id={segment.id}
      onKeyDown={ownKey}
      onDoubleClick={doubleClick}
    >
      <div className="card__tagrow">
        <label className="card__pick">
          <input
            type="checkbox"
            className="card__check"
            checked={selected}
            aria-label={`Select ${tag}`}
            onChange={(e) => onToggle(index, (e.nativeEvent as globalThis.MouseEvent).shiftKey)}
          />
          <span className="card__tag">{where}</span>
        </label>
        <StateBadge state={state} />
      </div>

      <div className="card__figure">
        {showCrop ? (
          <Structure
            src={api.segmentImageUrl(segment.id)}
            alt={`Crop ${tag}`}
            crossed={rejected}
          />
        ) : (
          <Structure
            src={depiction.src}
            failed={depiction.failed}
            alt={`Structure ${tag}`}
            crossed={rejected}
          />
        )}
        {drawable && (
          <button
            type="button"
            className="card__crop"
            aria-pressed={crop}
            aria-label={`Crop ${tag}`}
            onClick={() => setCrop((c) => !c)}
          >
            Crop
          </button>
        )}
        {(state === "accepted" || state === "rejected") && (
          <span className="card__stamp">
            <Stamp state={state} animate={landed} />
          </span>
        )}
      </div>

      <div className="card__body">
        {smiles !== null && smiles !== "" && <Smiles value={smiles} struck={rejected} />}
        {(edited || prediction) && (
          <p className="card__meta">
            <span>
              {edited
                ? "Edited"
                : `${engineName(prediction!.engine)} · ${prediction!.valid ? "Valid" : "Invalid"}`}
            </span>
            {enginesDiffer(segment) && <span className="card__differ">Engines differ</span>}
          </p>
        )}
        {note !== "" && <p className="card__note">{`Note: ${note}`}</p>}
        {reason !== null && <p className="card__reason">{sentence(reason)}</p>}
      </div>

      <CardActions
        segmentId={segment.id}
        tag={tag}
        state={state}
        paperEngine={paperEngine}
        canAccept={canAccept}
        failedEngine={failedEngine}
        onDecide={onDecide}
        onRun={onRun}
      />
    </article>
  );
}

export default memo(StructureCard);

function sentence(text: string): string {
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}.`;
}

function CardActions({
  segmentId,
  tag,
  state,
  paperEngine,
  canAccept,
  failedEngine,
  onDecide,
  onRun,
}: {
  segmentId: string;
  tag: string;
  state: CardState;
  paperEngine: string;
  canAccept: boolean;
  failedEngine: string | null;
  onDecide: StructureCardProps["onDecide"];
  onRun: StructureCardProps["onRun"];
}) {
  const own = asEngine(paperEngine) ?? "decimer";
  if (state === "to-check") {
    return (
      <div className="card__actions">
        <GlassButton
          tint="green"
          size="sm"
          label={`Accept ${tag}`}
          disabled={!canAccept}
          onClick={() => onDecide(segmentId, "accepted")}
        >
          Accept <Kbd>A</Kbd>
        </GlassButton>
        <GlassButton
          tint="clear"
          size="sm"
          label={`Reject ${tag}`}
          onClick={() => onDecide(segmentId, "rejected")}
        >
          Reject <Kbd>R</Kbd>
        </GlassButton>
      </div>
    );
  }
  if (state === "failed") {
    const failed = asEngine(failedEngine) ?? own;
    return (
      <div className="card__actions">
        <EngineMenu
          label="Try another engine"
          engines={others(failed)}
          onPick={(engine) => onRun(segmentId, engine)}
        />
      </div>
    );
  }
  if (state === "not-read") {
    return (
      <div className="card__actions">
        <GlassButton tint="clear" size="sm" onClick={() => onRun(segmentId, own)}>
          {`Read with ${engineName(own)}`}
        </GlassButton>
        <EngineMenu
          label="Other engine"
          engines={others(own)}
          onPick={(engine) => onRun(segmentId, engine)}
        />
      </div>
    );
  }
  return null;
}

const others = (engine: Engine) => ENGINES.filter((e) => e.value !== engine);

/** A disclosure of engines to read the segment with. Escape or a click outside closes it. */
function EngineMenu({
  label,
  engines,
  onPick,
}: {
  label: string;
  engines: { value: Engine; label: string }[];
  onPick: (engine: Engine) => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const outside = (e: Event) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("focusin", outside);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("focusin", outside);
    };
  }, [open]);

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key !== "Escape" || !open) return;
    e.stopPropagation(); // the review keys (F8) must not also see this Escape
    setOpen(false);
    button.current?.focus();
  };

  return (
    <div className="engine-menu" ref={root} onKeyDown={onKeyDown}>
      <GlassButton
        ref={button}
        tint="clear"
        size="sm"
        expanded={open}
        controls={open ? panelId : undefined}
        onClick={() => setOpen((o) => !o)}
      >
        {label}
      </GlassButton>
      {open && (
        <div id={panelId} className="engine-menu__panel" role="group" aria-label="Engines">
          {engines.map((e) => (
            <button
              key={e.value}
              type="button"
              className="engine-menu__item"
              onClick={() => {
                setOpen(false);
                onPick(e.value);
              }}
            >
              {e.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
