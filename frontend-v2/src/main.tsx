import { StrictMode } from "react";
import { createRoot, hydrateRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles/tokens.css";
import "./styles/fonts.css";
import "./styles/base.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("#root is missing from index.html");
}

const tree = (
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>
);

// Pre-rendered pages (/, /about, /privacy, /disclaimer, 404) arrive with
// markup and are hydrated; the /app shell arrives empty and is rendered.
if (container.firstElementChild) {
  hydrateRoot(container, tree);
} else {
  createRoot(container).render(tree);
}
