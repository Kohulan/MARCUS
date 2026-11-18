// The message protocol between the tool and the Ketcher frame (/ketcher/), used on both
// sides (ketcher/main.tsx imports this file too, so there is one definition).
//
// The frame is same-origin (it needs `allow-same-origin` for its own CSP and storage), so
// the origin check alone cannot tell the app from the frame or from any other same-origin
// window: every handler also checks that `event.source` is the one expected window. Data
// that arrives is never trusted: anything that is not exactly one of the shapes below is
// dropped. Posts always name the page's own origin as the target, never "*".
//
//   app → frame   {type: "marcus:load", molfile: string | null, smiles: string | null}
//   frame → app   {type: "marcus:ready"}
//                 {type: "marcus:save", molfile: string, smiles: string}
//                 {type: "marcus:cancel"}

export type LoadMessage = {
  type: "marcus:load";
  molfile: string | null;
  smiles: string | null;
};

export type FrameMessage =
  | { type: "marcus:ready" }
  | { type: "marcus:save"; molfile: string; smiles: string }
  | { type: "marcus:cancel" };

/** A plain object with exactly these keys (no more, no fewer). */
function exactly(data: unknown, keysWanted: string[]): data is Record<string, unknown> {
  if (typeof data !== "object" || data === null || Array.isArray(data)) return false;
  const got = Object.keys(data);
  return got.length === keysWanted.length && keysWanted.every((k) => got.includes(k));
}

const isStringOrNull = (v: unknown): v is string | null => v === null || typeof v === "string";

function readFrameData(data: unknown): FrameMessage | null {
  if (exactly(data, ["type"])) {
    if (data.type === "marcus:ready") return { type: "marcus:ready" };
    if (data.type === "marcus:cancel") return { type: "marcus:cancel" };
    return null;
  }
  if (
    exactly(data, ["type", "molfile", "smiles"]) &&
    data.type === "marcus:save" &&
    typeof data.molfile === "string" &&
    typeof data.smiles === "string"
  ) {
    return { type: "marcus:save", molfile: data.molfile, smiles: data.smiles };
  }
  return null;
}

function readLoadData(data: unknown): LoadMessage | null {
  if (
    exactly(data, ["type", "molfile", "smiles"]) &&
    data.type === "marcus:load" &&
    isStringOrNull(data.molfile) &&
    isStringOrNull(data.smiles)
  ) {
    return { type: "marcus:load", molfile: data.molfile, smiles: data.smiles };
  }
  return null;
}

/** Same origin as `self`, and never the opaque "null" origin. */
function sameOrigin(event: MessageEvent, self: Window): boolean {
  const origin = self.location.origin;
  return origin !== "null" && event.origin === origin;
}

// ---- app side ---------------------------------------------------------------------------

/** A frame message, or null when it is not from `frame`, not same-origin, or misshapen. */
export function fromFrame(event: MessageEvent, frame: Window | null): FrameMessage | null {
  if (frame === null || event.source !== frame || !sameOrigin(event, window)) return null;
  return readFrameData(event.data);
}

/**
 * Hands every valid message of the frame to `onMessage`. `getFrame` is read per message
 * (the iframe's window exists only once it is mounted). Returns the cleanup.
 */
export function listenToFrame(
  getFrame: () => Window | null,
  onMessage: (message: FrameMessage) => void,
): () => void {
  const handler = (event: MessageEvent) => {
    const message = fromFrame(event, getFrame());
    if (message) onMessage(message);
  };
  window.addEventListener("message", handler);
  return () => window.removeEventListener("message", handler);
}

/** Sends the structure to load into the editor. */
export function postToFrame(
  frame: Window,
  structure: { molfile: string | null; smiles: string | null },
): void {
  const message: LoadMessage = {
    type: "marcus:load",
    molfile: structure.molfile,
    smiles: structure.smiles,
  };
  frame.postMessage(message, window.location.origin);
}

// ---- frame side -------------------------------------------------------------------------

/** A load message, or null when it is not from `self`'s parent, not same-origin, or misshapen. */
export function fromParent(event: MessageEvent, self: Window = window): LoadMessage | null {
  const parent = self.parent;
  if (parent === self || event.source !== parent || !sameOrigin(event, self)) return null;
  return readLoadData(event.data);
}

/** Hands every valid load message of the parent to `onLoad`. Returns the cleanup. */
export function listenToParent(
  onLoad: (message: LoadMessage) => void,
  self: Window = window,
): () => void {
  const handler = (event: MessageEvent) => {
    const message = fromParent(event, self);
    if (message) onLoad(message);
  };
  self.addEventListener("message", handler);
  return () => self.removeEventListener("message", handler);
}

/** Posts to the parent (the tool); a page that is not framed posts nothing. */
export function postToParent(message: FrameMessage, self: Window = window): void {
  if (self.parent === self) return;
  self.parent.postMessage(message, self.location.origin);
}
