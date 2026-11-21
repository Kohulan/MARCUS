import { useSyncExternalStore } from "react";

// One MediaQueryList and one change listener per query for the whole tab, however many
// components read it (a 200-card grid has up to 200 stamps). Re-created only when
// window.matchMedia itself is replaced (tests swap it).
type Store = {
  mql: MediaQueryList | null;
  of: typeof window.matchMedia | null;
  listeners: Set<() => void>;
  notify: () => void;
};
const stores = new Map<string, Store>();

function storeOf(query: string): Store {
  let s = stores.get(query);
  if (!s) {
    const listeners = new Set<() => void>();
    s = { mql: null, of: null, listeners, notify: () => listeners.forEach((fn) => fn()) };
    stores.set(query, s);
  }
  return s;
}

function listOf(query: string): MediaQueryList | null {
  if (typeof window.matchMedia !== "function") return null;
  const s = storeOf(query);
  if (s.mql === null || s.of !== window.matchMedia) {
    s.mql?.removeEventListener("change", s.notify);
    s.of = window.matchMedia;
    s.mql = window.matchMedia(query);
    if (s.listeners.size > 0) s.mql.addEventListener("change", s.notify);
  }
  return s.mql;
}

/** Calls `onChange` when `query` starts or stops matching; returns the unsubscribe. */
export function subscribeMedia(query: string, onChange: () => void): () => void {
  const s = storeOf(query);
  // before the add: a new list attaches `notify` only for listeners already there
  const mq = listOf(query);
  if (s.listeners.size === 0) mq?.addEventListener("change", s.notify);
  s.listeners.add(onChange);
  return () => {
    s.listeners.delete(onChange);
    if (s.listeners.size === 0) s.mql?.removeEventListener("change", s.notify);
  };
}

/** Whether `query` matches; null where the browser has no matchMedia (jsdom). */
export function mediaMatches(query: string): boolean | null {
  return listOf(query)?.matches ?? null;
}

const REDUCE = "(prefers-reduced-motion: reduce)";
const subscribeReduce = (onChange: () => void) => subscribeMedia(REDUCE, onChange);

/**
 * True when the visitor asked for reduced motion. On the server (and while hydrating) it
 * is false without touching window; a fresh client render reads the media query before
 * the first paint, so a landing stamp never shows a frame of motion it should not.
 */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeReduce,
    () => mediaMatches(REDUCE) ?? false,
    () => false,
  );
}
