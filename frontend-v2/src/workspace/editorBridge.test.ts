// The Ketcher frame protocol: only same-origin messages from the expected window, of an
// exact shape, get through, in both directions.
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  fromFrame,
  fromParent,
  listenToFrame,
  listenToParent,
  postToFrame,
  postToParent,
  type FrameMessage,
} from "./editorBridge";

const ORIGIN = window.location.origin;

function frameWindow(): Window {
  const iframe = document.createElement("iframe");
  iframe.src = "/ketcher/"; // same origin (a frame without src is about:blank, origin "null")
  document.body.append(iframe);
  return iframe.contentWindow as Window;
}

function message(data: unknown, source: Window | null, origin = ORIGIN): MessageEvent {
  return new MessageEvent("message", { data, origin, source });
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("fromFrame (the app reads the frame)", () => {
  it("reads the four frame messages", () => {
    const frame = frameWindow();
    expect(fromFrame(message({ type: "marcus:ready" }, frame), frame)).toEqual({
      type: "marcus:ready",
    });
    expect(fromFrame(message({ type: "marcus:cancel" }, frame), frame)).toEqual({
      type: "marcus:cancel",
    });
    expect(fromFrame(message({ type: "marcus:unfocus" }, frame), frame)).toEqual({
      type: "marcus:unfocus",
    });
    expect(
      fromFrame(message({ type: "marcus:save", molfile: "M", smiles: "CCO" }, frame), frame),
    ).toEqual({ type: "marcus:save", molfile: "M", smiles: "CCO" });
  });

  it("ignores a message from another origin", () => {
    const frame = frameWindow();
    const save = { type: "marcus:save", molfile: "M", smiles: "CCO" };
    expect(fromFrame(message(save, frame, "https://evil.example"), frame)).toBeNull();
    expect(fromFrame(message(save, frame, "null"), frame)).toBeNull();
  });

  it("ignores a same-origin message from a window other than the frame", () => {
    const frame = frameWindow();
    const other = frameWindow();
    const save = { type: "marcus:save", molfile: "M", smiles: "CCO" };
    expect(fromFrame(message(save, other), frame)).toBeNull();
    expect(fromFrame(message(save, window), frame)).toBeNull();
    expect(fromFrame(message(save, null), frame)).toBeNull();
  });

  it("ignores everything when there is no frame yet", () => {
    expect(fromFrame(message({ type: "marcus:ready" }, null), null)).toBeNull();
  });

  it("ignores a message with an unknown type", () => {
    const frame = frameWindow();
    expect(fromFrame(message({ type: "marcus:load" }, frame), frame)).toBeNull();
    expect(fromFrame(message({ type: "marcus:savex" }, frame), frame)).toBeNull();
    expect(fromFrame(message({ type: "ketcher:ready" }, frame), frame)).toBeNull();
  });

  it("ignores a message of any other shape", () => {
    const frame = frameWindow();
    const bad: unknown[] = [
      null,
      undefined,
      "marcus:ready",
      42,
      ["marcus:ready"],
      {},
      { type: "marcus:ready", extra: 1 },
      { type: "marcus:save", smiles: "CCO" },
      { type: "marcus:save", molfile: "M" },
      { type: "marcus:save", molfile: null, smiles: "CCO" },
      { type: "marcus:save", molfile: "M", smiles: 5 },
      { type: "marcus:save", molfile: "M", smiles: "CCO", note: "x" },
      { type: "marcus:cancel", reason: "x" },
    ];
    for (const data of bad) expect(fromFrame(message(data, frame), frame)).toBeNull();
  });
});

describe("listenToFrame", () => {
  it("resolves marcus:save from the frame with its molfile and SMILES", async () => {
    const frame = frameWindow();
    const got = new Promise<FrameMessage>((resolve) => {
      listenToFrame(() => frame, resolve);
    });
    window.dispatchEvent(message({ type: "marcus:save", molfile: "M", smiles: "CCO" }, frame));
    await expect(got).resolves.toEqual({
      type: "marcus:save",
      molfile: "M",
      smiles: "CCO",
    });
  });

  it("drops what the checks refuse, and stops after the cleanup", () => {
    const frame = frameWindow();
    const other = frameWindow();
    const seen = vi.fn();
    const stop = listenToFrame(() => frame, seen);
    window.dispatchEvent(message({ type: "marcus:ready" }, other));
    window.dispatchEvent(message({ type: "marcus:ready" }, frame, "https://evil.example"));
    window.dispatchEvent(message({ type: "marcus:nope" }, frame));
    expect(seen).not.toHaveBeenCalled();
    stop();
    window.dispatchEvent(message({ type: "marcus:ready" }, frame));
    expect(seen).not.toHaveBeenCalled();
  });
});

describe("postToFrame", () => {
  it("posts marcus:load with the app's own origin as the target, never *", () => {
    const frame = frameWindow();
    const post = vi.spyOn(frame, "postMessage").mockImplementation(() => {});
    postToFrame(frame, { molfile: null, smiles: "CCO" });
    expect(post).toHaveBeenCalledWith(
      { type: "marcus:load", molfile: null, smiles: "CCO" },
      ORIGIN,
    );
  });
});

describe("fromParent (the frame reads the app)", () => {
  it("reads marcus:load from the parent window", () => {
    const self = frameWindow();
    const load = { type: "marcus:load", molfile: "M", smiles: null };
    expect(fromParent(message(load, self.parent), self)).toEqual(load);
    const both = { type: "marcus:load", molfile: null, smiles: null };
    expect(fromParent(message(both, self.parent), self)).toEqual(both);
  });

  it("ignores another origin, another window, and any other shape", () => {
    const self = frameWindow();
    const other = frameWindow();
    const load = { type: "marcus:load", molfile: "M", smiles: "CCO" };
    expect(fromParent(message(load, self.parent, "https://evil.example"), self)).toBeNull();
    expect(fromParent(message(load, other), self)).toBeNull();
    expect(fromParent(message(load, self), self)).toBeNull();
    expect(
      fromParent(message({ type: "marcus:save", molfile: "M", smiles: "C" }, self.parent), self),
    ).toBeNull();
    expect(
      fromParent(message({ type: "marcus:load", molfile: 1, smiles: null }, self.parent), self),
    ).toBeNull();
    expect(
      fromParent(message({ type: "marcus:load", molfile: "M" }, self.parent), self),
    ).toBeNull();
  });

  it("ignores everything in a page that is not framed", () => {
    // the top window is its own parent
    const load = { type: "marcus:load", molfile: "M", smiles: "CCO" };
    expect(fromParent(message(load, window), window)).toBeNull();
  });

  it("listenToParent hands over loads and stops after the cleanup", () => {
    const self = frameWindow();
    const seen = vi.fn();
    const stop = listenToParent(seen, self);
    const load = { type: "marcus:load", molfile: "M", smiles: "CCO" };
    self.dispatchEvent(message(load, self.parent));
    self.dispatchEvent(message({ type: "marcus:ready" }, self.parent));
    expect(seen).toHaveBeenCalledTimes(1);
    expect(seen).toHaveBeenCalledWith(load);
    stop();
    self.dispatchEvent(message(load, self.parent));
    expect(seen).toHaveBeenCalledTimes(1);
  });

  it("postToParent targets the frame's own origin, never *", () => {
    const self = frameWindow();
    const post = vi.spyOn(self.parent, "postMessage").mockImplementation(() => {});
    postToParent({ type: "marcus:save", molfile: "M", smiles: "CCO" }, self);
    expect(post).toHaveBeenCalledWith(
      { type: "marcus:save", molfile: "M", smiles: "CCO" },
      self.location.origin,
    );
  });
});
