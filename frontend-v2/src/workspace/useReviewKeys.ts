import { useEffect, useRef, type RefObject } from "react";
import { keysHeld } from "../ui/keysHeld";

export type ReviewKeyHandlers = {
  accept: () => void;
  reject: () => void;
  edit: () => void;
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

/**
 * The focus-mode keys (Global Constraints, exact), one table for the dispatch here and the
 * Keys list: what is shown, the KeyboardEvent.key values, the label and the handler. Only
 * arrows repeat (hold → to step through); a held A or R must not decide again and again.
 */
export const REVIEW_KEYS: {
  shown: string;
  keys: string[];
  label: string;
  action: keyof ReviewKeyHandlers;
  repeats?: boolean;
}[] = [
  { shown: "A", keys: ["a", "A"], label: "Accept", action: "accept" },
  { shown: "R", keys: ["r", "R"], label: "Reject", action: "reject" },
  { shown: "E", keys: ["e", "E"], label: "Edit", action: "edit" },
  { shown: "C", keys: ["c", "C"], label: "Compare engines", action: "compare" },
  { shown: "←", keys: ["ArrowLeft"], label: "Previous", action: "prev", repeats: true },
  { shown: "→", keys: ["ArrowRight"], label: "Next", action: "next", repeats: true },
  { shown: "Esc", keys: ["Escape"], label: "Back to grid", action: "close" },
  { shown: "?", keys: ["?"], label: "This list", action: "help" },
];

/**
 * The focus-mode keys (Global Constraints, exact): A accept, R reject, E edit, C compare,
 * ← previous, → next, Esc back to grid, ? key list. One document listener while mounted.
 * One rule for the components inside: one that handles a key calls preventDefault, and the
 * review keys skip it (no stopPropagation anywhere). Active only while focus is inside
 * `region` (WCAG 2.1.4 "active only on focus": a key pressed elsewhere on the page, or with
 * focus on the body, does nothing); the region takes focus when focus mode opens and after
 * each step or decision (FocusMode). Ignored while focus is in an input, textarea, select or
 * the Ketcher iframe, while any dialog is open or the tool is hidden (ui/keysHeld), and when
 * Ctrl, Meta or Alt is held (browser and system shortcuts stay theirs).
 */
export function useReviewKeys(
  region: RefObject<HTMLElement | null>,
  handlers: ReviewKeyHandlers,
): void {
  const latest = useRef(handlers);
  latest.current = handlers;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.isComposing) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const el = region.current;
      if (!el || !(e.target instanceof Node) || !el.contains(e.target)) return;
      if (typingIn(e.target) || typingIn(document.activeElement)) return;
      // A dialog is open or the tool is hidden: it owns the keys, wherever focus is. Esc
      // keeps its default, or a native dialog's cancel never fires.
      if (keysHeld()) return;
      const k = REVIEW_KEYS.find(({ keys }) => keys.includes(e.key));
      if (!k) return;
      e.preventDefault(); // arrows would scroll the page
      if (e.repeat && !k.repeats) return;
      latest.current[k.action]();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [region]);
}
