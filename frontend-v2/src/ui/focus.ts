import { useEffect, type DependencyList, type RefObject } from "react";

/** True when focus has nowhere useful to be: the body, a removed element or a disabled one. */
export function focusLost(el: Element | null = document.activeElement): boolean {
  return (
    el === null ||
    el === document.body ||
    !el.isConnected ||
    ((el instanceof HTMLButtonElement || el instanceof HTMLInputElement) && el.disabled)
  );
}

/** Gives focus back to `before` (a dialog's opener), else to the host's `fallback`. */
export function returnFocus(before: Element | null, fallback: HTMLElement | null): void {
  if (before instanceof HTMLElement && !focusLost(before)) {
    before.focus();
    if (document.activeElement === before) return;
  }
  if (fallback?.isConnected) fallback.focus({ preventScroll: true });
}

/**
 * After a change in `deps` (a step, a decision, a live update) took the focused control away
 * (it unmounted or was disabled), focus goes to `target` instead of falling to the page.
 */
export function useFocusRescue(target: RefObject<HTMLElement | null>, deps: DependencyList): void {
  useEffect(() => {
    if (focusLost()) target.current?.focus({ preventScroll: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the caller names what moves focus
  }, deps);
}
