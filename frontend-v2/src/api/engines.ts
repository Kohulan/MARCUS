import type { Engine, LegacyEngine, PredictionOut } from "./types";

/** The engines offered to users, in menu order (DECIMER is the default). */
export const ENGINES: { value: Engine; label: string }[] = [
  { value: "decimer", label: "DECIMER" },
  { value: "decimer-hand", label: "DECIMER hand-drawn" },
  { value: "molparser", label: "MolParser" },
  { value: "molscribe", label: "MolScribe" },
];

/** Engines no longer offered whose results old papers still hold: named, never run. */
export const LEGACY_ENGINES: { value: LegacyEngine; label: string }[] = [
  { value: "molnextr", label: "MolNexTR" },
];

const LABELS: ReadonlyMap<string, string> = new Map(
  [...ENGINES, ...LEGACY_ENGINES].map((e) => [e.value, e.label]),
);

/** The shown name of an engine wire value, offered or legacy ("molnextr" → "MolNexTR"); others as sent. */
export function engineName(engine: string): string {
  return LABELS.get(engine) ?? engine;
}

/** An offered engine wire value, or null (one the UI does not offer: legacy "molnextr", "fake"). */
export function asEngine(engine: string | null | undefined): Engine | null {
  return ENGINES.find((e) => e.value === engine)?.value ?? null;
}

/** A legacy engine (old papers only): its results show, but it is never started again. */
export function isLegacyEngine(engine: string | null | undefined): boolean {
  return LEGACY_ENGINES.some((e) => e.value === engine);
}

/**
 * The engines whose molfile can hold the image's atom positions, in the order they are
 * preferred (MolNexTR for old papers). MolParser is not one: its molfile is a computed layout.
 */
export const TEMPLATE_ENGINES: readonly string[] = ["molscribe", "molnextr"];

// A computed layout (backend workers/orient.py, the same rule): at least COMPUTED_SHARE of the
// bonds within ONE_LENGTH of the median length; fewer than FEW_BONDS bonds cannot tell.
const COMPUTED_SHARE = 0.8;
const ONE_LENGTH = 0.01;
const FEW_BONDS = 4;

/**
 * The molfile (V2000) holds positions read off the image, not a layout an engine computed
 * (MolNexTR before 7a4e03f; MolScribe when its structure does not sanitize). False for a
 * molfile that cannot be read. The tools worker applies the same rule (orient.image_layout).
 */
export function imageLayout(molfile: string): boolean {
  // a paper layout says itself that its positions are the image's (a printed ring has bonds of
  // one length too): never put to the computed-layout test (backend orient._template)
  if (layoutInfo(molfile) !== null) return true;
  const lines = molfile.split(/\r?\n/);
  const counts = lines[3];
  if (counts === undefined || !/V2000/.test(counts)) return false;
  const atoms = Number.parseInt(counts.slice(0, 3), 10);
  const bonds = Number.parseInt(counts.slice(3, 6), 10);
  if (!(atoms > 0) || !(bonds >= 0) || lines.length < 4 + atoms + bonds) return false;
  const pos: [number, number][] = [];
  for (let i = 0; i < atoms; i++) {
    const line = lines[4 + i]!;
    const x = Number.parseFloat(line.slice(0, 10));
    const y = Number.parseFloat(line.slice(10, 20));
    if (!Number.isFinite(x) || !Number.isFinite(y)) return false;
    pos.push([x, y]);
  }
  const lengths: number[] = [];
  for (let i = 0; i < bonds; i++) {
    const line = lines[4 + atoms + i]!;
    const a = pos[Number.parseInt(line.slice(0, 3), 10) - 1];
    const b = pos[Number.parseInt(line.slice(3, 6), 10) - 1];
    if (!a || !b) return false;
    lengths.push(Math.hypot(b[0] - a[0], b[1] - a[1]));
  }
  if (lengths.length < FEW_BONDS) return true;
  const median = [...lengths].sort((x, y) => x - y)[Math.floor(lengths.length / 2)]!;
  if (median <= 1e-9) return false;
  const same = lengths.filter((l) => Math.abs(l - median) <= ONE_LENGTH * median).length;
  return same < COMPUTED_SHARE * lengths.length;
}

/** The title line of a paper layout molfile (backend marcus.core.paper_layout). */
const LAYOUT_HEADER = /^MARCUS layout fit=(\d+(?:\.\d+)?) bond=(\d+(?:\.\d+)?) size=(\d{1,6})x(\d{1,6})\s*$/;
/** The overlay is offered when the fit is at most this share of the median bond length. */
const OVERLAY_MAX_FIT_SHARE = 0.04;

export type LayoutInfo = {
  /** Mean distance of the bonds from the ink, px. */
  fit: number;
  /** Median bond length, px. */
  bond: number;
  width: number;
  height: number;
  /** The fit is good enough to draw the answers over the image. */
  overlay: boolean;
};

/** What a paper layout's title line says; null for any other molfile. */
export function layoutInfo(molfile: string | null | undefined): LayoutInfo | null {
  if (!molfile || !molfile.startsWith("MARCUS layout")) return null;
  const m = LAYOUT_HEADER.exec(molfile.split("\n", 1)[0]!);
  if (!m) return null;
  const [fit, bond, width, height] = [m[1], m[2], m[3], m[4]].map(Number) as [number, number, number, number];
  if (!(bond > 0) || width < 1 || height < 1) return null;
  return { fit, bond, width, height, overlay: fit <= OVERLAY_MAX_FIT_SHARE * bond };
}

/** The engine whose predictions carry a paper layout. */
const LAYOUT_ENGINE = "molscribe";

/**
 * The prediction whose paper layout the image's drawings follow: the newest MolScribe prediction
 * that has one, valid or not (backend api/depiction.py layout_of). `predictions`: newest first.
 */
export function layoutPrediction(predictions: readonly PredictionOut[]): PredictionOut | null {
  return predictions.find((p) => p.engine === LAYOUT_ENGINE && layoutInfo(p.layout) !== null) ?? null;
}

/** What a drawing is oriented by: the molfile sent, and an id for the query key. */
export type Template = Pick<PredictionOut, "id" | "molfile">;

/** The layout of `p` as a template (its own key: not the prediction's molfile). */
export const layoutTemplate = (p: PredictionOut): Template => ({ id: `${p.id}:layout`, molfile: p.layout! });

/** A molfile that holds the image's positions (none: false). */
export const hasImageLayout = (molfile: string | null | undefined): boolean =>
  !!molfile && imageLayout(molfile);

/** A prediction whose molfile can be a template: valid, with a molfile from the image. */
export const usableTemplate = (p: PredictionOut | null | undefined): boolean =>
  p != null && p.valid && hasImageLayout(p.molfile);

/**
 * What draws an image's structures in the paper's orientation: MolScribe's paper layout (valid
 * or not), else the newest valid MolScribe prediction whose molfile holds the image's
 * positions, else MolNexTR's (old papers); null without one. `use` leaves an engine out
 * (Compare's "Use coordinates" off: MolScribe's switches its layout off too).
 * The server picks a segment's template in the same order (backend api/depiction.py
 * orientation_templates).
 * `predictions`: newest first.
 */
export function orientationTemplate(
  predictions: readonly PredictionOut[],
  use: Readonly<Record<string, boolean>> = {},
): Template | null {
  const layout = use[LAYOUT_ENGINE] === false ? null : layoutPrediction(predictions);
  if (layout) return layoutTemplate(layout);
  for (const engine of TEMPLATE_ENGINES) {
    if (use[engine] === false) continue;
    const p = predictions.find((x) => x.engine === engine && x.valid && Boolean(x.molfile));
    if (p && usableTemplate(p)) return p;
  }
  return null;
}

/**
 * The line beside a run's "Reading…" for an engine much slower on its first run, else null.
 * DECIMER hand-drawn loads its model on its first request (backend workers/ocsr/decimer.py:
 * ~25 s on the GPU before the prediction), while the others answer in a few seconds.
 */
export function firstRunNote(engine: string | null | undefined): string | null {
  return engine === "decimer-hand" ? "The first run can take about 30 s" : null;
}
