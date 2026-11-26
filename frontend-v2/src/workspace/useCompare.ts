// Compare engines (spec §6): one engine per column, started when Compare opens, the pairwise
// Tanimoto similarity, the differences or the common part marked. Every chemistry answer comes from the
// /tools routes (per-owner bucket of 60/min); each is a TanStack Query entry keyed by its
// inputs with staleTime Infinity, so a second look at the same structures costs nothing.
import { useQueries, useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { api, ApiError, errorText } from "../api/client";
import type { Glow } from "../api/depictions";
import { ENGINES, engineName } from "../api/engines";
import { reasonText } from "../api/reasons";
import { isStepActive } from "../api/status";
import type { CompareReply, Engine, PredictionOut } from "../api/types";

export type CompareTarget = { kind: "segment" | "image"; id: string };

/** One OCSR step of the target, newest first (paper steps or ImageStepOut). */
export type CompareStep = { engine: string | null; status: string; error_class: string | null };

export type EngineRow = {
  engine: string;
  label: string;
  /** The engine's newest prediction. */
  prediction: PredictionOut | null;
  /** done: has a prediction; reading: a step is on its way; failed: its newest step failed. */
  state: "done" | "reading" | "failed" | "idle";
  /** For a failed engine: reasonText of its newest step. */
  reason: string | null;
};

/** The three main engines, Compare's columns. DECIMER hand-drawn is the DECIMER column's toggle. */
export const MAIN_ENGINES: readonly Engine[] = ["decimer", "molparser", "molscribe"];
const HAND: Engine = "decimer-hand";

/**
 * The columns: the three main engines, then any other engine a prediction came from (as
 * sent; never DECIMER hand-drawn). `hand`: the DECIMER column shows the hand-drawn model.
 * `requested` maps an engine started here to its step count at that moment: it reads as
 * "Reading…" until a newer step of it (or a prediction) arrives.
 */
export function engineRows(
  predictions: PredictionOut[],
  steps: CompareStep[],
  requested: ReadonlyMap<string, number>,
  hand = false,
): EngineRow[] {
  const names: string[] = MAIN_ENGINES.map((e) => (hand && e === "decimer" ? HAND : e));
  for (const p of predictions) {
    if (!names.includes(p.engine) && p.engine !== HAND && p.engine !== "decimer") {
      names.push(p.engine);
    }
  }
  return names.map((engine) => {
    const prediction = predictions.find((p) => p.engine === engine) ?? null;
    const own = steps.filter((s) => s.engine === engine);
    const label = engineName(engine);
    if (prediction) return { engine, label, prediction, state: "done", reason: null };
    const asked = requested.get(engine);
    if (own.some((s) => isStepActive(s.status)) || (asked !== undefined && own.length <= asked)) {
      return { engine, label, prediction, state: "reading", reason: null };
    }
    if (own[0]?.status === "failed") {
      return { engine, label, prediction, state: "failed", reason: reasonText(own[0].error_class) };
    }
    return { engine, label, prediction, state: "idle", reason: null };
  });
}

/**
 * The engines of these columns to start: offered ones not read and not running (Compare's
 * opening start; the hand-drawn toggle's). A failed one is left for its own Retry (an engine
 * that just failed would likely fail again).
 */
export function enginesToRun(rows: EngineRow[]): Engine[] {
  return ENGINES.map((e) => e.value).filter((engine) => {
    const row = rows.find((r) => r.engine === engine);
    return row !== undefined && row.state === "idle";
  });
}

/** "Too many requests, try again in N s" for a 429 (errorText); null for anything else. */
export function tooManyText(err: unknown): string | null {
  return err instanceof ApiError && err.status === 429 ? errorText(err) : null;
}

const sorted = <T>(list: T[]) => [...list].sort();

/**
 * Starts engines: a prediction for each engine given, all at once (Compare's opening start,
 * or one engine's Retry); once they have answered, `onStarted()` once (when at least one was
 * accepted), so the page's stream opens again. Compare opens no stream of its own.
 */
export function useEngineRuns(
  target: CompareTarget,
  steps: CompareStep[],
  onStarted: () => void,
): {
  requested: ReadonlyMap<string, number>;
  /** The engines the last start started (those refused taken out). */
  batch: readonly string[];
  sending: boolean;
  error: unknown;
  run: (engines: Engine[]) => void;
} {
  const [requested, setRequested] = useState<ReadonlyMap<string, number>>(() => new Map());
  const [batch, setBatch] = useState<readonly string[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const run = useCallback(
    (engines: Engine[]) => {
      if (engines.length === 0) return;
      setError(null);
      setSending(true);
      setBatch(engines);
      setRequested((old) => {
        const next = new Map(old);
        for (const engine of engines) {
          next.set(engine, steps.filter((s) => s.engine === engine).length);
        }
        return next;
      });
      const start =
        target.kind === "image"
          ? (engine: Engine) => api.runImagePrediction(target.id, engine)
          : (engine: Engine) => api.runPrediction(target.id, engine);
      void Promise.allSettled(engines.map(start)).then((results) => {
        setSending(false);
        const refused = engines.filter((_, i) => results[i]!.status === "rejected");
        if (refused.length > 0) {
          setRequested((old) => {
            const next = new Map(old);
            for (const engine of refused) next.delete(engine);
            return next;
          });
          setBatch((old) => old.filter((engine) => !refused.includes(engine as Engine)));
          const first = results.find((r) => r.status === "rejected") as PromiseRejectedResult;
          setError(first.reason);
        }
        if (refused.length < engines.length) onStarted();
      });
    },
    [target.kind, target.id, steps, onStarted],
  );

  return { requested, batch, sending, error, run };
}

export type Pair = {
  a: string;
  b: string;
  /** Tanimoto in 0..1; null while asking or when it failed. */
  value: number | null;
  same: boolean;
  error: unknown;
};

/**
 * The similarity of every pair of engines with a valid prediction: one `api.compare` per
 * unordered pair of distinct SMILES (key ["compare", a, b] with a < b); engines with the
 * same SMILES need no call.
 */
export function useSimilarity(rows: EngineRow[]): Pair[] {
  const valid = rows.filter((r) => r.prediction?.valid);
  const distinct = sorted([...new Set(valid.map((r) => r.prediction!.smiles))]);
  const smilesPairs: [string, string][] = [];
  for (let i = 0; i < distinct.length; i++) {
    for (let j = i + 1; j < distinct.length; j++) smilesPairs.push([distinct[i]!, distinct[j]!]);
  }
  const results = useQueries({
    queries: smilesPairs.map(([a, b]) => ({
      queryKey: ["compare", a, b] as const,
      queryFn: (): Promise<CompareReply> => api.compare(a, b),
      staleTime: Infinity,
    })),
  });

  const pairs: Pair[] = [];
  for (let i = 0; i < valid.length; i++) {
    for (let j = i + 1; j < valid.length; j++) {
      const x = valid[i]!.prediction!.smiles;
      const y = valid[j]!.prediction!.smiles;
      const pair = { a: valid[i]!.label, b: valid[j]!.label };
      if (x === y) {
        pairs.push({ ...pair, value: 1, same: true, error: null });
        continue;
      }
      const [lo, hi] = x < y ? [x, y] : [y, x];
      const k = smilesPairs.findIndex(([p, q]) => p === lo && q === hi);
      const q = results[k]!;
      pairs.push({ ...pair, value: q.data?.tanimoto ?? null, same: false, error: q.error });
    }
  }
  return pairs;
}

/** A SMILES as a molfile from /tools/smiles-to-molfile: key ["molfile", smiles]. */
export function molfileQuery(smiles: string) {
  return {
    queryKey: ["molfile", smiles] as const,
    queryFn: () => api.smilesToMolfile(smiles),
    staleTime: Infinity,
  };
}

/** What Compare marks in the drawings. */
export type MarkMode = "differences" | "common" | "off";

/**
 * Where the drawn answers differ and what they share (/tools/differences, stereo-aware): one
 * question for the distinct SMILES in a fixed order (key ["differences", ...sorted]). `of`
 * gives a SMILES its atoms to mark under `mode` (null: none, or not known yet). `settled`: the
 * answer is here or failed, so a drawing is asked for once, with its marks. `none`: nothing
 * to mark in any answer (the same structure written in different ways; nothing in common).
 */
export function useDifferences(
  smiles: string[],
  mode: MarkMode,
): {
  of: (smiles: string) => Glow | null;
  settled: boolean;
  none: boolean;
  rough: boolean;
  error: unknown;
} {
  const distinct = sorted([...new Set(smiles)]);
  const on = mode !== "off" && distinct.length >= 2;
  const q = useQuery({
    queryKey: ["differences", ...distinct],
    queryFn: () => api.differences(distinct),
    staleTime: Infinity,
    enabled: on,
  });
  const field = mode === "common" ? "common" : "marks";
  const lists = on && q.data ? q.data[field] : null;
  const of = (x: string): Glow | null => {
    const atoms = lists?.[distinct.indexOf(x)];
    return atoms && atoms.length > 0 ? { [field]: atoms } : null;
  };
  return {
    of,
    settled: !on || q.data !== undefined || q.isError,
    none: lists !== null && lists.every((atoms) => atoms.length === 0),
    rough: on && q.data?.rough === true,
    error: on ? q.error : null,
  };
}
