import type { Engine } from "./types";

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
