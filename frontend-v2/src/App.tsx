import AppRoutes from "./AppRoutes";

// The router is supplied by the caller: BrowserRouter in main.tsx,
// StaticRouter in entry-server.tsx, MemoryRouter in tests.
export default function App() {
  return <AppRoutes />;
}
