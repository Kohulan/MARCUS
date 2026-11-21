import { memo, useState } from "react";
import { api } from "../api/client";
import type { SegmentOut } from "../api/types";
import { GlassButton } from "../ui/GlassButton";
import { structureTag } from "../ui/tag";
import type { CardState } from "./cardState";
import { boxStyle } from "./pageBox";
import { rgroupTag } from "./rgroups";

export type PageMarker = {
  segmentId: string;
  /** 1-based, in (page, idx) order: the `[nn]` tag. */
  n: number;
  state: CardState;
  bbox: SegmentOut["bbox"];
  /** R-group labels of the structure shown ([] for none): the marker carries the tag. */
  rgroups: string[];
};

/** Whether the page image can be shown: rendered, still to come, or failed with a reason. */
export type PageImage = { kind: "ready" } | { kind: "waiting" } | { kind: "failed"; reason: string };

type Props = {
  paperId: string;
  /** 0-based API page; the UI shows page0 + 1. */
  page0: number;
  pages: number;
  /** Primitives, not a PageImage object: a live steps refresh leaves unchanged pages alone. */
  imageKind: PageImage["kind"];
  /** Why the page failed (reasonText), for `imageKind` "failed". */
  imageReason: string | null;
  markers: PageMarker[];
  /** The selected segment, when it is on this page. */
  selected: string | null;
  /** The hovered segment (its card or its marker), when it is on this page. */
  hovered: string | null;
  onPick: (segmentId: string) => void;
  onHover: (segmentId: string | null) => void;
};

/**
 * One page of the Paper view: the page image (lazy), with a marker per segment placed from
 * its `bbox` (pageBox: percent of the image's natural size, so no measuring). Markers are
 * buttons: a click selects the structure, hovering outlines its card. Memoised: hovering
 * re-renders only the pages whose `selected` or `hovered` changed.
 */
function PageWithBoxes({
  paperId,
  page0,
  pages,
  imageKind,
  imageReason,
  markers,
  selected,
  hovered,
  onPick,
  onHover,
}: Props) {
  const label = `Page ${page0 + 1}`;
  // "Try again" after a failed load asks afresh (a new URL, so the browser loads it again).
  const [attempt, setAttempt] = useState(0);
  const base = api.pageImageUrl(paperId, page0);
  const src = attempt === 0 ? base : `${base}?attempt=${attempt}`;
  // The image's natural size, from its load (markers wait for it).
  const [size, setSize] = useState<{ src: string; w: number; h: number } | null>(null);
  const natural = size !== null && size.src === src ? size : null;
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const broken = failedSrc === src;
  const ready = imageKind === "ready" && !broken;

  return (
    <figure className="pv-page" data-page={page0}>
      <figcaption className="pv-page__cap">
        <span aria-hidden="true">+</span>
        <span>{`${label} of ${pages}`}</span>
        <span aria-hidden="true">+</span>
      </figcaption>
      {ready ? (
        <div className="pv-page__sheet">
          <img
            className="pv-page__img"
            src={src}
            alt={label}
            loading="lazy"
            decoding="async"
            onLoad={(e) =>
              setSize({ src, w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })
            }
            onError={() => setFailedSrc(src)}
          />
          {natural &&
            markers.map((m) => {
              const lit = m.segmentId === selected || m.segmentId === hovered;
              const cls = ["pv-marker", `pv-marker--${m.state}`];
              if (lit) cls.push("pv-marker--lit");
              return (
                <button
                  key={m.segmentId}
                  type="button"
                  className={cls.join(" ")}
                  style={boxStyle(m.bbox, natural.w, natural.h)}
                  data-marker={m.segmentId}
                  aria-label={
                    `Structure ${structureTag(m.n)} on page ${page0 + 1}` +
                    (m.rgroups.length > 0 ? `, ${rgroupTag(m.rgroups)}` : "")
                  }
                  aria-current={m.segmentId === selected ? "true" : undefined}
                  onClick={() => onPick(m.segmentId)}
                  onMouseEnter={() => onHover(m.segmentId)}
                  onMouseLeave={() => onHover(null)}
                  onFocus={() => onHover(m.segmentId)}
                  onBlur={() => onHover(null)}
                >
                  <span className="pv-marker__tag" aria-hidden="true">
                    {structureTag(m.n)}
                  </span>
                  {m.rgroups.length > 0 && (
                    <span className="pv-marker__rgroups" aria-hidden="true">
                      {rgroupTag(m.rgroups)}
                    </span>
                  )}
                </button>
              );
            })}
        </div>
      ) : (
        <div
          className={
            imageKind === "failed"
              ? "pv-page__sheet pv-page__sheet--failed"
              : "pv-page__sheet pv-page__sheet--empty"
          }
        >
          {imageKind === "failed" ? (
            <p className="pv-page__why">{`Could not be read: ${imageReason ?? "an unknown error"}`}</p>
          ) : broken ? (
            <div className="pv-page__retry">
              <p className="pv-page__why">The page image could not be loaded</p>
              <GlassButton tint="clear" size="sm" onClick={() => setAttempt((a) => a + 1)}>
                Try again
              </GlassButton>
            </div>
          ) : (
            <p className="pv-page__why">Not ready</p>
          )}
        </div>
      )}
    </figure>
  );
}

export default memo(PageWithBoxes);
