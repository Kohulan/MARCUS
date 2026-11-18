import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
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
/** One Matomo page view per navigation, with the route template (src/analytics.ts). */
function usePageViews() {
  const location = useLocation();
  const last = useRef<string | null>(null);
  useEffect(() => {
    if (last.current === location.key) return; // StrictMode runs the effect twice
    last.current = location.key;
    trackPage(location.pathname);
  }, [location.key, location.pathname]);
}

export default function App() {
  usePageViews();
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
