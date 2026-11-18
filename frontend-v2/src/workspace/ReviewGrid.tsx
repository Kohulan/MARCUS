import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { asEngine, engineName } from "../api/engines";
import { BulkPartialError, useBulkCuration } from "../api/queries";
import type { CurationStatus, Engine } from "../api/types";
import { useToast } from "../ui/Toasts";
import BulkBar from "./BulkBar";
import { filterOf, hasDrawing, type GridFilter } from "./cardState";
import { CardCompare } from "./Compare";
import { CardEditor } from "./SegmentEditor";
import GridFilters from "./GridFilters";
import StructureCard from "./StructureCard";
import { errorDetail as detail, useCardActions } from "./useCardActions";
import type { ReviewRow } from "./useReviewRows";
import type { Workspace } from "./useWorkspace";
import "./grid.css";

/** At most this many prediction requests in flight from one bulk "Read N". */
const READ_AT_ONCE = 4;
const BUSY_PAPER = new Set(["checking", "processing"]);

/** Run `fn` over `items`, at most `limit` at a time; never rejects. */
async function runPool<T>(
  items: T[],
  limit: number,
  fn: (item: T) => Promise<unknown>,
): Promise<boolean[]> {
  const ok: boolean[] = new Array<boolean>(items.length).fill(false);
  let next = 0;
  const worker = async () => {
    while (next < items.length) {
      const i = next++;
      try {
        await fn(items[i]!);
        ok[i] = true;
      } catch {
        ok[i] = false;
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return ok;
}

/** Focus the filter strip's pressed button. */
const focusFilters = () =>
  document.querySelector<HTMLElement>('.rg-filters [aria-pressed="true"]')?.focus();

/**
 * The review view: filters with counts, the grid of structure cards in (page, idx) order,
 * and the bulk bar for the selected cards.
 */
export default function ReviewGrid({ ws, rows }: { ws: Workspace; rows: ReviewRow[] }) {
  const paper = ws.paper!;
  const { segments, openFocus, selection } = ws;
  // ws.live.reconnect is stable (the live object itself is new each render).
  const { decide, run: onRun, started } = useCardActions(paper.id, ws.live.reconnect);
  const { bulk } = useBulkCuration(paper.id);
  const toast = useToast();
  const [filter, setFilter] = useState<GridFilter>("all");
  const [picked, setPicked] = useState<ReadonlySet<string>>(() => new Set());
  const [busy, setBusy] = useState(false);
  const [comparing, setComparing] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  // The Shift-click anchor: a card, looked up in the list shown now (positions move).
  const anchor = useRef<string | null>(null);
  const grid = useRef<HTMLDivElement>(null);

  const byId = useMemo(() => new Map(segments.map((s) => [s.id, s])), [segments]);

  const counts = useMemo(() => {
    const c: Record<GridFilter, number> = {
      all: rows.length,
      "to-check": 0,
      accepted: 0,
      rejected: 0,
      failed: 0,
    };
    for (const r of rows) c[filterOf(r.state)] += 1;
    return c;
  }, [rows]);

  const shown = useMemo(
    () => (filter === "all" ? rows : rows.filter((r) => filterOf(r.state) === filter)),
    [rows, filter],
  );
  const shownRef = useRef(shown);
  shownRef.current = shown;

  // The selection is what is selected AND shown: a card that leaves the filter (a decision on
  // its card, a live update, a new engine run) leaves the selection with it, so a bulk
  // action never touches a card out of sight.
  const chosen = shown.filter((r) => picked.has(r.segmentId));
  useEffect(() => {
    const visible = new Set(shown.map((r) => r.segmentId));
    setPicked((prev) => {
      const next = new Set([...prev].filter((id) => visible.has(id)));
      return next.size === prev.size ? prev : next; // a card coming back is not re-selected
    });
  }, [shown]);
  // Accept only what has a structure to accept (a curated one or a valid prediction).
  const acceptable = chosen.filter((r) => {
    const segment = byId.get(r.segmentId);
    return segment !== undefined && hasDrawing(segment);
  });
  const notRead = chosen.filter((r) => r.state === "not-read");
  const readEngine: Engine = asEngine(paper.engine) ?? "decimer";

  const onFilter = (next: GridFilter) => {
    setFilter(next);
    anchor.current = null;
    // The selection keeps to what is shown: a bulk action never touches hidden cards.
    const keep = new Set(
      rows.filter((r) => next === "all" || filterOf(r.state) === next).map((r) => r.segmentId),
    );
    setPicked((prev) => new Set([...prev].filter((id) => keep.has(id))));
  };

  const onToggle = useCallback((index: number, range: boolean) => {
    const list = shownRef.current;
    const id = list[index]?.segmentId;
    if (id === undefined) return;
    const from = anchor.current === null ? -1 : list.findIndex((r) => r.segmentId === anchor.current);
    anchor.current = id;
    setPicked((prev) => {
      const on = !prev.has(id);
      const next = new Set(prev);
      const [a, b] =
        range && from >= 0
          ? [Math.min(from, index), Math.max(from, index)]
          : [index, index];
      for (let i = a; i <= b; i++) {
        const rowId = list[i]!.segmentId;
        if (on) next.add(rowId);
        else next.delete(rowId);
      }
      return next;
    });
  }, []);

  // Enter or double-click: focus mode on that structure (a new history entry; Back closes it).
  const onOpen = openFocus;

  /** Focus a card of the grid by id (null: the first card, else the filter strip). */
  const focusCard = useCallback((segmentId: string | null) => {
    const cards = [...(grid.current?.querySelectorAll<HTMLElement>("[data-segment-id]") ?? [])];
    const card =
      segmentId === null ? cards[0] : cards.find((el) => el.dataset.segmentId === segmentId);
    if (card) card.focus();
    else if (segmentId === null) focusFilters();
  }, []);

  const filterRef = useRef(filter);
  filterRef.current = filter;
  const onDecide = useCallback(
    (segmentId: string, status: CurationStatus) => {
      // The card's buttons go when its state changes: keep the keyboard on the next card.
      // With none left, the card itself under All (it stays), else the filter strip (the
      // decided card leaves the filter).
      const list = shownRef.current;
      const at = list.findIndex((r) => r.segmentId === segmentId);
      const next = list[at + 1] ?? list[at - 1];
      if (next) focusCard(next.segmentId);
      else if (filterRef.current === "all") focusCard(segmentId);
      else focusFilters();
      decide(segmentId, status);
    },
    [decide, focusCard],
  );

  const clear = () => {
    setPicked(new Set());
    anchor.current = null;
  };

  const decideAll = async (status: "accepted" | "rejected") => {
    const items = (status === "accepted" ? acceptable : chosen).map((r) => ({
      segment_id: r.segmentId,
      status,
    }));
    setBusy(true);
    try {
      await bulk(items);
      clear();
      toast(`${items.length} ${status}`);
      // The bar goes with the selection: focus the first card (after this render).
      requestAnimationFrame(() => focusCard(null));
    } catch (err) {
      toast(
        err instanceof BulkPartialError ? err.message : `Not saved: ${detail(err)}`,
        "error",
      );
    } finally {
      setBusy(false);
    }
  };

  const readAll = async () => {
    const ids = notRead.map((r) => r.segmentId);
    setBusy(true);
    const ok = await runPool(ids, READ_AT_ONCE, (id) => api.runPrediction(id, readEngine));
    setBusy(false);
    const count = ok.filter(Boolean).length;
    if (count > 0) started(); // results of an ocsr=off paper arrive without a reload
    if (count < ids.length) toast(`${ids.length - count} not started`, "error");
    clear();
  };

  return (
    <>
      <GridFilters
        filter={filter}
        counts={counts}
        onFilter={onFilter}
        shown={shown.length}
        onSelectAll={() => setPicked(new Set(shown.map((r) => r.segmentId)))}
      />
      {shown.length === 0 ? (
        <p className="rg-empty">
          {rows.length > 0
            ? "None here."
            : BUSY_PAPER.has(paper.status)
              ? "Structures appear here as pages are read."
              : "No structures found."}
        </p>
      ) : (
        <div className="rg-grid" ref={grid}>
          {shown.map((r, index) => (
            <StructureCard
              key={r.segmentId}
              segment={byId.get(r.segmentId)!}
              n={r.n}
              index={index}
              state={r.state}
              paperEngine={paper.engine}
              canAccept={hasDrawing(byId.get(r.segmentId)!)}
              reason={r.reason}
              failedEngine={r.failedEngine}
              selected={picked.has(r.segmentId)}
              current={selection === r.segmentId}
              onToggle={onToggle}
              onOpen={onOpen}
              onDecide={onDecide}
              onRun={onRun}
              onCompare={setComparing}
              onEdit={setEditing}
              paperName={paper.display_name}
            />
          ))}
        </div>
      )}
      {chosen.length > 0 && (
        <BulkBar
          count={chosen.length}
          acceptCount={acceptable.length}
          notRead={notRead.length}
          engineLabel={engineName(readEngine)}
          busy={busy}
          onAccept={() => void decideAll("accepted")}
          onReject={() => void decideAll("rejected")}
          onRead={() => void readAll()}
          onClear={clear}
        />
      )}
      {comparing !== null && (
        <CardCompare
          ws={ws}
          rows={rows}
          segmentId={comparing}
          onStarted={started}
          onClose={() => setComparing(null)}
        />
      )}
      {editing !== null && (
        <CardEditor ws={ws} segmentId={editing} onClose={() => setEditing(null)} />
      )}
    </>
  );
}
