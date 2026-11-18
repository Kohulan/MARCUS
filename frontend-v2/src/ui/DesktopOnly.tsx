import { useState, useSyncExternalStore } from "react";
import type { ReactNode } from "react";
import { mediaMatches, subscribeMedia } from "./motion";
import "./ui.css";

const MIN_WIDTH = 1024;
const QUERY = `(min-width: ${MIN_WIDTH}px)`;

// The media query's change event, through the tab's one list (ui/motion); the window's
// resize event only where the browser has no matchMedia.
function subscribe(onChange: () => void): () => void {
  if (typeof window.matchMedia === "function") return subscribeMedia(QUERY, onChange);
  window.addEventListener("resize", onChange);
  return () => window.removeEventListener("resize", onChange);
}

function isWide(): boolean {
  return mediaMatches(QUERY) ?? window.innerWidth >= MIN_WIDTH;
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
