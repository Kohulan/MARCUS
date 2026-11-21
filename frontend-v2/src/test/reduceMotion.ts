// Tests only: window.matchMedia stubbed so the reduced-motion query matches (or not).
import { vi } from "vitest";

/**
 * Stubs window.matchMedia: `(prefers-reduced-motion: reduce)` matches when `on`, no other query
 * does. Returns the restore.
 */
export function reduceMotion(on: boolean): () => void {
  const real = window.matchMedia;
  window.matchMedia = vi.fn((query: string) => ({
    matches: on && query.includes("prefers-reduced-motion: reduce"),
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
  return () => {
    window.matchMedia = real;
  };
}
