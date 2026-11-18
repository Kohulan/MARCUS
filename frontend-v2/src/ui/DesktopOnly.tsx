import { useSyncExternalStore } from "react";
import type { ReactNode } from "react";
import "./ui.css";

const MIN_WIDTH = 1024;
const QUERY = `(min-width: ${MIN_WIDTH}px)`;

let query: MediaQueryList | null = null;
let queryOf: typeof window.matchMedia | null = null;

/** The one (min-width: 1024px) query; null where the browser has no matchMedia (jsdom). */
function wideQuery(): MediaQueryList | null {
  if (typeof window.matchMedia !== "function") return null;
  if (query === null || queryOf !== window.matchMedia) {
    queryOf = window.matchMedia;
    query = window.matchMedia(QUERY);
  }
  return query;
}

function subscribe(onChange: () => void): () => void {
  const mq = wideQuery();
  mq?.addEventListener("change", onChange);
  window.addEventListener("resize", onChange);
  return () => {
    mq?.removeEventListener("change", onChange);
    window.removeEventListener("resize", onChange);
  };
}

function isWide(): boolean {
  const mq = wideQuery();
  return mq ? mq.matches : window.innerWidth >= MIN_WIDTH;
}

/**
 * The tool needs at least 1024 px. Below that it shows one note. The width is read during
 * render (useSyncExternalStore), so below 1024 px the tool is never mounted, not even for
 * one frame: no stream, query or upload starts on a phone. /app is not pre-rendered; the
 * server snapshot (wide) only keeps renderToString from touching window.
 */
export default function DesktopOnly({ children }: { children: ReactNode }) {
  const wide = useSyncExternalStore(subscribe, isWide, () => true);

  if (wide) return <>{children}</>;
  return (
    <main className="desktop-only">
      <p className="desktop-only__note">MARCUS is made for a desktop screen</p>
    </main>
  );
}
