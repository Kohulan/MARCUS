import { lazy, Suspense, type ReactNode } from "react";
import { Route, Routes } from "react-router-dom";
import About from "./pages/About";
import Disclaimer from "./pages/Disclaimer";
import Landing from "./pages/Landing";
import NotFound from "./pages/NotFound";
import Privacy from "./pages/Privacy";
import DesktopOnly from "./ui/DesktopOnly";

// The tool is client-only and split off so the pre-rendered pages stay small.
const ToolHome = lazy(() => import("./tool/ToolHome"));
const Workspace = lazy(() => import("./workspace/Workspace"));
const ImageResult = lazy(() => import("./images/ImageResult"));
const QueryProvider = lazy(() => import("./api/QueryProvider"));

// Below 1024 px DesktopOnly shows its note instead: the tool chunk is not even loaded,
// so no query, stream or upload starts on a phone.
function Tool({ children }: { children: ReactNode }) {
  return (
    <DesktopOnly>
      <Suspense fallback={<p role="status">Loading…</p>}>
        <QueryProvider>{children}</QueryProvider>
      </Suspense>
    </DesktopOnly>
  );
}

// One declarative route tree for the browser (BrowserRouter) and the
// pre-render (StaticRouter). No data router, so no hydration script.
export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/about" element={<About />} />
      <Route path="/privacy" element={<Privacy />} />
      <Route path="/disclaimer" element={<Disclaimer />} />
      <Route
        path="/app"
        element={
          <Tool>
            <ToolHome />
          </Tool>
        }
      />
      <Route
        path="/app/papers/:id"
        element={
          <Tool>
            <Workspace />
          </Tool>
        }
      />
      <Route
        path="/app/images/:id"
        element={
          <Tool>
            <ImageResult />
          </Tool>
        }
      />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
