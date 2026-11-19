import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { DragEvent } from "react";
import { useNavigate } from "react-router-dom";
import { dropHandOff, fileKind, handOff, MAX_BYTES } from "../tool/files";
import { mediaMatches, subscribeMedia } from "../ui/motion";

// The landing's drop zone: an empty benzene ring drawn in dashes, a structure not read yet.
// Hover or focus draws its double bonds; a file dragged over turns it orange and runs the
// dashes; a checked PDF closes the ring in green with alternating double bonds (resonance)
// while the tool opens and uploads it; a refused file strikes it through. Below 1024 px the
// tool cannot run, so the zone only says "Desktop screen needed" (CSS) and takes no file.
//
// One upload path: the PDF is checked here with the tool's own rules (tool/files.ts), kept in
// memory (handOff), and /app opens with only its token in the router state; the tool home
// takes it once and uploads it as if it had been dropped there.

export const NOT_PDF = "That file is not a PDF";
export const TOO_BIG = "That PDF is larger than 20 MB";
/** The tool's own words for an upload that could not start (tool/ToolHome.tsx). */
export const NO_CONNECTION = "The upload did not reach the server. Check your connection.";

const NARROW = "(max-width: 1023.98px)";
const subscribeNarrow = (onChange: () => void) => subscribeMedia(NARROW, onChange);

/** The tool's chunks, so the ring shows the upload starting rather than a blank page. */
const loadTool = () => Promise.all([import("../tool/ToolHome"), import("../api/QueryProvider")]);

// `n` counts refusals, so the same refusal twice is announced twice (a new text node).
type State = { kind: "idle" | "drag" } | { kind: "done" | "error"; text: string; n: number };

const hasFiles = (e: DragEvent<HTMLElement>) => e.dataTransfer.types.includes("Files");

export default function RingDrop() {
  const navigate = useNavigate();
  const input = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<State>({ kind: "idle" });
  // Wide on the server and while hydrating; the pre-rendered page has its CSS for both.
  const narrow = useSyncExternalStore(
    subscribeNarrow,
    () => mediaMatches(NARROW) ?? false,
    () => false,
  );
  const busy = state.kind === "done";
  const alive = useRef(true);

  // A file dropped beside the ring would make the browser leave the page to show it.
  useEffect(() => {
    const keep = (e: globalThis.DragEvent) => {
      if (e.dataTransfer?.types.includes("Files")) e.preventDefault();
    };
    alive.current = true;
    window.addEventListener("dragover", keep);
    window.addEventListener("drop", keep);
    return () => {
      alive.current = false; // left the landing while the tool loaded: stay where you went
      window.removeEventListener("dragover", keep);
      window.removeEventListener("drop", keep);
    };
  }, []);

  const refuse = (text: string) =>
    setState((prev) => ({ kind: "error", text, n: ("n" in prev ? prev.n : 0) + 1 }));

  /** The first PDF among the files (or the first file, to say why it is refused). */
  function take(files: ArrayLike<File> | null | undefined) {
    const list = files ? Array.from(files) : [];
    const file = list.find((f) => fileKind(f) === "pdf") ?? list[0];
    if (!file) return setState({ kind: "idle" });
    if (fileKind(file) !== "pdf") return refuse(NOT_PDF);
    if (file.size > MAX_BYTES) return refuse(TOO_BIG);
    setState({ kind: "done", text: `Uploading ${file.name}…`, n: 0 });
    const token = handOff(file);
    const fail = () => {
      dropHandOff(token);
      if (alive.current) refuse(NO_CONNECTION);
    };
    loadTool().then(() => {
      if (!alive.current) return dropHandOff(token); // left the landing meanwhile: stay there
      try {
        navigate("/app", { state: { handOff: token } });
      } catch {
        fail();
      }
    }, fail);
  }

  function onDragOver(e: DragEvent<HTMLButtonElement>) {
    if (!hasFiles(e)) return; // text or a link: not a drop for this zone
    e.preventDefault();
    if (narrow || busy) {
      e.dataTransfer.dropEffect = "none";
      return;
    }
    e.dataTransfer.dropEffect = "copy";
    if (state.kind !== "drag") setState({ kind: "drag" });
  }

  function onDragLeave(e: DragEvent<HTMLButtonElement>) {
    if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
    if (state.kind === "drag") setState({ kind: "idle" });
  }

  function onDrop(e: DragEvent<HTMLButtonElement>) {
    if (!hasFiles(e)) return;
    e.preventDefault();
    if (narrow || busy) return;
    take(e.dataTransfer.files);
  }

  const cls = state.kind === "idle" ? "dz" : `dz is-${state.kind}`;
  const message = state.kind === "done" || state.kind === "error" ? state.text : "";

  return (
    <>
      <button
        type="button"
        className={cls}
        aria-disabled={narrow || busy ? "true" : undefined}
        onClick={() => {
          if (!narrow && !busy) input.current?.click();
        }}
        onDragEnter={onDragOver}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        <svg className="dz__ring" viewBox="0 0 120 132" aria-hidden="true" focusable="false">
          <polygon className="dz__hex" points="60,8 110.2,37 110.2,95 60,124 9.8,95 9.8,37" />
          <g className="dz__bonds--a">
            <path className="dz__bond" pathLength={1} d="M65.7 22.3 95 39.2" />
            <path className="dz__bond" pathLength={1} d="M95 92.8 65.7 109.7" />
            <path className="dz__bond" pathLength={1} d="M19.3 82.9V49.1" />
          </g>
          <g className="dz__bonds--b">
            <path className="dz__bond" pathLength={1} d="M100.7 49.1v33.8" />
            <path className="dz__bond" pathLength={1} d="M54.3 109.7 25 92.8" />
            <path className="dz__bond" pathLength={1} d="M25 39.2 54.3 22.3" />
          </g>
          <g className="dz__mark dz__mark--up" transform="translate(44 49) scale(1.35)">
            <g className="dz__arrow">
              <path d="M12 15V4" />
              <path d="M7.5 8.5 12 4l4.5 4.5" />
            </g>
            <path d="M4 15v3.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V15" />
          </g>
          <g className="dz__mark dz__mark--desk" transform="translate(44 50) scale(1.35)">
            <rect x="3" y="4" width="18" height="12" rx="1.5" />
            <path d="M8.5 20h7M12 16v4" />
          </g>
          <path className="dz__strike" d="M9.8 95 110.2 37" />
        </svg>
        <span className="dz__title dz__title--idle">
          Drop a PDF here or <span className="dz__browse">browse</span>
        </span>{" "}
        <span className="dz__title dz__title--desk">Desktop screen needed</span>{" "}
        {message && <span className="dz__title dz__title--said">{message}</span>}{" "}
        <span className="dz__hint dz__hint--size">PDF up to 20 MB</span>
      </button>
      {/* Said once when it happens; the button's own text changes silently. */}
      <p className="visually-hidden" role="status">
        {state.kind === "done" ? state.text : ""}
      </p>
      <p className="visually-hidden" role="alert">
        {state.kind === "error" ? <span key={state.n}>{state.text}</span> : null}
      </p>
      <input
        ref={input}
        type="file"
        className="visually-hidden"
        accept="application/pdf,.pdf"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(e) => {
          take(e.target.files);
          e.target.value = ""; // the same file can be chosen again
        }}
      />
    </>
  );
}
