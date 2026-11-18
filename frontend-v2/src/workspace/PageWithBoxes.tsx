import { memo, useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { api } from "../api/client";
import type { SegmentOut } from "../api/types";
import { GlassButton } from "../ui/GlassButton";
import { structureTag } from "../ui/tag";
import type { CardState } from "./cardState";

export type PageMarker = {
  segmentId: string;
  /** 1-based, in (page, idx) order: the `[nn]` tag. */
  n: number;
  state: CardState;
  bbox: SegmentOut["bbox"];
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

type Size = { w: number; h: number; scale: number };

const px = (v: number) => `${+v.toFixed(2)}px`;
const clamp = (v: number, max: number) => Math.min(Math.max(v, 0), max);

/**
 * One page of the Paper view: the page image (lazy), with a marker per segment drawn from
 * its `bbox` ([x0, y0, x1, y1] in pixels of the 300 DPI page PNG, the image served), scaled
 * by the width the image is shown at over its natural width. Markers are buttons: a click
 * selects the structure, hovering outlines its card. Memoised: hovering re-renders only the
 * pages whose `selected` or `hovered` changed.
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
  const img = useRef<HTMLImageElement>(null);
  const [size, setSize] = useState<Size | null>(null);
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const broken = failedSrc === src;
  const ready = imageKind === "ready" && !broken;

  const measure = useCallback(() => {
    const el = img.current;
    if (!el || !el.naturalWidth || !el.clientWidth) return;
    const next = { w: el.naturalWidth, h: el.naturalHeight, scale: el.clientWidth / el.naturalWidth };
    setSize((prev) =>
      prev && prev.w === next.w && prev.h === next.h && prev.scale === next.scale ? prev : next,
    );
  }, []);

  // The shown width follows the column (window resize, a scrollbar coming or going).
  useEffect(() => {
    const el = img.current;
    if (!ready || !el) return;
    if (el.complete) measure(); // loaded from the cache before this effect ran
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [ready, measure]);

  const box = (bbox: SegmentOut["bbox"], s: Size): CSSProperties => {
    const [a, b, c, d] = bbox;
    const left = clamp(Math.min(a, c), s.w);
    const top = clamp(Math.min(b, d), s.h);
    const right = clamp(Math.max(a, c), s.w);
    const bottom = clamp(Math.max(b, d), s.h);
    return {
      left: px(left * s.scale),
      top: px(top * s.scale),
      width: px((right - left) * s.scale),
      height: px((bottom - top) * s.scale),
    };
  };

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
            ref={img}
            className="pv-page__img"
            src={src}
            alt={label}
            loading="lazy"
            decoding="async"
            onLoad={measure}
            onError={() => setFailedSrc(src)}
          />
          {size &&
            markers.map((m) => {
              const lit = m.segmentId === selected || m.segmentId === hovered;
              const cls = ["pv-marker", `pv-marker--${m.state}`];
              if (lit) cls.push("pv-marker--lit");
              return (
                <button
                  key={m.segmentId}
                  type="button"
                  className={cls.join(" ")}
                  style={box(m.bbox, size)}
                  data-marker={m.segmentId}
                  aria-label={`Structure ${structureTag(m.n)} on page ${page0 + 1}`}
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
