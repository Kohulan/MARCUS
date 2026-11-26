import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, errorText } from "../api/client";
import { refreshPaper } from "../api/queries";
import type { PaperDetail, SegmentOut, StepOut } from "../api/types";
import { GlassButton } from "../ui/GlassButton";
import { useToast } from "../ui/Toasts";
import PageWithBoxes, { type PageMarker } from "./PageWithBoxes";
import { pageImages } from "./PaperView";
import { pageSteps } from "./pageFailures";
import "./pick.css";

const NO_MARKERS: PageMarker[] = [];
const isActive = (s: StepOut) => s.status === "pending" || s.status === "queued" || s.status === "running";

/** The page's boxes: picked structures and candidates, in idx order; a candidate reads on click. */
function markersOf(page0: number, segments: SegmentOut[], candidates: SegmentOut[]): PageMarker[] {
  const onPage = [...segments, ...candidates]
    .filter((s) => s.page === page0)
    .sort((a, b) => a.idx - b.idx);
  if (onPage.length === 0) return NO_MARKERS;
  return onPage.map((s, i) => ({
    segmentId: s.id,
    target: s.id,
    n: i + 1,
    state: s.candidate ? "not-read" : "to-check",
    bbox: s.bbox,
    rgroups: [],
    read: s.candidate === true,
  }));
}

/**
 * Mode `pick` (owner decision 2026-11-25): the pages to pick from, then one page with its boxes.
 * A page is segmented when it is opened; a box is read (three engines) when it is clicked, and
 * its card then appears with the others. "Read all pages" switches to reading everything.
 */
/**
 * A page tile grows under the pointer or the keyboard (owner, 2026-11-26): from its middle,
 * or inward when it sits at the grid's left or right edge, so it stays on the screen.
 */
function grow(e: { currentTarget: HTMLElement }) {
  const tile = e.currentTarget;
  const grid = tile.parentElement?.getBoundingClientRect();
  const r = tile.getBoundingClientRect();
  let side = "center";
  if (grid && r.width > 0) {
    if (r.left - grid.left < r.width) side = "left";
    else if (grid.right - r.right < r.width) side = "right";
  }
  tile.dataset.grow = side;
}

export default function PickPanel({
  paper,
  segments,
  candidates,
  allSteps,
  reconnect,
}: {
  paper: PaperDetail;
  segments: SegmentOut[];
  candidates: SegmentOut[];
  allSteps: StepOut[];
  /** Reopens the live stream (a finished paper's has ended), so the new steps show live. */
  reconnect: () => void;
}) {
  const client = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState<number | null>(null);
  // Pages whose boxes came at once (segmentation cache), none of them: nothing more will come.
  const [cachedEmpty, setCachedEmpty] = useState<ReadonlySet<number>>(new Set());
  const pages = paper.pages ?? 0;
  const images = useMemo(
    () => pageImages(allSteps, pages, paper.status !== "done" && paper.status !== "failed"),
    [allSteps, pages, paper.status],
  );
  const segmentSteps = useMemo(
    () => (open === null ? [] : (pageSteps(allSteps).get(open) ?? []).filter((s) => s.kind === "segment_page")),
    [allSteps, open],
  );
  const refresh = () => {
    reconnect();
    refreshPaper(client, paper.id);
  };
  const fail = (err: unknown) => toast(`Not started: ${errorText(err)}`, "error");

  const openPage = (page0: number) => {
    setOpen(page0);
    api
      .segmentPage(paper.id, page0)
      .then((out) => {
        if (out.step_id === null) setCachedEmpty((s) => new Set(s).add(page0));
        refresh();
      })
      .catch(fail);
  };
  const readAll = () => api.setMode(paper.id, "auto").then(refresh).catch(fail);
  const onPick = (segmentId: string) => {
    if (candidates.some((c) => c.id === segmentId)) {
      api.readSegment(segmentId).then(refresh).catch(fail);
    }
  };

  const markers = open === null ? NO_MARKERS : markersOf(open, segments, candidates);
  const finding = segmentSteps.some(isActive);
  const newest = segmentSteps[0]?.status;
  const failed = open !== null && markers.length === 0 && !finding && newest === "failed";
  const none =
    open !== null &&
    markers.length === 0 &&
    !finding &&
    (newest === "done" || (newest === undefined && cachedEmpty.has(open)));

  return (
    <section className="pick" aria-label="Pick a structure">
      <div className="pick__bar glassbed">
        {open !== null && (
          <GlassButton tint="clear" size="sm" onClick={() => setOpen(null)}>
            Pick another
          </GlassButton>
        )}
        <GlassButton tint="orange" size="sm" onClick={readAll}>
          Read all pages
        </GlassButton>
      </div>
      {open === null ? (
        <div className="pick__grid" role="group" aria-label="Pick a page">
          {images.map((image, page0) => (
            <button
              key={page0}
              type="button"
              className="pick__tile"
              aria-label={`Page ${page0 + 1}`}
              onPointerEnter={grow}
              onFocus={grow}
              disabled={image.kind !== "ready"}
              onClick={() => openPage(page0)}
            >
              {image.kind === "ready" ? (
                <img src={api.pageImageUrl(paper.id, page0)} alt="" loading="lazy" decoding="async" />
              ) : (
                <span className="pick__wait" aria-hidden="true" />
              )}
              <span className="pick__num" aria-hidden="true">
                {page0 + 1}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <div className="pick__page">
          {none && <p className="pick__note">No structures found on this page</p>}
          {failed && (
            <div className="pick__note">
              <p>Structures could not be found on this page.</p>
              <GlassButton tint="clear" size="sm" onClick={() => openPage(open)}>
                Try again
              </GlassButton>
            </div>
          )}
          {finding && <p className="pick__note">Finding structures…</p>}
          <PageWithBoxes
            paperId={paper.id}
            page0={open}
            pages={pages}
            imageKind={images[open]?.kind ?? "waiting"}
            imageReason={null}
            markers={markers}
            selected={null}
            hovered={null}
            onPick={onPick}
            onHover={() => undefined}
            isMain={false}
            onMark={null}
          />
        </div>
      )}
    </section>
  );
}
