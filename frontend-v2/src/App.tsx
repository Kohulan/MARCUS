import AppRoutes from "./AppRoutes";
import Footer from "./ui/Footer";
import GlassFilter from "./ui/GlassFilter";
import Header from "./ui/Header";
import { ToastHost, ToastProvider } from "./ui/Toasts";

// The app frame: the glass refraction filter (once), then one drawing sheet around the
// header, the page and the footer, and the toast host. The router is supplied by the
// caller: BrowserRouter in main.tsx, StaticRouter in entry-server.tsx, MemoryRouter in tests.
export default function App() {
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
