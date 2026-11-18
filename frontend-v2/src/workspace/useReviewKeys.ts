import { useEffect, useRef } from "react";
import { keysHeld } from "../ui/keysHeld";

export type ReviewKeyHandlers = {
  accept: () => void;
  reject: () => void;
  /** E: open the editor. F11 fills it; until then a no-op. */
  edit: () => void;
  /** C: compare engines. F10 fills it; until then a no-op. */
  compare: () => void;
  prev: () => void;
  next: () => void;
  close: () => void;
  help: () => void;
};

/** Where typing happens: keys there are text, not review actions. */
const TYPING = new Set(["INPUT", "TEXTAREA", "SELECT", "IFRAME"]);

function typingIn(el: EventTarget | Element | null): boolean {
  if (!(el instanceof Element)) return false;
  return TYPING.has(el.tagName) || (el instanceof HTMLElement && el.isContentEditable);
}

/** Arrows may repeat (hold → to step through); a held A or R must not decide again and again. */
const REPEATS = new Set(["ArrowLeft", "ArrowRight"]);

function pick(h: ReviewKeyHandlers, key: string): (() => void) | undefined {
  switch (key) {
    case "a":
    case "A":
      return h.accept;
    case "r":
    case "R":
      return h.reject;
    case "e":
    case "E":
      return h.edit;
    case "c":
    case "C":
      return h.compare;
    case "ArrowLeft":
      return h.prev;
    case "ArrowRight":
      return h.next;
    case "Escape":
      return h.close;
    case "?":
      return h.help;
    default:
      return undefined;
  }
}

/**
 * The focus-mode keys (Global Constraints, exact): A accept, R reject, E edit, C compare,
 * ← previous, → next, Esc back to grid, ? key list. One document listener while mounted.
 * Ignored while focus is in an input, textarea, select or the Ketcher iframe, while any
 * dialog is open or the tool is hidden (ui/keysHeld), and when Ctrl, Meta or Alt is held
 * (browser and system shortcuts stay theirs).
 */
export function useReviewKeys(handlers: ReviewKeyHandlers): void {
  const latest = useRef(handlers);
  latest.current = handlers;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.isComposing) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (typingIn(e.target) || typingIn(document.activeElement)) return;
      // A dialog is open (native or modal div) or the tool is hidden: it owns the keys,
      // wherever focus is. Esc keeps its default, or a native dialog's cancel never fires.
      if (keysHeld()) return;
      const fn = pick(latest.current, e.key);
      if (!fn) return;
      e.preventDefault(); // arrows would scroll the page
      if (e.repeat && !REPEATS.has(e.key)) return;
      fn();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
}
