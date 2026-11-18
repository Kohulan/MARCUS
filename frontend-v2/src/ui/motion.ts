import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

// One media query and one change listener for the whole tab, however many components read
// it (a 200-card grid has up to 200 stamps). Re-created only when window.matchMedia itself
// is replaced (tests swap it).
let mql: MediaQueryList | null = null;
let mqlOf: typeof window.matchMedia | null = null;
const listeners = new Set<() => void>();
const notify = () => {
  for (const fn of listeners) fn();
};

function query(): MediaQueryList | null {
  if (typeof window.matchMedia !== "function") return null;
  if (mql === null || mqlOf !== window.matchMedia) {
    mql?.removeEventListener("change", notify);
    mqlOf = window.matchMedia;
    mql = window.matchMedia(QUERY);
    if (listeners.size > 0) mql.addEventListener("change", notify);
  }
  return mql;
}

function subscribe(onChange: () => void): () => void {
  const mq = query(); // before the add: a new query attaches `notify` only for listeners already there
  if (listeners.size === 0) mq?.addEventListener("change", notify);
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
    if (listeners.size === 0) mql?.removeEventListener("change", notify);
  };
}

/**
 * True when the visitor asked for reduced motion. On the server (and while hydrating) it
 * is false without touching window; a fresh client render reads the media query before
 * the first paint, so a landing stamp never shows a frame of motion it should not.
 */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => query()?.matches ?? false,
    () => false,
  );
}
