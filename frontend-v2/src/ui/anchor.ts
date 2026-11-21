import { useLayoutEffect, useRef, type RefObject } from "react";

/** A box in viewport px (a DOMRect's edges). */
export type Box = { top: number; right: number; bottom: number; left: number };

export type PlaceOptions = {
  /** The side tried first; the other is taken when only it has room. */
  prefer: "above" | "below";
  /** Which edges line up: the panel's left with the anchor's left, or right with right. */
  align: "start" | "end";
  /** Space between anchor and panel. */
  gap: number;
  /** Space kept free at the bounds' edges. */
  margin: number;
};

export type Placement = {
  top: number;
  left: number;
  /** The height the panel may take; it scrolls inside past that. */
  maxHeight: number;
  side: "above" | "below";
};

/**
 * Where a panel of `size` goes next to `anchor`, kept inside `bounds` (the viewport):
 * on the preferred side when it fits there, else on the other side when it fits there, else
 * on the roomier side with its height capped (it scrolls inside). Then shifted sideways so
 * no edge leaves the bounds. Pure: the unit tests drive it with plain numbers.
 */
export function placePanel(
  anchor: Box,
  size: { width: number; height: number },
  bounds: Box,
  opts: PlaceOptions,
): Placement {
  const { gap, margin } = opts;
  const roomAbove = Math.max(0, anchor.top - gap - (bounds.top + margin));
  const roomBelow = Math.max(0, bounds.bottom - margin - (anchor.bottom + gap));
  const other = opts.prefer === "above" ? "below" : "above";
  const room = (side: "above" | "below") => (side === "above" ? roomAbove : roomBelow);
  let side: "above" | "below";
  if (size.height <= room(opts.prefer)) side = opts.prefer;
  else if (size.height <= room(other)) side = other;
  else side = room(opts.prefer) >= room(other) ? opts.prefer : other;
  const maxHeight = Math.max(0, Math.floor(room(side)));
  const height = Math.min(size.height, maxHeight);
  // An anchor scrolled past the bounds still gets a panel inside them.
  let top = side === "below" ? anchor.bottom + gap : anchor.top - gap - height;
  top = Math.min(Math.max(top, bounds.top + margin), bounds.bottom - margin - height);

  // Shifted to stay inside; one wider than the bounds keeps its left edge in.
  let left = opts.align === "start" ? anchor.left : anchor.right - size.width;
  left = Math.max(Math.min(left, bounds.right - margin - size.width), bounds.left + margin);
  return { top: Math.round(top), left: Math.round(left), maxHeight, side };
}

const clips = (overflow: string) => overflow !== "" && overflow !== "visible";

/** The viewport as a box. */
function viewport(): Box {
  const root = document.documentElement;
  return { top: 0, left: 0, right: root.clientWidth, bottom: root.clientHeight };
}

/** The ancestors that clip `el` (an overflow other than visible), nearest first. */
export function clippingAncestors(el: Element): Element[] {
  const root = document.documentElement;
  const out: Element[] = [];
  for (let p = el.parentElement; p && p !== document.body && p !== root; p = p.parentElement) {
    const s = getComputedStyle(p);
    if (clips(s.overflowX) || clips(s.overflowY)) out.push(p);
  }
  return out;
}

/** The part of the viewport an element can be seen in: the viewport cut by its clipping ancestors. */
export function visibleArea(clippers: readonly Element[]): Box {
  const box = viewport();
  for (const p of clippers) {
    const r = p.getBoundingClientRect();
    box.top = Math.max(box.top, r.top);
    box.left = Math.max(box.left, r.left);
    box.right = Math.min(box.right, r.right);
    box.bottom = Math.min(box.bottom, r.bottom);
  }
  return box;
}

const VIEW_MARGIN = 8;

/**
 * Lifts an open menu panel into the top layer (a manual popover: no ancestor's overflow,
 * transform or stacking clips or covers it) and keeps it next to its anchor, inside the
 * viewport (placePanel), on every scroll, resize and change of size. The panel stays where
 * React put it in the DOM, so the tab order, a click "inside" and Escape bubbling to the
 * menu all work as before. Position is set through the CSSOM (CSP: no style attributes).
 * Once the anchor is scrolled out of sight inside its column, `onAway` is called (the host
 * closes the menu). Without the Popover API (jsdom, old engines) the panel stays where its
 * CSS puts it.
 */
export function useAnchoredPanel(
  open: boolean,
  anchor: RefObject<HTMLElement | null>,
  panel: RefObject<HTMLElement | null>,
  opts: Pick<PlaceOptions, "prefer" | "align"> & { gap?: number },
  onAway?: () => void,
): void {
  const { prefer, align, gap = 6 } = opts;
  // Read when it fires: the host passes a fresh closure each render.
  const away = useRef(onAway);
  away.current = onAway;
  useLayoutEffect(() => {
    const el = panel.current;
    const a = anchor.current;
    if (!open || !el || !a || typeof el.showPopover !== "function") return;
    el.setAttribute("popover", "manual");
    try {
      el.showPopover();
    } catch {
      el.removeAttribute("popover");
      return;
    }
    el.setAttribute("data-anchored", "");
    const st = el.style;
    st.setProperty("position", "fixed");
    st.setProperty("margin", "0");
    st.setProperty("right", "auto");
    st.setProperty("bottom", "auto");

    // The anchor's clipping columns, found once; the panel's own size, measured when it opens
    // and when it changes size (ResizeObserver), so a scroll only reads and then writes.
    const clippers = clippingAncestors(a);
    let size = { width: 0, height: 0 };
    let measure = true;
    let frame = 0;
    const place = () => {
      frame = 0;
      if (!el.isConnected || !a.isConnected) return;
      const ar = a.getBoundingClientRect();
      const seen = visibleArea(clippers);
      if (ar.bottom <= seen.top || ar.top >= seen.bottom || ar.right <= seen.left || ar.left >= seen.right) {
        away.current?.();
        return;
      }
      const remeasured = measure;
      const scrolled = el.scrollTop;
      if (measure) {
        // At its own size: no cap from the last placement (its scroll is kept below).
        st.removeProperty("max-height");
        size = { width: el.offsetWidth, height: el.offsetHeight };
        measure = false;
      }
      const p = placePanel(ar, size, viewport(), { prefer, align, gap, margin: VIEW_MARGIN });
      st.setProperty("top", `${p.top}px`);
      st.setProperty("left", `${p.left}px`);
      st.setProperty("max-height", `${p.maxHeight}px`);
      el.dataset.side = p.side;
      if (remeasured) el.scrollTop = scrolled;
    };
    const later = (e?: Event) => {
      // The panel's own scroll (a capped panel) moves nothing.
      if (e?.type === "scroll" && e.target instanceof Node && el.contains(e.target)) return;
      if (!frame) frame = requestAnimationFrame(place);
    };
    place();
    window.addEventListener("scroll", later, true);
    window.addEventListener("resize", later);
    let ro: ResizeObserver | undefined;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver((entries) => {
        if (entries.some((entry) => entry.target === el)) measure = true;
        later();
      });
      ro.observe(el);
      ro.observe(a);
    }
    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener("scroll", later, true);
      window.removeEventListener("resize", later);
      ro?.disconnect();
      try {
        el.hidePopover();
      } catch {
        // Already hidden (the browser closed it, or it left the page).
      }
    };
  }, [open, anchor, panel, prefer, align, gap]);
}
