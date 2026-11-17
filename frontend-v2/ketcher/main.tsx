// The Ketcher editor page, served at /ketcher/ under its own CSP and framed by the tool.
// Bare Ketcher 3.18.0 with the standalone (in-browser Indigo) struct service. The
// binaryWasm entry starts the Indigo worker from its own file and loads a separate .wasm
// (no base64 WebAssembly, no Blob worker), both served from /ketcher/assets/.
import { createRoot } from "react-dom/client";
import type { Ketcher } from "ketcher-core";
import { Editor } from "ketcher-react";
import { StandaloneStructServiceProvider } from "ketcher-standalone/dist/binaryWasm";
import "ketcher-react/dist/index.css";
import "./ketcher.css";

declare global {
  interface Window {
    ketcher?: Ketcher;
  }
}

const structServiceProvider = new StandaloneStructServiceProvider();

function onInit(ketcher: Ketcher) {
  window.ketcher = ketcher;
  // Same-origin parent only (the tool at /app); the target origin is never "*".
  window.parent.postMessage({ type: "marcus:ready" }, window.location.origin);
}

const root = document.getElementById("root");
if (!root) throw new Error("#root missing");

createRoot(root).render(
  <Editor
    staticResourcesUrl="/ketcher/"
    structServiceProvider={structServiceProvider}
    errorHandler={(message) => console.error("Ketcher:", message)}
    disableMacromoleculesEditor
    onInit={onInit}
  />,
);
