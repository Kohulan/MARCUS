import { useEffect, useRef } from "react";
import { useLocation, useNavigationType } from "react-router-dom";
import { trackPage } from "./analytics";
import AppRoutes from "./AppRoutes";
import Footer from "./ui/Footer";
import GlassFilter from "./ui/GlassFilter";
import Header from "./ui/Header";
import { ToastHost, ToastProvider } from "./ui/Toasts";

// The app frame: the glass refraction filter (once), then one drawing sheet around the
// header, the page and the footer, and the toast host. The router is supplied by the
// caller: BrowserRouter in main.tsx, StaticRouter in entry-server.tsx, MemoryRouter in tests.
// Each navigation sends one Matomo page view (effects never run in the pre-render).
/**
 * One Matomo page view per real page change, with the route template (src/analytics.ts):
 * only when the path changes, whatever the navigation type. A search or hash change on the
 * same path (focus mode, the view switch, Back from focus mode, the tool dropping
 * ?sample=1) is the same page.
 */
function usePageViews() {
  const location = useLocation();
  const last = useRef<string | null>(null);
  useEffect(() => {
    if (last.current === location.pathname) return; // also StrictMode's second run
    last.current = location.pathname;
    trackPage(location.pathname);
  }, [location.pathname]);
}

/** The element a "#id" names; null for none, or for a malformed hash ("#%E0%A4%A"). */
function hashTarget(hash: string): Element | null {
  let id: string;
  try {
    id = decodeURIComponent(hash.slice(1));
  } catch {
    return null; // URIError: the page simply opens at its top
  }
  return id ? document.getElementById(id) : null;
}

/**
 * A forward navigation (a link) opens the next page at its top, or at the element its hash
 * names ("/about#cite"). Back and Forward keep the browser's own scroll restoration; the first
 * load is the browser's too; a replace on the same path (the tool dropping a flag) stays put.
 * Instant, never smooth, so reduced motion holds.
 */
function useScrollOnNavigate() {
  const location = useLocation();
  const type = useNavigationType();
  const last = useRef({ key: location.key, path: location.pathname });
  useEffect(() => {
    const previous = last.current;
    if (previous.key === location.key) return; // the first load, or StrictMode's second run
    last.current = { key: location.key, path: location.pathname };
    if (type === "POP") return;
    if (type === "REPLACE" && previous.path === location.pathname) return;
    const target = hashTarget(location.hash);
    if (target) target.scrollIntoView({ block: "start" });
    else window.scrollTo(0, 0);
  }, [location.key, location.pathname, location.hash, type]);
}

export default function App() {
  usePageViews();
  useScrollOnNavigate();
  return (
    <ToastProvider>
      <GlassFilter />
      <div className="frame">
        <div className="sheet">
          <Header />
          <div className="sheet__page">
            <AppRoutes />
          </div>
          <Footer />
        </div>
      </div>
      <ToastHost />
    </ToastProvider>
  );
}
