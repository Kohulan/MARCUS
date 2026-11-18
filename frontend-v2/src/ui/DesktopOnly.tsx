import { useState, useSyncExternalStore } from "react";
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
 * render (useSyncExternalStore), so a tool first opened below 1024 px is never mounted, not
 * even for one frame: no stream, query or upload starts on a phone. Once mounted, the tool
 * stays mounted: a window narrowed below 1024 px (half-screen snapping, docked DevTools)
 * hides it behind the note and keeps its state (an unsaved drawing, a note draft, a filled
 * form); widening shows it again as it was. /app is not pre-rendered; the server snapshot
 * (wide) only keeps renderToString from touching window.
 */
export default function DesktopOnly({ children }: { children: ReactNode }) {
  const wide = useSyncExternalStore(subscribe, isWide, () => true);
  // Decided at the first wide read, never undone (state set during render: no extra frame).
  const [mounted, setMounted] = useState(wide);
  if (wide && !mounted) setMounted(true);

  const note = (
    <main className="desktop-only">
      <h1 className="desktop-only__note">MARCUS is made for a desktop screen</h1>
      <a href="/" className="desktop-only__back">
        Back to start
      </a>
    </main>
  );
  if (!mounted) return note;
  return (
    <>
      {/* data-keys-off: the review keys go inert while the tool is hidden (ui/keysHeld.ts). */}
      <div className="desktop-only__tool" hidden={!wide} data-keys-off={wide ? undefined : ""}>
        {children}
      </div>
      {!wide && note}
    </>
  );
}
