// How often each agreement badge was right, measured (owner decision 2026-11-26: "show the
// measured number next to the badge, stating where it comes from").
import type { AgreeState } from "../api/types";

/**
 * Per badge state: `n` hand-checked drawings that got the badge, `right` of them where the
 * structure MARCUS shows was right, stereo included.
 *
 * Source: MARCUS-training/review-feedback/trust-measure/MEASURE.md (2026-11-26; the 119
 * phase-B crops with a hand-made gold structure, stored DECIMER, MolParser and MolScribe
 * outputs, the stereo checked by eye). The rule was set on the same drawings: there is no
 * held-out set. Change the numbers only with a new measurement.
 */
export const MEASURED: Record<AgreeState, { n: number; right: number }> = {
  agree3: { n: 30, right: 30 },
  agree2: { n: 18, right: 18 },
  stereo: { n: 18, right: 0 },
  differ: { n: 25, right: 0 },
};

const LEAD: Record<AgreeState, string> = {
  agree3: "All agree",
  agree2: "Two agree",
  stereo: "Stereo differs",
  differ: "Engines differ",
};

/** "All agree: right in 30 of 30 hand-checked drawings (MARCUS test set 2026-11-26)". */
export function measuredText(state: AgreeState): string {
  const { n, right } = MEASURED[state];
  return `${LEAD[state]}: right in ${right} of ${n} hand-checked drawings (MARCUS test set 2026-11-26)`;
}
