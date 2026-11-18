import { useEffect, type RefObject } from "react";

// Where focus goes when a dialog closes: back to what had it (the opener). When that cannot
// take it (gone after a decision or a live update, disabled, or it was the page body), to the
// page's focus home (data-focus-home: the focus-mode region), so the review keys, which act
// only inside that region, keep working. With no home, focus stays where it fell.

const HOME = "[data-focus-home]";

/** Gives focus back to `before`, else to the page's focus home. */
export function returnFocus(before: Element | null): void {
  if (before instanceof HTMLElement && before.isConnected && before !== document.body) {
    before.focus();
    if (document.activeElement === before) return;
  }
  document.querySelector<HTMLElement>(HOME)?.focus({ preventScroll: true });
}

/**
 * Opens a native <dialog> as a modal (top layer; the page behind is inert) and moves focus to
 * `first`; on unmount gives focus back (returnFocus). jsdom and old engines without
 * showModal get the open attribute.
 */
export function useModal(
  dialog: RefObject<HTMLDialogElement | null>,
  first: RefObject<HTMLElement | null>,
): void {
  useEffect(() => {
    const el = dialog.current;
    const before = document.activeElement;
    if (el && !el.open) {
      if (typeof el.showModal === "function") el.showModal();
      else el.setAttribute("open", "");
    }
    first.current?.focus();
    return () => returnFocus(before);
  }, [dialog, first]);
}
