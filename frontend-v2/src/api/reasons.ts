// Why a step failed, from its coarse error_class (raw error text is never shown).
const REASONS: Record<string, string> = {
  timeout: "it took too long",
  worker_lost: "the worker stopped while reading it",
  bad_input: "the page could not be opened",
  engine_error: "the engine failed",
};

/** A step kind's own words where the shared ones do not fit (an annotate step reads no page). */
const BY_KIND: Record<string, Record<string, string>> = {
  annotate: {
    worker_lost: "the worker stopped",
    bad_input: "no title, abstract or introduction was found",
    engine_error: "the model failed",
  },
};

/** Why a step (of `kind`, when its words differ) failed. Only own keys count. */
export function reasonText(errorClass: string | null, kind?: string): string {
  if (errorClass === null) return "an unknown error";
  const mine = kind !== undefined && Object.hasOwn(BY_KIND, kind) ? BY_KIND[kind]! : {};
  if (Object.hasOwn(mine, errorClass)) return mine[errorClass]!;
  if (Object.hasOwn(REASONS, errorClass)) return REASONS[errorClass]!;
  return "an unknown error";
}
