// The Ketcher editor page, served at /ketcher/ under its own CSP and framed by the tool's
// structure editor (src/workspace/Editor.tsx). Ketcher 3.18.0 with the standalone
// (in-browser Indigo) struct service: the binaryWasm entry starts the Indigo worker from its
// own file and loads a separate .wasm (no base64 WebAssembly, no Blob worker), both served
// from /ketcher/assets/.
//
// Talks to the tool only through src/workspace/editorBridge.ts: posts marcus:ready once
// Ketcher is up, loads the structure of marcus:load (molfile first, SMILES as the fallback),
// and posts marcus:save (molfile and SMILES of the drawing) or marcus:cancel from its bar.
// Every message from the tool is checked for origin, source (the parent window) and shape.
import { useEffect, useState, useSyncExternalStore } from "react";
import { createRoot } from "react-dom/client";
import type { Ketcher } from "ketcher-core";
import { Editor } from "ketcher-react";
import { StandaloneStructServiceProvider } from "ketcher-standalone/dist/binaryWasm";
import { listenToParent, postToParent, type LoadMessage } from "../src/workspace/editorBridge";
import "ketcher-react/dist/index.css";
import "./ketcher.css";

declare global {
  interface Window {
    ketcher?: Ketcher;
  }
}

// The Ketcher instance, once onInit ran (a tiny store, so the bar can wait for it).
let instance: Ketcher | null = null;
const listeners = new Set<() => void>();
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};
const getInstance = () => instance;

function onInit(ketcher: Ketcher) {
  instance = ketcher;
  window.ketcher = ketcher; // for e2e checks
  for (const listener of listeners) listener();
}

// One element, created once: the bar's state changes never re-render Ketcher.
const structServiceProvider = new StandaloneStructServiceProvider();
const ketcherEditor = (
  <Editor
    staticResourcesUrl="/ketcher/"
    structServiceProvider={structServiceProvider}
    errorHandler={(message) => console.error("Ketcher:", message)}
    disableMacromoleculesEditor
    onInit={onInit}
  />
);

/** Molfile first; the SMILES when the molfile is missing or Ketcher cannot read it. */
async function load(ketcher: Ketcher, message: LoadMessage): Promise<boolean> {
  const sources = [message.molfile, message.smiles].filter(
    (s): s is string => s !== null && s.trim() !== "",
  );
  if (sources.length === 0) return true; // nothing stored yet: start from an empty canvas
  for (const source of sources) {
    try {
      await ketcher.setMolecule(source);
      return true;
    } catch {
      // try the next one
    }
  }
  return false;
}

function App() {
  const ketcher = useSyncExternalStore(subscribe, getInstance);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  // Listen first, then say ready, so the answering marcus:load is never missed.
  useEffect(() => {
    if (!ketcher) return;
    let latest = 0;
    const stop = listenToParent((message) => {
      const run = ++latest;
      setLoading(true);
      setNote(null);
      void load(ketcher, message).then((ok) => {
        if (run !== latest) return; // a newer load is under way
        setLoading(false);
        if (!ok) setNote("Could not open the stored structure.");
      });
    });
    postToParent({ type: "marcus:ready" });
    return stop;
  }, [ketcher]);

  async function save() {
    if (!ketcher) return;
    setSaving(true);
    setNote(null);
    try {
      const molfile = await ketcher.getMolfile();
      const smiles = await ketcher.getSmiles();
      postToParent({ type: "marcus:save", molfile, smiles });
    } catch {
      setNote("Could not read the drawing.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="host">{ketcherEditor}</div>
      <div className="bar">
        <p className="bar__note" role="status">
          {note}
        </p>
        <div className="bar__actions">
          <button
            type="button"
            className="pill pill--clear"
            onClick={() => postToParent({ type: "marcus:cancel" })}
          >
            Cancel
          </button>
          <button
            type="button"
            className="pill pill--green"
            disabled={!ketcher || loading || saving}
            onClick={() => void save()}
          >
            Save drawing
          </button>
        </div>
      </div>
    </>
  );
}

const root = document.getElementById("root");
if (!root) throw new Error("#root missing");

createRoot(root).render(<App />);
