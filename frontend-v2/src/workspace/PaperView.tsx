import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type RefObject,
} from "react";
import { errorText } from "../api/client";
import { useMainFigure } from "../api/queries";
import { reasonText } from "../api/reasons";
import { isPaperBusy } from "../api/status";
import type { StepOut } from "../api/types";
import { usePrefersReducedMotion } from "../ui/motion";
import { useToast } from "../ui/Toasts";
import { scrollWithin } from "./scrollWithin";
import { pageSteps } from "./pageFailures";
import PageWithBoxes, { type PageImage, type PageMarker } from "./PageWithBoxes";
import StructureCard from "./StructureCard";
import TextColumn from "./TextColumn";
import { useCardActions } from "./useCardActions";
import type { ReviewRow } from "./useReviewRows";
import type { Workspace } from "./useWorkspace";
import "./paper.css";

const NO_MARKERS: PageMarker[] = [];

const sameMarker = (a: PageMarker, b: PageMarker) =>
  a.segmentId === b.segmentId &&
  a.target === b.target &&
  a.n === b.n &&
  a.state === b.state &&
  a.bbox.every((v, i) => v === b.bbox[i]) &&
  a.rgroups.join() === b.rgroups.join();

/**
 * Per page: can its image be shown? Yes once a render_page step of the page is done. Its
 * newest render_page step failed: the reason. A render still to come, or none yet on a
 * paper being worked on: waiting. No render_page step on a finished paper: try the image.
 */
function pageImages(steps: StepOut[], pages: number, busy: boolean): PageImage[] {
  const byPage = pageSteps(steps);
  return Array.from({ length: pages }, (_, page0): PageImage => {
    const renders = (byPage.get(page0) ?? []).filter((s) => s.kind === "render_page");
    const newest = renders[0];
    if (!newest) return busy ? { kind: "waiting" } : { kind: "ready" };
    if (renders.some((s) => s.status === "done")) return { kind: "ready" };
    if (newest.status === "failed") return { kind: "failed", reason: reasonText(newest.error_class) };
    return { kind: "waiting" };
  });
}

/** The child of `root` whose `data-<key>` is `value` (compared as data, never as a selector). */
function byData(root: HTMLElement | null, key: "marker" | "segmentId" | "page", value: string) {
  const attr = key === "segmentId" ? "data-segment-id" : `data-${key}`;
  return [...(root?.querySelectorAll<HTMLElement>(`[${attr}]`) ?? [])].find(
    (el) => el.dataset[key] === value,
  );
}

/**
 * Sets `--pv-top` on the view: its distance from the top of the page. The view is the
 * window's height less that, so at the top of the page all three columns end inside the
 * window, and the wheel at a column's end goes on to scroll the page (no trap). Measured
 * again when the window or anything above the view (header, status bar lines) changes size.
 */
function useViewTop(view: RefObject<HTMLDivElement | null>) {
  useLayoutEffect(() => {
    const el = view.current;
    if (!el) return;
    const measure = () => {
      const top = Math.max(0, Math.round(el.getBoundingClientRect().top + window.scrollY));
      el.style.setProperty("--pv-top", `${top}px`);
    };
    measure();
    window.addEventListener("resize", measure);
    let ro: ResizeObserver | undefined;
    const ws = el.closest(".ws");
    if (typeof ResizeObserver !== "undefined" && ws) {
      ro = new ResizeObserver(measure);
      for (const child of ws.children) if (!child.contains(el)) ro.observe(child);
    }
    return () => {
      window.removeEventListener("resize", measure);
      ro?.disconnect();
    };
  }, [view]);
}

/**
 * The Paper view (spec §5.4, board: Field Sheet "paper view" in the Survey Sheet look):
 * the pages with a marker per structure | the paper's text | the structure list. A marker
 * and its card are one thing: clicking a marker selects and scrolls to its card; selecting
 * or hovering a card brings its page into view and outlines its marker; hovering a marker
 * outlines its card.
 */
export default function PaperView({ ws, rows }: { ws: Workspace; rows: ReviewRow[] }) {
  const paper = ws.paper!;
  const { segments, steps, selection, setSelection } = ws;
  const { decide: onDecide, run: onRun } = useCardActions(paper.id, ws.live.reconnect);
  const reduce = usePrefersReducedMotion();
  const pagesHead = useId();
  const listHead = useId();
  const view = useRef<HTMLDivElement>(null);
  const pagesCol = useRef<HTMLElement>(null);
  const listCol = useRef<HTMLElement>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  const busy = isPaperBusy(paper.status);
  const byId = useMemo(() => new Map(segments.map((s) => [s.id, s])), [segments]);
  const pages = paper.pages ?? 0;
  const images = useMemo(() => pageImages(steps, pages, busy), [steps, pages, busy]);
  const shownMarkers = useRef(new Map<number, PageMarker[]>());
  const markers = useMemo(() => {
    const map = new Map<number, PageMarker[]>();
    const rowOf = new Map(rows.map((r) => [r.segmentId, r]));
    // Every segment has its marker; a repeat of a main-figure structure carries that one's tag
    // and selects it (it has no row of its own).
    for (const s of segments) {
      const target = s.repeat_of ?? s.id;
      const r = rowOf.get(target);
      if (!r) continue;
      const m: PageMarker = {
        segmentId: s.id,
        target,
        n: r.n,
        state: r.state,
        bbox: s.bbox,
        rgroups: r.rgroups,
      };
      const list = map.get(s.page);
      if (list) list.push(m);
      else map.set(s.page, [m]);
    }
    // A page whose markers did not change keeps its array, so a live refresh re-renders only
    // the pages that changed (PageWithBoxes is memoised).
    for (const [page, list] of map) {
      const old = shownMarkers.current.get(page);
      if (old && old.length === list.length && old.every((m, i) => sameMarker(m, list[i]!))) {
        map.set(page, old);
      }
    }
    shownMarkers.current = map;
    return map;
  }, [rows, segments]);

  // The main figure: one page, marked from its caption (pages with structures, and the marked
  // page, so its mark can always be cleared).
  const { mark } = useMainFigure(paper.id);
  const toast = useToast();
  const mainPage = paper.main_figure_page ?? null;

  // Callbacks handed to 200 memoised cards stay stable: they read the latest values here.
  const latest = useRef({ byId, reduce, setSelection, mark, toast, mainPage });
  latest.current = { byId, reduce, setSelection, mark, toast, mainPage };

  const onMark = useCallback((page0: number) => {
    const { mark: save, toast: say, mainPage: now } = latest.current;
    save(now === page0 ? null : page0).catch((err: unknown) =>
      say(`Not saved: ${errorText(err)}`, "error"),
    );
  }, []);

  /** Brings a structure's marker into view in the pages column (its page, before it loads). */
  const showMarker = useCallback((segmentId: string) => {
    const { byId: segs, reduce: still } = latest.current;
    const marker = byData(pagesCol.current, "marker", segmentId);
    if (marker) {
      scrollWithin(pagesCol.current, marker, "nearest", !still);
      return;
    }
    const s = segs.get(segmentId);
    if (s) scrollWithin(pagesCol.current, byData(pagesCol.current, "page", String(s.page)), "start", !still);
  }, []);

  const showCard = useCallback((segmentId: string, focus = false) => {
    const card = byData(listCol.current, "segmentId", segmentId);
    if (!card) return;
    if (focus) card.focus({ preventScroll: true });
    scrollWithin(listCol.current, card, "nearest", !latest.current.reduce);
  }, []);

  useViewTop(view);

  // A structure picked from its marker: the pages column stays where the click was (a repeat's
  // marker picks its main-figure structure, whose own marker is on another page).
  const pickedFromMarker = useRef<string | null>(null);

  // A selection (here, from the URL, or from the Review view) brings its card and page in.
  useEffect(() => {
    if (selection === null) return;
    showCard(selection);
    if (pickedFromMarker.current === selection) pickedFromMarker.current = null;
    else showMarker(selection);
  }, [selection, showCard, showMarker]);

  const onPick = useCallback(
    (segmentId: string) => {
      pickedFromMarker.current = segmentId;
      latest.current.setSelection(segmentId);
      showCard(segmentId, true);
    },
    [showCard],
  );
  const onSelect = useCallback((segmentId: string) => latest.current.setSelection(segmentId), []);
  const onCardHover = useCallback(
    (segmentId: string | null) => {
      setHovered(segmentId);
      if (segmentId === null) pickedFromMarker.current = null;
      else if (segmentId !== pickedFromMarker.current) showMarker(segmentId);
    },
    [showMarker],
  );

  const pageOf = (id: string | null) => (id === null ? undefined : byId.get(id)?.page);
  const selectedPage = pageOf(selection);
  const hoveredPage = pageOf(hovered);

  return (
    <div className="pv" ref={view}>
      <section className="pv-col pv-col--pages" aria-labelledby={pagesHead} ref={pagesCol}>
        <div className="pv-cap">
          <h2 id={pagesHead} className="pv-cap__title">
            Pages
          </h2>
          {pages > 0 && <span className="pv-cap__count">{pages}</span>}
        </div>
        {pages === 0 ? (
          <p className="pv-empty">{busy ? "Pages appear here as they are read." : "No pages."}</p>
        ) : (
          <div className="pv-pages">
            {images.map((image, page0) => (
              <PageWithBoxes
                key={page0}
                paperId={paper.id}
                page0={page0}
                pages={pages}
                imageKind={image.kind}
                imageReason={image.kind === "failed" ? image.reason : null}
                markers={markers.get(page0) ?? NO_MARKERS}
                selected={selectedPage === page0 ? selection : null}
                hovered={hoveredPage === page0 ? hovered : null}
                onPick={onPick}
                onHover={setHovered}
                isMain={mainPage === page0}
                onMark={markers.has(page0) || mainPage === page0 ? onMark : null}
              />
            ))}
          </div>
        )}
      </section>

      <TextColumn
        paperId={paper.id}
        displayName={paper.display_name}
        paperStatus={paper.status}
      />

      <section className="pv-col pv-col--list" aria-labelledby={listHead} ref={listCol}>
        <div className="pv-cap">
          <h2 id={listHead} className="pv-cap__title">
            Structures
          </h2>
          {rows.length > 0 && <span className="pv-cap__count">{rows.length}</span>}
        </div>
        {rows.length === 0 ? (
          <p className="pv-empty">
            {busy ? "Structures appear here as pages are read." : "No structures found."}
          </p>
        ) : (
          <div className="pv-list">
            {rows.map((r) => {
              const segment = byId.get(r.segmentId)!;
              return (
                <StructureCard
                  key={r.segmentId}
                  compact
                  segment={segment}
                  n={r.n}
                  state={r.state}
                  paperEngine={paper.engine}
                  reason={r.reason}
                  failedEngine={r.failedEngine}
                  readingNote={r.readingNote}
                  alsoOn={r.alsoOn}
                  current={selection === r.segmentId}
                  linked={hovered === r.segmentId}
                  onOpen={onSelect}
                  onDecide={onDecide}
                  onRun={onRun}
                  onCompare={ws.openCompare}
                  onEdit={ws.openEditor}
                  paperName={paper.display_name}
                  onHover={onCardHover}
                />
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
