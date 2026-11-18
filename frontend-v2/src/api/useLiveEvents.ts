import { useCallback, useEffect, useRef, useState } from "react";
import { BASE } from "./client";

export type LiveMode = "connecting" | "live" | "polling" | "ended";

const POLL_MS = 2000;
const BACKOFF_MS = [5000, 10000, 20000, 40000]; // then every 60 s
const BACKOFF_LAST_MS = 60000;
const HIDDEN_CLOSE_MS = 60000;

/**
 * Live updates of a paper or image job (wire format: backend-v2 api/routes/events.py).
 * `onEvent` is a hint to refetch; the API stays the source of truth.
 *
 * - `snapshot` (named) and unnamed `data:` frames → onEvent, mode "live". A snapshot hands
 *   onEvent its parsed data (a page may skip a refetch it has just made).
 * - `end` (named) → onEvent, close, every timer stops, mode "ended". Named events reach only
 *   addEventListener, never onmessage.
 * - `error` (the native error and the named `error` frame both arrive as "error") → mode
 *   "polling", onEvent every 2 s. readyState CLOSED (an HTTP error such as the 429 for too
 *   many streams) → a new EventSource after 5, 10, 20, 40, then every 60 s; CONNECTING → the
 *   browser reconnects itself. `open` stops polling and resets the back-off.
 * - No inactivity timeout: the server's `: ping` comments never reach JS.
 * - A tab hidden for more than 60 s closes its stream and stops polling (each open stream
 *   holds an HTTP/1.1 connection); shown again, it reopens and calls onEvent once.
 * - reconnect() opens a new stream when the mode is "ended" (after a prediction or page
 *   retry has reopened a finished paper or image job).
 */
export function useLiveEvents(
  kind: "paper" | "image",
  id: string,
  onEvent: (snapshot?: unknown) => void,
): { mode: LiveMode; reconnect: () => void } {
  const [mode, setModeState] = useState<LiveMode>("connecting");
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  // reconnect() is stable; it reaches the current effect's opener through this ref
  const reopenEnded = useRef<() => void>(() => undefined);

  useEffect(() => {
    if (typeof EventSource === "undefined") return; // never during the pre-render
    const url = `${BASE}/${kind === "paper" ? "papers" : "images"}/${encodeURIComponent(id)}/events`;

    let es: EventSource | null = null;
    let current: LiveMode = "connecting";
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    let reopenTimer: ReturnType<typeof setTimeout> | null = null;
    let hiddenTimer: ReturnType<typeof setTimeout> | null = null;
    let backoff = 0;
    let suspended = false; // closed because the tab was hidden too long

    const fire = () => onEventRef.current();
    const parse = (data: unknown): unknown => {
      try {
        return typeof data === "string" ? (JSON.parse(data) as unknown) : undefined;
      } catch {
        return undefined;
      }
    };
    const setMode = (next: LiveMode) => {
      current = next;
      setModeState(next);
    };
    const stopPolling = () => {
      if (pollTimer !== null) clearInterval(pollTimer);
      pollTimer = null;
    };
    const startPolling = () => {
      if (pollTimer === null) pollTimer = setInterval(fire, POLL_MS);
    };
    const cancelReopen = () => {
      if (reopenTimer !== null) clearTimeout(reopenTimer);
      reopenTimer = null;
    };
    const closeStream = () => {
      es?.close();
      es = null;
    };
    const stopAll = () => {
      closeStream();
      stopPolling();
      cancelReopen();
    };

    const open = () => {
      closeStream();
      cancelReopen();
      const source = new EventSource(url);
      es = source;
      // Every handler ignores a stream that has since been replaced or closed.
      const mine =
        <E,>(fn: (e: E) => void) =>
        (e: E) => {
          if (es === source) fn(e);
        };
      const live = (snapshot?: unknown) => {
        stopPolling();
        backoff = 0;
        setMode("live");
        onEventRef.current(snapshot);
      };
      source.addEventListener(
        "snapshot",
        mine((e: Event) => live(parse((e as MessageEvent).data) ?? null)),
      );
      source.onmessage = mine(() => live());
      source.addEventListener(
        "open",
        mine(() => {
          stopPolling();
          backoff = 0;
          setMode("live");
        }),
      );
      source.addEventListener(
        "end",
        mine(() => {
          stopAll();
          setMode("ended");
          fire();
        }),
      );
      source.addEventListener(
        "error",
        mine(() => {
          setMode("polling");
          startPolling();
          if (source.readyState === EventSource.CLOSED && reopenTimer === null) {
            const delay = BACKOFF_MS[backoff] ?? BACKOFF_LAST_MS;
            backoff += 1;
            reopenTimer = setTimeout(() => {
              reopenTimer = null;
              open();
            }, delay);
          }
        }),
      );
    };

    const onVisibility = () => {
      if (document.hidden) {
        if (current === "ended" || hiddenTimer !== null) return;
        hiddenTimer = setTimeout(() => {
          hiddenTimer = null;
          if (current === "ended") return;
          suspended = true;
          stopAll();
        }, HIDDEN_CLOSE_MS);
        return;
      }
      if (hiddenTimer !== null) clearTimeout(hiddenTimer);
      hiddenTimer = null;
      if (suspended) {
        suspended = false;
        backoff = 0;
        setMode("connecting");
        open();
        fire();
      }
    };

    reopenEnded.current = () => {
      if (current !== "ended") return;
      backoff = 0;
      setMode("connecting");
      open();
    };

    setMode("connecting");
    open();
    document.addEventListener("visibilitychange", onVisibility);
    if (document.hidden) onVisibility();

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      if (hiddenTimer !== null) clearTimeout(hiddenTimer);
      stopAll();
      reopenEnded.current = () => undefined;
    };
  }, [kind, id]);

  const reconnect = useCallback(() => reopenEnded.current(), []);
  return { mode, reconnect };
}
