import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "./motion";
import {
  annotateEstimate,
  climb,
  countFrame,
  END_HOLD_MS,
  FILL_MS,
  percentOf,
  spokenValue,
  type Climb,
} from "./progressMotion";
import "./ui.css";

// useLayoutEffect warns on the server; the bar's fill is set before the first paint in the browser.
const useBrowserLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

/** The highest figure so far in this run (progressMotion climb); null stays indeterminate. */
function useClimbing(value: number | null, active: boolean): number | null {
  const [state, setState] = useState<Climb>({ max: value ?? 0, busy: active });
  const next = climb(state, value, active);
  if (next !== state) setState(next); // during render: no extra frame
  return value === null ? null : next.max;
}

/**
 * The printed figure: it counts up to each new value on the fill's curve and time (one
 * requestAnimationFrame loop), never down; it jumps under reduced motion, when it appears,
 * and when a new run starts lower.
 */
function useCountUp(target: number | null, reduce: boolean): number | null {
  const [shown, setShown] = useState(target);
  const at = useRef(target);
  useEffect(() => {
    const from = at.current;
    if (
      target === null ||
      from === null ||
      reduce ||
      target <= from ||
      typeof requestAnimationFrame !== "function"
    ) {
      at.current = target;
      setShown(target);
      return;
    }
    let raf = 0;
    let start: number | null = null;
    const frame = (now: number) => {
      start ??= now;
      const v = countFrame(from, target, now - start, FILL_MS);
      at.current = v;
      setShown(v);
      if (v < target) raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [target, reduce]);
  return shown;
}

/**
 * True while `on`, and for `ms` after it turns off (a finished run stays on its full bar for a
 * moment).
 */
export function useHeldAfter(on: boolean, ms: number): boolean {
  const [held, setHeld] = useState(on);
  if (on && !held) setHeld(true);
  useEffect(() => {
    if (on || !held) return;
    const id = setTimeout(() => setHeld(false), ms);
    return () => clearTimeout(id);
  }, [on, held, ms]);
  return on || held;
}

/** How often the annotate estimate moves on (the fill eases between the steps). */
const ESTIMATE_TICK_MS = 250;

/**
 * An annotate run's figure, which its model does not report: the time-based estimate
 * (progressMotion annotateEstimate, from the moment this page saw the run start) while it
 * runs, 1 for END_HOLD_MS once it has ended, null before a run and after the hold. A caller
 * whose run failed shows no bar, so the 1 is only ever seen for a run that finished.
 */
export function useAnnotateEstimate(running: boolean): number | null {
  const [start, setStart] = useState<number | null>(null);
  const [now, setNow] = useState(0);
  const [was, setWas] = useState(running);
  const held = useHeldAfter(running, END_HOLD_MS);
  if (running !== was) {
    setWas(running);
    if (running) setStart(Date.now()); // a new run, even one inside the last one's hold
  } else if (running && start === null) setStart(Date.now());
  else if (!held && start !== null) setStart(null);

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setNow(Date.now()), ESTIMATE_TICK_MS);
    return () => clearInterval(id);
  }, [running]);

  if (running) return start === null ? 0 : annotateEstimate(Math.max(now, start) - start);
  return held ? 1 : null;
}

/**
 * The one progress bar. Measured (`value` 0 to 1): a square track whose fill eases to each
 * new value (transform: scaleX from the --pb custom property, set through the CSSOM: no style
 * attribute), the percentage printed beside it counting up with the fill (never down, 100
 * only at 1), and a slow sheen on the fill while `active` (none once the work is done or
 * stopped). Unmeasured (`value` null): a calm sliding segment and no number. Reduced motion:
 * no sheen, no slide, no easing, the figure jumps. The bar's spoken value is `valueText`
 * with the percentage; announcing stages is the caller's.
 */
export default function ProgressBar({
  value,
  label,
  valueText = "",
  active = true,
  size = "md",
  estimated = false,
  className,
}: {
  value: number | null;
  /** The bar's accessible name. */
  label: string;
  /** What the bar says besides its percentage: "Reading structures, 10 of 15". */
  valueText?: string;
  /** The work is going on (the sheen); false once it is done or stopped. */
  active?: boolean;
  size?: "md" | "sm";
  /** The value is an estimate (an annotate run): printed "~60%", said "about 60%", until 1. */
  estimated?: boolean;
  className?: string;
}) {
  const reduce = usePrefersReducedMotion();
  const climbed = useClimbing(value, active);
  const counted = useCountUp(climbed, reduce);
  const track = useRef<HTMLDivElement>(null);

  useBrowserLayoutEffect(() => {
    const el = track.current;
    if (!el) return;
    if (climbed === null) el.style.removeProperty("--pb");
    else el.style.setProperty("--pb", String(climbed));
  }, [climbed]);

  const measured = climbed !== null;
  const classes = [
    "pb",
    `pb--${size}`,
    measured ? (active ? "pb--active" : "") : "pb--indeterminate",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");
  const spoken = spokenValue(valueText, climbed, estimated);
  const about = estimated && counted !== null && counted < 1 ? "~" : "";

  return (
    <div className={classes}>
      <div
        ref={track}
        className="pb__track"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={measured ? percentOf(climbed) : undefined}
        aria-valuetext={spoken || undefined}
      >
        {measured ? (
          <>
            <span className="pb__fill" />
            <span className="pb__sheen" />
          </>
        ) : (
          <span className="pb__slide" />
        )}
      </div>
      <span className="pb__pct" aria-hidden="true">
        {counted === null ? "" : `${about}${percentOf(counted)}%`}
      </span>
    </div>
  );
}
