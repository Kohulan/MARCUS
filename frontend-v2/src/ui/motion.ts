import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function query(): MediaQueryList | null {
  return typeof window.matchMedia === "function" ? window.matchMedia(QUERY) : null;
}

function subscribe(onChange: () => void): () => void {
  const mql = query();
  mql?.addEventListener("change", onChange);
  return () => mql?.removeEventListener("change", onChange);
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
