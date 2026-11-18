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
import Smiles from "../ui/Smiles";
import Stamp from "../ui/Stamp";
import StateBadge from "../ui/StateBadge";
import Structure from "../ui/Structure";
import { structureTag } from "../ui/tag";
import {
  enginesDiffer,
  hasDrawing,
  shownPrediction,
  STATE_WORD,
  type CardState,
} from "./cardState";
import StructureActions, { type StructureActionsProps } from "./StructureActions";
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
  /** Opens Compare engines for the segment (To check cards, the engine menu, the card menu). */
  onCompare?: ((segmentId: string) => void) | undefined;
  /** Opens the structure editor for the segment (the card menu's Edit). */
  onEdit?: ((segmentId: string) => void) | undefined;
  /** The paper's file name, for the card menu's downloads (`<name>-<n>.mol`, `.svg`). */
  paperName?: string;

  /**
   * The Paper view's list: the drawing beside the text, no checkbox (no bulk actions
   * there), and a click on the card calls `onOpen` (the Paper view selects with it).
   */
  compact?: boolean;
  /** Its page marker is hovered: the card is outlined (spec §7 signature interaction). */
  linked?: boolean;
  /** The pointer or keyboard focus entered (the segment id) or left (null) the card. */
  onHover?: ((segmentId: string | null) => void) | undefined;
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
  onCompare,
  onEdit,
  paperName = "structure",
  compact = false,
  linked = false,
  onHover,
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
  // The compact card (Paper view) opens on a single click; its controls keep their own.
  const click = (e: MouseEvent<HTMLElement>) => {
    if ((e.target as Element).closest("button, input, a, label")) return;
    onOpen(segment.id);
  };
  const enter = onHover && (() => onHover(segment.id));
  const leave = onHover && (() => onHover(null));

  const classes = ["card", `card--${state}`];
  if (selected) classes.push("card--selected");
  if (compact) classes.push("card--compact");
  const stamp = (state === "accepted" || state === "rejected") && (
    <span className="card__stamp">
      <Stamp state={state} animate={landed} />
    </span>
  );
  if (linked) classes.push("card--linked");

  return (
    <article
      ref={ref}
      className={classes.join(" ")}
      tabIndex={0}
      aria-label={`${where}, ${STATE_WORD[state]}`}
      aria-current={current ? "true" : undefined}
      data-segment-id={segment.id}
      onKeyDown={ownKey}
      onDoubleClick={compact ? undefined : doubleClick}
      onClick={compact ? click : undefined}
      onMouseEnter={enter}
      onMouseLeave={leave}
      onFocus={enter}
      onBlur={leave}
    >
      <div className="card__tagrow">
        {compact ? (
          <span className="card__tag">{where}</span>
        ) : (
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
        )}
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
        {!compact && stamp}
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
        {/* Compact (Paper view): the stamp sits in the text column, clear of the drawing. */}
        {compact && stamp}
      </div>

      <div className="card__actions">
        <CardActions
          segmentId={segment.id}
          tag={tag}
          state={state}
          paperEngine={paperEngine}
          canAccept={canAccept}
          failedEngine={failedEngine}
          onDecide={onDecide}
          onRun={onRun}
          onCompare={onCompare}
        />
        <CardMenu
          tag={tag}
          name={paperName}
          n={n}
          smiles={smiles}
          curatedMolfile={curation?.molfile ?? null}
          // Only for the prediction shown: an edited structure never takes its molfile.
          predictionMolfile={edited ? null : (prediction?.molfile ?? null)}
          depictionUrl={drawable ? api.depictionUrl(segment.id, depictionKey(segment)) : null}
          copySmiles={false}
          onEdit={onEdit && (() => onEdit(segment.id))}
          onCompare={onCompare && (() => onCompare(segment.id))}
        />
      </div>
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
  onCompare,
}: {
  segmentId: string;
  tag: string;
  state: CardState;
  paperEngine: string;
  canAccept: boolean;
  failedEngine: string | null;
  onDecide: StructureCardProps["onDecide"];
  onRun: StructureCardProps["onRun"];
  onCompare: StructureCardProps["onCompare"];
}) {
  const own = asEngine(paperEngine) ?? "decimer";
  const compare = onCompare && (() => onCompare(segmentId));
  if (state === "to-check") {
    // No key hints: A and R act in focus mode only. The name starts with the visible word
    // (WCAG 2.5.3 label in name).
    return (
      <>
        <GlassButton
          tint="green"
          size="sm"
          label={`Accept ${tag}`}
          disabled={!canAccept}
          onClick={() => onDecide(segmentId, "accepted")}
        >
          Accept
        </GlassButton>
        <GlassButton
          tint="clear"
          size="sm"
          label={`Reject ${tag}`}
          onClick={() => onDecide(segmentId, "rejected")}
        >
          Reject
        </GlassButton>
        {compare && (
          <GlassButton
            tint="clear"
            size="sm"
            label={`Compare ${tag}`}
            hasPopup="dialog"
            onClick={compare}
          >
            Compare
          </GlassButton>
        )}
      </>
    );
  }
  if (state === "failed") {
    const failed = asEngine(failedEngine) ?? own;
    return (
      <EngineMenu
        label="Try another engine"
        engines={others(failed)}
        onPick={(engine) => onRun(segmentId, engine)}
        onCompare={compare}
      />
    );
  }
  if (state === "not-read") {
    return (
      <>
        <GlassButton tint="clear" size="sm" onClick={() => onRun(segmentId, own)}>
          {`Read with ${engineName(own)}`}
        </GlassButton>
        <EngineMenu
          label="Other engine"
          engines={others(own)}
          onPick={(engine) => onRun(segmentId, engine)}
          onCompare={compare}
        />
      </>
    );
  }
  return null;
}

const others = (engine: Engine) => ENGINES.filter((e) => e.value !== engine);

/**
 * A disclosure on a card: open and close, Escape (kept from the review keys) and a click or
 * focus outside close it. `close(true)` also puts focus back on its button, where a dialog
 * opened from the panel returns it.
 */
function useDisclosure() {
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

  const close = (refocus: boolean) => {
    setOpen(false);
    if (refocus) button.current?.focus();
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key !== "Escape" || !open) return;
    e.stopPropagation(); // the review keys (F8) must not also see this Escape
    close(true);
  };

  return { open, setOpen, root, button, panelId, close, onKeyDown };
}

/**
 * A disclosure of engines to read the segment with, and Compare engines last (when given).
 * Escape or a click outside closes it.
 */
function EngineMenu({
  label,
  engines,
  onPick,
  onCompare,
}: {
  label: string;
  engines: { value: Engine; label: string }[];
  onPick: (engine: Engine) => void;
  onCompare?: (() => void) | undefined;
}) {
  const { open, setOpen, root, button, panelId, close, onKeyDown } = useDisclosure();
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
          {onCompare && (
            <button
              type="button"
              className="engine-menu__item engine-menu__item--compare"
              aria-haspopup="dialog"
              onClick={() => {
                close(true); // where focus returns when Compare closes
                onCompare();
              }}
            >
              Compare
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * The card menu ("More", on every card): the structure's actions (copy, download, PubChem)
 * with Edit and Compare. Edit and Compare close the menu first, so the dialog they open
 * returns focus to "More".
 */
function CardMenu({
  tag,
  ...actions
}: { tag: string } & StructureActionsProps) {
  const { open, setOpen, root, button, panelId, close, onKeyDown } = useDisclosure();
  const then = (fn: (() => void) | undefined) =>
    fn &&
    (() => {
      close(true);
      fn();
    });
  return (
    <div className="card-menu" ref={root} onKeyDown={onKeyDown}>
      <GlassButton
        ref={button}
        tint="clear"
        size="sm"
        label={`More for ${tag}`}
        expanded={open}
        controls={open ? panelId : undefined}
        onClick={() => setOpen((o) => !o)}
      >
        More
      </GlassButton>
      {open && (
        <div id={panelId} className="card-menu__panel" role="group" aria-label={`${tag} actions`}>
          <StructureActions
            {...actions}
            onEdit={then(actions.onEdit)}
            onCompare={then(actions.onCompare)}
          />
        </div>
      )}
    </div>
  );
}
