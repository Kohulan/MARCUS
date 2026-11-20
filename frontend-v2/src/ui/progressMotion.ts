// The figures behind every progress bar (ProgressBar): the shown percentage, the one motion
// curve in JS (the count-up follows the fill's CSS transition), and the time-based estimate
// of an annotate run, whose model reports no progress.

/** The fill's transition and the count-up, in ms (tokens.css: 500ms for position). */
export const FILL_MS = 500;

/**
 * An estimate, not a measurement: a typical annotate run (the local model over one paper's
 * text) takes about this long. The bar eases to ANNOTATE_TYPICAL_SHARE over this time.
 */
export const ANNOTATE_TYPICAL_MS = 6000;
/** Where the estimate stands at the typical run time. */
export const ANNOTATE_TYPICAL_SHARE = 0.9;
/** A run that takes longer creeps toward this and never past it: 100% only when it ends. */
export const ANNOTATE_CAP = 0.95;
/** How slowly a long run creeps (the time constant past the typical run time). */
const ANNOTATE_CREEP_MS = 20_000;

/** How long a finished run stays on its full bar before the bar goes. */
export const END_HOLD_MS = 600;

/** The whole percent reached, rounded down: 100 only when the work is done. */
export function percentOf(fraction: number): number {
  if (!(fraction > 0)) return 0;
  return Math.min(100, Math.floor(fraction * 100 + 1e-9));
}

/**
 * The bar's spoken value: its words and, when it is measured, the percentage ("about 60%"
 * for an estimate short of the end).
 */
export function spokenValue(text: string, fraction: number | null, estimated = false): string {
  if (fraction === null) return text;
  const pct = `${estimated && fraction < 1 ? "about " : ""}${percentOf(fraction)}%`;
  return text ? `${text}, ${pct}` : pct;
}

/** The --ease token's control points (tokens.css cubic-bezier(0.22, 1, 0.36, 1); a test keeps them equal). */
export const EASE = [0.22, 1, 0.36, 1] as const;
const [X1, Y1, X2, Y2] = EASE;
const bez = (t: number, a: number, b: number) =>
  3 * a * t * (1 - t) ** 2 + 3 * b * t ** 2 * (1 - t) + t ** 3;
// d/dt of bez: positive on [0, 1] for these points (x only grows), so Newton converges.
const slope = (t: number, a: number, b: number) =>
  3 * a * (1 - t) ** 2 + 6 * (b - a) * t * (1 - t) + 3 * (1 - b) * t ** 2;

/** The --ease curve at time share `x` (0 to 1): x(t) = x solved by Newton's method, then y(t). */
export function ease(x: number): number {
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  let t = x;
  for (let i = 0; i < 5; i += 1) {
    t = Math.min(1, Math.max(0, t - (bez(t, X1, X2) - x) / slope(t, X1, X2)));
  }
  return bez(t, Y1, Y2);
}

/** The counted figure `elapsed` ms after it set off from `from` toward `to`; never below `from`. */
export function countFrame(from: number, to: number, elapsed: number, duration: number): number {
  if (to <= from) return from;
  if (elapsed >= duration) return to;
  return from + (to - from) * ease(elapsed / duration);
}

/**
 * The annotate estimate `elapsedMs` after the run started: an ease-out to 90% over the typical
 * run time, then a slow creep toward 95%. Never 100%: that is shown when the run ends.
 */
export function annotateEstimate(elapsedMs: number): number {
  if (!(elapsedMs > 0)) return 0;
  if (elapsedMs <= ANNOTATE_TYPICAL_MS) {
    const x = elapsedMs / ANNOTATE_TYPICAL_MS;
    return ANNOTATE_TYPICAL_SHARE * (1 - (1 - x) ** 2);
  }
  const past = elapsedMs - ANNOTATE_TYPICAL_MS;
  const creep = (ANNOTATE_CAP - ANNOTATE_TYPICAL_SHARE) * (1 - Math.exp(-past / ANNOTATE_CREEP_MS));
  return Math.min(ANNOTATE_CAP, ANNOTATE_TYPICAL_SHARE + creep);
}

/** The figure shown so far in this run, and whether the work was going on at the last look. */
export type Climb = { max: number; busy: boolean };

/**
 * A bar never moves back while its work goes on: the shown figure is the highest so far in
 * this run (work that starts again, a retried page, starts a new run). The same state back
 * when nothing changed.
 */
export function climb(prev: Climb, fraction: number | null, busy: boolean): Climb {
  if (busy && !prev.busy) return { max: fraction ?? 0, busy };
  const max = fraction !== null && fraction > prev.max ? fraction : prev.max;
  if (max === prev.max && busy === prev.busy) return prev;
  return { max, busy };
}
