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
const TEMPLATE_ENGINES: readonly string[] = ["molscribe", "molnextr"];

/**
 * The prediction whose molfile draws an image's structures in the paper's orientation: the
 * newest valid MolScribe prediction with a molfile, else MolNexTR's; null without one. The
 * server picks a segment's the same way (backend api/depiction.py orientation_template), and
 * the tools worker uses it only when its positions come from the image.
 * `predictions`: newest first.
 */
export function orientationTemplate(predictions: readonly PredictionOut[]): PredictionOut | null {
  for (const engine of TEMPLATE_ENGINES) {
    const p = predictions.find((x) => x.engine === engine && x.valid && Boolean(x.molfile));
    if (p) return p;
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
