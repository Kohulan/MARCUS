// The editor's left panel: the crop the engines read, so the curator sees what the paper
// shows while drawing. "Find on paper" swaps the crop for the page with only this
// structure's box marked (pageBox, as the paper view places it), "Back" returns. The page opens
// zoomed in on the box ("+" / "−", drag or scroll to move). Ketcher on the right is untouched.
import { useLayoutEffect, useRef, useState, type PointerEvent } from "react";
import { GlassButton } from "../ui/GlassButton";
import { boxStyle } from "./pageBox";

export type EditorSourceInfo = {
  /** The crop (a segment's image, or the uploaded single image). */
  image: string;
  /** The structure's page: 300 DPI page PNG, bbox in its pixels, 0-based page. Null: no page. */
  page: { url: string; bbox: [number, number, number, number]; page0: number } | null;
};

/** Zoom steps of the page. It opens at the largest step up to MAX_START where the box fills
 * at most FILL of the view: the drawing and its label at a readable size. */
export const ZOOMS = [1, 1.5, 2, 3, 4, 6] as const;
const MAX_START = ZOOMS.indexOf(4);
const FILL = 0.75;
const PAD = 16; // .editor-src__view padding

export function EditorSource({ source }: { source: EditorSourceInfo }) {
  const page = source.page;
  const [onPage, setOnPage] = useState(false);
  // The page's natural size, from its load: the marker waits for it.
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  // null: not chosen yet (the opening zoom, once the page and the view are measured)
  const [step, setStep] = useState<number | null>(null);
  const zoom = ZOOMS[step ?? 0]!;
  // One button for "Find on paper" and "Back": the same element keeps the focus (focused on
  // click too: Safari and tests do not focus a clicked button).
  const button = useRef<HTMLButtonElement>(null);
  const toggle = () => {
    setOnPage((v) => !v);
    setStep(null);
    anchor.current = null;
    button.current?.focus();
  };

  // The page's width at zoom 1: the whole page fits the view. Measured once the page is in.
  const view = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState<number | null>(null);
  const measure = () => {
    const v = view.current;
    if (!v || !size) return;
    const w = v.clientWidth - 2 * PAD;
    const h = v.clientHeight - 2 * PAD;
    if (w > 0 && h > 0) setFit(Math.min(w, (h * size.w) / size.h));
  };
  useLayoutEffect(measure, [size, onPage]);
  useLayoutEffect(() => {
    const v = view.current;
    if (step !== null || fit === null || !size || !page || !v) return;
    const [x0, y0, x1, y1] = page.bbox;
    const scale = fit / size.w; // page pixels to view pixels at zoom 1
    const fits = (z: number) =>
      (x1 - x0) * scale * z <= FILL * v.clientWidth && (y1 - y0) * scale * z <= FILL * v.clientHeight;
    let best = 0;
    for (let i = 1; i <= MAX_START; i++) if (fits(ZOOMS[i]!)) best = i;
    setStep(best);
  }, [step, fit, size, page]);
  useLayoutEffect(() => {
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }); // re-added each render: `measure` reads the newest size

  // The point of the page (fractions of its width and height) the view is centred on: the box
  // at opening, the view's centre when the zoom changes.
  const anchor = useRef<{ fx: number; fy: number } | null>(null);
  const width = fit !== null && step !== null ? fit * zoom : null;
  // where the sheet starts in the view: centred while narrower than it (margin auto)
  const left = (v: HTMLElement, w: number) => Math.max(PAD, (v.clientWidth - w) / 2);
  useLayoutEffect(() => {
    const v = view.current;
    if (!v || !page || !size || width === null) return;
    const [x0, y0, x1, y1] = page.bbox;
    const at = anchor.current ?? { fx: (x0 + x1) / 2 / size.w, fy: (y0 + y1) / 2 / size.h };
    const height = (width * size.h) / size.w;
    v.scrollLeft = at.fx * width + left(v, width) - v.clientWidth / 2;
    v.scrollTop = at.fy * height + PAD - v.clientHeight / 2;
  }, [width, size, page]);
  const zoomBy = (d: number) => {
    const v = view.current;
    if (v && size && width !== null) {
      const height = (width * size.h) / size.w;
      anchor.current = {
        fx: (v.scrollLeft + v.clientWidth / 2 - left(v, width)) / width,
        fy: (v.scrollTop + v.clientHeight / 2 - PAD) / height,
      };
    }
    setStep((s) => Math.min(Math.max((s ?? 0) + d, 0), ZOOMS.length - 1));
  };

  // Drag to move the page (a mouse or a pen; touch scrolls by itself).
  const drag = useRef<{ x: number; y: number; id: number } | null>(null);
  const onDown = (e: PointerEvent<HTMLDivElement>) => {
    if (!onPage || e.button !== 0 || e.pointerType === "touch") return;
    drag.current = { x: e.clientX, y: e.clientY, id: e.pointerId };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    e.currentTarget.scrollLeft += d.x - e.clientX;
    e.currentTarget.scrollTop += d.y - e.clientY;
    drag.current = { ...d, x: e.clientX, y: e.clientY };
  };
  const onUp = () => {
    drag.current = null;
  };

  return (
    <div className="editor-src">
      <div
        ref={view}
        className={onPage ? "editor-src__view editor-src__view--page" : "editor-src__view"}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
      >
        {onPage && page ? (
          <div
            className="editor-src__sheet"
            data-zoom={zoom}
            style={width !== null ? { width: `${width}px` } : undefined}
          >
            <img
              className="editor-src__img"
              src={page.url}
              alt={`Page ${page.page0 + 1}`}
              draggable={false}
              onLoad={(e) => setSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
            />
            {size && size.w > 0 && size.h > 0 ? (
              <span className="editor-src__mark" aria-hidden="true" style={boxStyle(page.bbox, size.w, size.h)} />
            ) : null}
          </div>
        ) : (
          <img
            className="editor-src__img editor-src__crop"
            src={source.image}
            alt={page ? "Crop the engines read" : "Uploaded image"}
          />
        )}
      </div>
      {page ? (
        <div className="editor-src__bar">
          <GlassButton ref={button} tint="clear" size="sm" onClick={toggle}>
            {onPage ? "Back" : "Find on paper"}
          </GlassButton>
          {onPage ? (
            <>
              <GlassButton tint="clear" size="sm" label="Zoom out" disabled={(step ?? 0) === 0} onClick={() => zoomBy(-1)}>
                −
              </GlassButton>
              <GlassButton
                tint="clear"
                size="sm"
                label="Zoom in"
                disabled={step === ZOOMS.length - 1}
                onClick={() => zoomBy(1)}
              >
                +
              </GlassButton>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
