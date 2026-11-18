import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import { asEngine, engineName } from "../api/engines";
import { refreshPaper, useBulkCuration, useSaveCuration } from "../api/queries";
import { reasonText } from "../api/reasons";
import type { CurationStatus, Engine, StepOut } from "../api/types";
import { useToast } from "../ui/Toasts";
import BulkBar from "./BulkBar";
import { cardState, filterOf, ocsrSteps, type CardState, type GridFilter } from "./cardState";
import GridFilters from "./GridFilters";
import StructureCard from "./StructureCard";
import type { Workspace } from "./useWorkspace";
import "./grid.css";

/** At most this many prediction requests in flight from one bulk "Read N". */
const READ_AT_ONCE = 4;
const NO_STEPS: StepOut[] = [];
const BUSY_PAPER = new Set(["checking", "processing"]);

type Row = {
  segmentId: string;
  n: number;
  state: CardState;
  reason: string | null;
  failedEngine: string | null;
};

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

const detail = (err: unknown) => (err instanceof ApiError ? err.detail : "Something went wrong.");

/**
 * The review view: filters with counts, the grid of structure cards in (page, idx) order,
 * and the bulk bar for the selected cards.
 */
export default function ReviewGrid({ ws }: { ws: Workspace }) {
  const paper = ws.paper!;
  const { segments, steps, setSelection, selection } = ws;
  const client = useQueryClient();
  const reconnect = ws.live.reconnect; // stable (the live object itself is new each render)
  const paperId = paper.id;
  // After a prediction was accepted: open the stream again if it had ended (a finished or
  // ocsr=off paper), and read the steps once, so the card says "Reading…" at once.
  const started = useCallback(() => {
    reconnect();
    refreshPaper(client, paperId);
  }, [reconnect, client, paperId]);
  const { save } = useSaveCuration(paper.id);
  const { bulk } = useBulkCuration(paper.id);
  const toast = useToast();
  const [filter, setFilter] = useState<GridFilter>("all");
  const [picked, setPicked] = useState<ReadonlySet<string>>(() => new Set());
  const [busy, setBusy] = useState(false);
  const anchor = useRef<number | null>(null);

  // One pass over the steps for the whole grid, not one per card.
  const stepsBySegment = useMemo(() => {
    const map = new Map<string, StepOut[]>();
    for (const s of steps) {
      if (s.kind !== "ocsr" || s.segment_id === null) continue;
      const list = map.get(s.segment_id);
      if (list) list.push(s);
      else map.set(s.segment_id, [s]);
    }
    return map;
  }, [steps]);

  const rows = useMemo<Row[]>(
    () =>
      segments.map((segment, i) => {
        const own = stepsBySegment.get(segment.id) ?? NO_STEPS;
        const state = cardState(segment, own, paper);
        const newest = state === "failed" ? ocsrSteps(segment, own)[0] : undefined;
        return {
          segmentId: segment.id,
          n: i + 1,
          state,
          reason: newest ? reasonText(newest.error_class) : null,
          failedEngine: newest?.engine ?? null,
        };
      }),
    [segments, stepsBySegment, paper],
  );

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

  const chosen = rows.filter((r) => picked.has(r.segmentId));
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
    const from = anchor.current;
    anchor.current = index;
    setPicked((prev) => {
      const on = !prev.has(id);
      const next = new Set(prev);
      const [a, b] =
        range && from !== null && from < list.length
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

  const onOpen = useCallback(
    (segmentId: string) => setSelection(segmentId, { push: true }),
    [setSelection],
  );

  const onDecide = useCallback(
    (segmentId: string, status: CurationStatus) => {
      save(segmentId, { status }).catch((err: unknown) =>
        toast(`Not saved: ${detail(err)}`, "error"),
      );
    },
    [save, toast],
  );

  const onRun = useCallback(
    (segmentId: string, engine: Engine) => {
      api.runPrediction(segmentId, engine).then(
        started,
        (err: unknown) => toast(`Not started: ${detail(err)}`, "error"),
      );
    },
    [started, toast],
  );

  const clear = () => {
    setPicked(new Set());
    anchor.current = null;
  };

  const decideAll = async (status: "accepted" | "rejected") => {
    const items = chosen.map((r) => ({ segment_id: r.segmentId, status }));
    setBusy(true);
    try {
      await bulk(items);
      clear();
      toast(`${items.length} ${status}`);
    } catch (err) {
      toast(`Not saved: ${detail(err)}`, "error");
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
        <div className="rg-grid">
          {shown.map((r, index) => (
            <StructureCard
              key={r.segmentId}
              segment={byId.get(r.segmentId)!}
              n={r.n}
              index={index}
              state={r.state}
              paperEngine={paper.engine}
              reason={r.reason}
              failedEngine={r.failedEngine}
              selected={picked.has(r.segmentId)}
              current={selection === r.segmentId}
              onToggle={onToggle}
              onOpen={onOpen}
              onDecide={onDecide}
              onRun={onRun}
            />
          ))}
        </div>
      )}
      {chosen.length > 0 && (
        <BulkBar
          count={chosen.length}
          notRead={notRead.length}
          engineLabel={engineName(readEngine)}
          busy={busy}
          onAccept={() => void decideAll("accepted")}
          onReject={() => void decideAll("rejected")}
          onRead={() => void readAll()}
          onClear={clear}
        />
      )}
    </>
  );
}
