import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useLiveEvents } from "./useLiveEvents";

// A fake EventSource that, like the real one, delivers named events only to
// addEventListener and unnamed `data:` frames to onmessage (and "message" listeners).
class FakeEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  static all: FakeEventSource[] = [];

  readonly url: string;
  readyState = FakeEventSource.CONNECTING;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onopen: ((ev: Event) => void) | null = null;
  closed = false;
  private listeners = new Map<string, Set<(ev: Event) => void>>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.all.push(this);
  }

  addEventListener(type: string, fn: (ev: Event) => void) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(fn);
  }

  removeEventListener(type: string, fn: (ev: Event) => void) {
    this.listeners.get(type)?.delete(fn);
  }

  close() {
    this.closed = true;
    this.readyState = FakeEventSource.CLOSED;
  }

  /** Dispatch like the browser: named events reach only addEventListener. */
  emit(type: string, data = "{}") {
    const ev = type === "open" || type === "error" ? new Event(type) : new MessageEvent(type, { data });
    for (const fn of this.listeners.get(type) ?? []) fn(ev);
    if (type === "message") this.onmessage?.(ev as MessageEvent);
    if (type === "error") this.onerror?.(ev);
    if (type === "open") this.onopen?.(ev);
  }

  open() {
    this.readyState = FakeEventSource.OPEN;
    this.emit("open");
  }

  fail(state: number) {
    this.readyState = state;
    this.emit("error");
  }
}

function latest(): FakeEventSource {
  const es = FakeEventSource.all.at(-1);
  if (!es) throw new Error("no EventSource");
  return es;
}

let hidden = false;

function setHidden(value: boolean) {
  hidden = value;
  document.dispatchEvent(new Event("visibilitychange"));
}

beforeEach(() => {
  vi.useFakeTimers();
  FakeEventSource.all = [];
  hidden = false;
  vi.stubGlobal("EventSource", FakeEventSource);
  Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => (hidden ? "hidden" : "visible"),
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function setup(kind: "paper" | "image" = "paper") {
  const onEvent = vi.fn();
  const hook = renderHook(() => useLiveEvents(kind, "p1", onEvent));
  return { onEvent, hook };
}

describe("useLiveEvents", () => {
  it("opens the paper or image stream", () => {
    setup("paper");
    expect(latest().url).toBe("/api/v2/papers/p1/events");
    setup("image");
    expect(latest().url).toBe("/api/v2/images/p1/events");
  });

  it("a snapshot and a message each call onEvent and set live", () => {
    const { onEvent, hook } = setup();
    expect(hook.result.current.mode).toBe("connecting");
    act(() => latest().open());
    act(() => latest().emit("snapshot", '{"status":"processing"}'));
    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(hook.result.current.mode).toBe("live");
    act(() => latest().emit("message", '{"status":"done"}'));
    expect(onEvent).toHaveBeenCalledTimes(2);
  });

  it("error while CONNECTING polls every 2000 ms; open stops polling", () => {
    const { onEvent, hook } = setup();
    act(() => latest().fail(FakeEventSource.CONNECTING));
    expect(hook.result.current.mode).toBe("polling");
    act(() => vi.advanceTimersByTime(2000));
    expect(onEvent).toHaveBeenCalledTimes(1);
    act(() => vi.advanceTimersByTime(4000));
    expect(onEvent).toHaveBeenCalledTimes(3);
    // the browser reconnects itself: no new EventSource
    expect(FakeEventSource.all).toHaveLength(1);
    act(() => latest().open());
    act(() => vi.advanceTimersByTime(10000));
    expect(onEvent).toHaveBeenCalledTimes(3);
    expect(hook.result.current.mode).toBe("live");
  });

  it("the named error frame (Redis down) also switches to polling", () => {
    const { onEvent, hook } = setup();
    act(() => latest().open());
    act(() => latest().emit("error"));
    expect(hook.result.current.mode).toBe("polling");
    act(() => vi.advanceTimersByTime(2000));
    expect(onEvent).toHaveBeenCalledTimes(1);
  });

  it("error while CLOSED opens a new EventSource after 5000 ms, then backs off", () => {
    setup();
    const first = latest();
    act(() => first.fail(FakeEventSource.CLOSED));
    act(() => vi.advanceTimersByTime(4999));
    expect(FakeEventSource.all).toHaveLength(1);
    act(() => vi.advanceTimersByTime(1));
    expect(FakeEventSource.all).toHaveLength(2);
    // refused again (429): the next try waits 10 s
    act(() => latest().fail(FakeEventSource.CLOSED));
    act(() => vi.advanceTimersByTime(9999));
    expect(FakeEventSource.all).toHaveLength(2);
    act(() => vi.advanceTimersByTime(1));
    expect(FakeEventSource.all).toHaveLength(3);
    // open resets the back-off
    act(() => latest().open());
    act(() => latest().fail(FakeEventSource.CLOSED));
    act(() => vi.advanceTimersByTime(5000));
    expect(FakeEventSource.all).toHaveLength(4);
  });

  it("the back-off goes 5, 10, 20, 40, then every 60 s", () => {
    setup();
    const delays = [5000, 10000, 20000, 40000, 60000, 60000];
    for (const [i, d] of delays.entries()) {
      act(() => latest().fail(FakeEventSource.CLOSED));
      act(() => vi.advanceTimersByTime(d - 1));
      expect(FakeEventSource.all).toHaveLength(i + 1);
      act(() => vi.advanceTimersByTime(1));
      expect(FakeEventSource.all).toHaveLength(i + 2);
    }
  });

  it("end (a named event) calls onEvent, closes, stops timers and sets ended", () => {
    const { onEvent, hook } = setup();
    const es = latest();
    act(() => es.fail(FakeEventSource.CLOSED)); // polling + a pending reopen
    onEvent.mockClear();
    act(() => es.emit("end", '{"status":"done"}'));
    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(es.closed).toBe(true);
    expect(hook.result.current.mode).toBe("ended");
    act(() => vi.advanceTimersByTime(120000));
    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(FakeEventSource.all).toHaveLength(1);
  });

  it("end is handled through addEventListener, not onmessage", () => {
    const { hook } = setup();
    const es = latest();
    // the fake's emit("end") never calls onmessage, as in the browser
    act(() => es.emit("end"));
    expect(hook.result.current.mode).toBe("ended");
  });

  it("reconnect() after end opens a new stream", () => {
    const { hook } = setup();
    act(() => latest().emit("end"));
    expect(FakeEventSource.all).toHaveLength(1);
    act(() => hook.result.current.reconnect());
    expect(FakeEventSource.all).toHaveLength(2);
    expect(hook.result.current.mode).toBe("connecting");
    act(() => latest().emit("snapshot"));
    expect(hook.result.current.mode).toBe("live");
  });

  it("reconnect() while the stream is open does nothing", () => {
    const { hook } = setup();
    act(() => latest().open());
    act(() => hook.result.current.reconnect());
    expect(FakeEventSource.all).toHaveLength(1);
  });

  // A run accepted while the old stream is still open (a re-run right after another one
  // finished): that stream may already have read the paper as done and send `end`. The run's
  // result must still arrive, so the end opens one new stream instead of ending.
  it("reconnect() while open, then end: one new stream (the run is not lost)", () => {
    const { hook, onEvent } = setup();
    act(() => latest().emit("snapshot", '{"status":"processing"}'));
    act(() => hook.result.current.reconnect());
    expect(FakeEventSource.all).toHaveLength(1);
    act(() => latest().emit("end", '{"status":"done"}'));
    expect(FakeEventSource.all).toHaveLength(2);
    expect(FakeEventSource.all[0]!.closed).toBe(true);
    expect(hook.result.current.mode).toBe("connecting");
    expect(onEvent).toHaveBeenCalledTimes(2); // the snapshot, then the end
    act(() => latest().emit("snapshot", '{"status":"processing"}'));
    expect(hook.result.current.mode).toBe("live");
    // That stream's own end is final.
    act(() => latest().emit("end", '{"status":"done"}'));
    expect(FakeEventSource.all).toHaveLength(2);
    expect(hook.result.current.mode).toBe("ended");
  });

  it("reconnect() while connecting, then end: one new stream", () => {
    const { hook } = setup();
    act(() => hook.result.current.reconnect());
    act(() => latest().emit("snapshot", '{"status":"done"}'));
    act(() => latest().emit("end", '{"status":"done"}'));
    expect(FakeEventSource.all).toHaveLength(2);
    expect(hook.result.current.mode).toBe("connecting");
  });

  it("hidden for 61 s closes the stream and polling; visible reopens and calls onEvent once", () => {
    const { onEvent } = setup();
    const es = latest();
    act(() => es.fail(FakeEventSource.CONNECTING)); // polling
    act(() => setHidden(true));
    act(() => vi.advanceTimersByTime(59000));
    expect(es.closed).toBe(false);
    act(() => vi.advanceTimersByTime(2000));
    expect(es.closed).toBe(true);
    onEvent.mockClear();
    act(() => vi.advanceTimersByTime(30000));
    expect(onEvent).not.toHaveBeenCalled(); // no polling while hidden
    act(() => setHidden(false));
    expect(FakeEventSource.all).toHaveLength(2);
    expect(onEvent).toHaveBeenCalledTimes(1);
  });

  it("hidden for less than 60 s keeps the stream", () => {
    setup();
    const es = latest();
    act(() => setHidden(true));
    act(() => vi.advanceTimersByTime(30000));
    act(() => setHidden(false));
    act(() => vi.advanceTimersByTime(60000));
    expect(es.closed).toBe(false);
    expect(FakeEventSource.all).toHaveLength(1);
  });

  it("unmount closes the stream and stops every timer", () => {
    const { onEvent, hook } = setup();
    const es = latest();
    act(() => es.fail(FakeEventSource.CLOSED));
    hook.unmount();
    expect(es.closed).toBe(true);
    act(() => vi.advanceTimersByTime(120000));
    expect(onEvent).not.toHaveBeenCalled();
    expect(FakeEventSource.all).toHaveLength(1);
  });

  it("calls the newest onEvent", () => {
    const first = vi.fn();
    const second = vi.fn();
    const hook = renderHook(({ cb }) => useLiveEvents("paper", "p1", cb), {
      initialProps: { cb: first },
    });
    hook.rerender({ cb: second });
    expect(FakeEventSource.all).toHaveLength(1);
    act(() => latest().emit("snapshot"));
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });
});
