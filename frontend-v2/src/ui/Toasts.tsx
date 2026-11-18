import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import "./ui.css";

export type ToastTone = "info" | "error";
type Toast = { id: number; msg: string; tone: ToastTone };
type Push = (msg: string, tone?: ToastTone) => void;

const SHOW_MS = { info: 4000, error: 7000 } as const;
const MAX_SHOWN = 3;

const PushContext = createContext<Push>(() => {});
const ListContext = createContext<Toast[]>([]);

/** Holds the toasts of the app; <ToastHost/> shows them. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Set<ReturnType<typeof setTimeout>>());

  useEffect(() => {
    const pending = timers.current;
    return () => {
      for (const t of pending) clearTimeout(t);
      pending.clear();
    };
  }, []);

  const push = useCallback<Push>((msg, tone = "info") => {
    const id = nextId.current++;
    setToasts((list) => [...list, { id, msg, tone }].slice(-MAX_SHOWN));
    const timer = setTimeout(() => {
      timers.current.delete(timer);
      setToasts((list) => list.filter((t) => t.id !== id));
    }, SHOW_MS[tone]);
    timers.current.add(timer);
  }, []);

  return (
    <PushContext.Provider value={push}>
      <ListContext.Provider value={toasts}>{children}</ListContext.Provider>
    </PushContext.Provider>
  );
}

/** Shows a short message: `toast("SMILES copied")`, `toast("Upload failed", "error")`. */
export function useToast(): Push {
  return useContext(PushContext);
}

/** The live region the toasts appear in (bottom of the window). Rendered once, by App. */
export function ToastHost() {
  const toasts = useContext(ListContext);
  return (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map((t) => (
        <p key={t.id} className={t.tone === "error" ? "toast toast--error" : "toast"}>
          {t.msg}
        </p>
      ))}
    </div>
  );
}
