import type { Engine, PredictionOut } from "./types";

/** The engines shown to users, in menu order (DECIMER is the default). */
export const ENGINES: { value: Engine; label: string }[] = [
  { value: "decimer", label: "DECIMER" },
  { value: "decimer-hand", label: "DECIMER hand-drawn" },
  { value: "molnextr", label: "MolNexTR" },
  { value: "molscribe", label: "MolScribe" },
];

/** The shown name of an engine wire value ("molnextr" → "MolNexTR"); unknown values as sent. */
export function engineName(engine: string): string {
  return ENGINES.find((e) => e.value === engine)?.label ?? engine;
}

/** A known engine wire value, or null (an engine the UI does not offer, such as "fake"). */
export function asEngine(engine: string | null | undefined): Engine | null {
  return ENGINES.find((e) => e.value === engine)?.value ?? null;
}

/** The engines whose molfile can hold the image's atom positions, in the order they are preferred. */
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

/** A molfile that holds the image's positions (none: false). */
export const hasImageLayout = (molfile: string | null | undefined): boolean =>
  !!molfile && imageLayout(molfile);

/** A prediction whose molfile can be a template: valid, with a molfile from the image. */
export const usableTemplate = (p: PredictionOut | null | undefined): boolean =>
  p != null && p.valid && hasImageLayout(p.molfile);

/**
 * The prediction whose molfile draws an image's structures in the paper's orientation: the
 * newest valid MolScribe prediction whose molfile holds the image's positions, else MolNexTR's;
 * null without one. `use` leaves an engine out (Compare's "Use coordinates" off). The server
 * picks a segment's template in the same order (backend api/depiction.py orientation_template).
 * `predictions`: newest first.
 */
export function orientationTemplate(
  predictions: readonly PredictionOut[],
  use: Readonly<Record<string, boolean>> = {},
): PredictionOut | null {
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
