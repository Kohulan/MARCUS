// The editor's left panel: the crop the engines read, so the curator sees what the paper
// shows while drawing. "Find on paper" swaps the crop for the page with only this
// structure's box marked (pageBox, as the paper view places it), "Back" returns. The page opens
// whole; "+" zooms in on the box ("−", drag or scroll to move), and a hint says so until the
// curator has zoomed once. Ketcher on the right is untouched.
import { useLayoutEffect, useRef, useState, type PointerEvent } from "react";
import { GlassButton } from "../ui/GlassButton";
import { boxStyle } from "./pageBox";

export type EditorSourceInfo = {
  /** The crop (a segment's image, or the uploaded single image). */
  image: string;
  /** The structure's page: 300 DPI page PNG, bbox in its pixels, 0-based page. Null: no page. */
  page: { url: string; bbox: [number, number, number, number]; page0: number } | null;
};

/** Zoom steps of the page; it opens at 1 (the whole page). */
export const ZOOMS = [1, 1.5, 2, 3, 4, 6] as const;
const PAD = 16; // .editor-src__view padding

// The zoom hint: shown until the curator zooms once (this browser); editor.css times it.
const HINT_KEY = "marcus.zoomHintSeen";
function hintSeen(): boolean {
  try {
    return localStorage.getItem(HINT_KEY) === "1";
  } catch {
    return false;
  }
}
function markHintSeen(): void {
  try {
    localStorage.setItem(HINT_KEY, "1");
  } catch {
    // storage blocked: the hint shows again next time
  }
}

export function EditorSource({ source }: { source: EditorSourceInfo }) {
  const page = source.page;
  const [onPage, setOnPage] = useState(false);
  // The page's natural size, from its load: the marker waits for it.
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [step, setStep] = useState(0);
  const zoom = ZOOMS[step]!;
  // The zoom hint; its own CSS animation ends it (onAnimationEnd), or the first zoom does.
  const [hint, setHint] = useState(false);
  // One button for "Find on paper" and "Back": the same element keeps the focus (focused on
  // click too: Safari and tests do not focus a clicked button).
  const button = useRef<HTMLButtonElement>(null);
  const toggle = () => {
    setHint(!onPage && !hintSeen());
    setOnPage((v) => !v);
    setStep(0);
    button.current?.focus();
  };

  // The page's width at zoom 1: the whole page fits the view. Measured once the page is in,
  // and again when the window changes size.
  const view = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState<number | null>(null);
  useLayoutEffect(() => {
    const measure = () => {
      const v = view.current;
      if (!v || !size) return;
      const w = v.clientWidth - 2 * PAD;
      const h = v.clientHeight - 2 * PAD;
      if (w > 0 && h > 0) setFit(Math.min(w, (h * size.w) / size.h));
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [size, onPage]);

  const width = fit !== null ? fit * zoom : null;
  const height = width !== null && size ? (width * size.h) / size.w : null;
  // Where the sheet starts in the view: centred across while narrower than it (margin auto),
  // PAD from the top.
  const origin = (v: HTMLElement, w: number) => ({ x: Math.max(PAD, (v.clientWidth - w) / 2), y: PAD });

  // The point of the page (fractions of its width and height) to centre once the zoom has
  // changed: the box when zooming in from the whole page, else the view's centre. Only a zoom
  // sets it, so a live update of the dialog never moves the page.
  const anchor = useRef<{ fx: number; fy: number } | null>(null);
  useLayoutEffect(() => {
    const v = view.current;
    const at = anchor.current;
    if (!v || !at || width === null || height === null) return;
    anchor.current = null;
    const o = origin(v, width);
    v.scrollLeft = at.fx * width + o.x - v.clientWidth / 2;
    v.scrollTop = at.fy * height + o.y - v.clientHeight / 2;
  }, [width, height]);
  const zoomBy = (d: number) => {
    setHint(false);
    markHintSeen();
    const v = view.current;
    if (!v || !page || !size || width === null || height === null) return;
    if (step === 0) {
      const [x0, y0, x1, y1] = page.bbox;
      anchor.current = { fx: (x0 + x1) / 2 / size.w, fy: (y0 + y1) / 2 / size.h };
    } else {
      const o = origin(v, width);
      anchor.current = {
        fx: (v.scrollLeft + v.clientWidth / 2 - o.x) / width,
        fy: (v.scrollTop + v.clientHeight / 2 - o.y) / height,
      };
    }
    setStep((s) => Math.min(Math.max(s + d, 0), ZOOMS.length - 1));
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
            className={width !== null ? "editor-src__sheet editor-src__sheet--sized" : "editor-src__sheet"}
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
      {hint ? (
        <p
          className="editor-src__hint"
          role="status"
          onAnimationEnd={(e) => e.animationName === "editor-hint-out" && setHint(false)}
        >
          Use + and − to zoom
        </p>
      ) : null}
      {page ? (
        <div className="editor-src__bar">
          <GlassButton ref={button} tint="clear" size="sm" onClick={toggle}>
            {onPage ? "Back" : "Find on paper"}
          </GlassButton>
          {onPage ? (
            <>
              <GlassButton tint="clear" size="sm" label="Zoom out" disabled={step === 0} onClick={() => zoomBy(-1)}>
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
