// Compare engines (spec §6): one engine per column, the pairwise Tanimoto similarity, the
// common part (MCS) highlighted, and "Run all engines". Every chemistry answer comes from the
// /tools routes (per-owner bucket of 60/min); each is a TanStack Query entry keyed by its
// inputs with staleTime Infinity, so a second look at the same structures costs nothing.
import { useQueries, useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { api, ApiError } from "../api/client";
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

/**
 * The columns: the four engines in menu order, then any other engine a prediction came
 * from (as sent). `requested` maps an engine started here to its step count at that moment:
 * it reads as "Reading…" until a newer step of it (or a prediction) arrives.
 */
export function engineRows(
  predictions: PredictionOut[],
  steps: CompareStep[],
  requested: ReadonlyMap<string, number>,
): EngineRow[] {
  const names = ENGINES.map((e) => e.value as string);
  for (const p of predictions) if (!names.includes(p.engine)) names.push(p.engine);
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

/** The engines "Run all engines" starts: offered ones with no prediction and nothing running. */
export function enginesToRun(rows: EngineRow[]): Engine[] {
  return ENGINES.map((e) => e.value).filter((engine) => {
    const row = rows.find((r) => r.engine === engine);
    return row !== undefined && (row.state === "idle" || row.state === "failed");
  });
}

/** "Too many requests, try again in N s" for a 429; null for anything else. */
export function tooManyText(err: unknown): string | null {
  if (!(err instanceof ApiError) || err.status !== 429) return null;
  return err.retryAfter !== undefined
    ? `Too many requests, try again in ${err.retryAfter} s`
    : "Too many requests, try again in a moment";
}

const sorted = <T>(list: T[]) => [...list].sort();

/**
 * "Run all engines": a prediction for each engine of `enginesToRun`, all at once; once they
 * have answered, `onStarted()` once (when at least one was accepted), so the page's stream
 * opens again. Compare opens no stream of its own.
 */
export function useRunAll(
  target: CompareTarget,
  steps: CompareStep[],
  onStarted: () => void,
): {
  requested: ReadonlyMap<string, number>;
  sending: boolean;
  error: unknown;
  runAll: (engines: Engine[]) => void;
} {
  const [requested, setRequested] = useState<ReadonlyMap<string, number>>(() => new Map());
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const runAll = useCallback(
    (engines: Engine[]) => {
      if (engines.length === 0) return;
      setError(null);
      setSending(true);
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
          const first = results.find((r) => r.status === "rejected") as PromiseRejectedResult;
          setError(first.reason);
        }
        if (refused.length < engines.length) onStarted();
      });
    },
    [target.kind, target.id, steps, onStarted],
  );

  return { requested, sending, error, runAll };
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

/**
 * The common part of the valid predictions' distinct structures: each one's own molfile, or
 * `smilesToMolfile` for one sent without (molfileQuery), then `mcs` over the molfiles
 * (["mcs", ...sortedMolfiles]). `highlight` is the MCS SMARTS: null while asking, when off,
 * or when there is none (`none`).
 */
export function useCommonPart(
  predictions: Pick<PredictionOut, "smiles" | "molfile">[],
  enabled: boolean,
): { highlight: string | null; none: boolean; errors: unknown[] } {
  const own = new Map<string, string | null>();
  for (const p of predictions) if (!own.get(p.smiles)) own.set(p.smiles, p.molfile || null);
  const distinct = sorted([...own.keys()]);
  const on = enabled && distinct.length >= 2;
  const toConvert = distinct.filter((s) => own.get(s) === null);
  const converted = useQueries({
    queries: toConvert.map((s) => ({ ...molfileQuery(s), enabled: on })),
  });
  const files = distinct.map((s) => own.get(s) ?? converted[toConvert.indexOf(s)]?.data);
  const ready = on && files.every((f): f is string => typeof f === "string");
  const key = ready ? sorted(files as string[]) : [];
  const mcs = useQuery({
    queryKey: ["mcs", ...key],
    queryFn: () => api.mcs(key),
    staleTime: Infinity,
    enabled: ready,
  });
  const smarts = mcs.data && mcs.data.atom_count > 0 ? mcs.data.mcs_smarts || null : null;
  return {
    highlight: on ? smarts : null,
    none: on && mcs.data !== undefined && smarts === null,
    errors: [...converted.map((q) => q.error), mcs.error].filter((e) => e !== null),
  };
}
