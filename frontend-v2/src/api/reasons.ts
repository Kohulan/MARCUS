// Why a step failed, from its coarse error_class (raw error text is never shown).
const REASONS: Record<string, string> = {
  timeout: "it took too long",
  worker_lost: "the worker stopped while reading it",
  bad_input: "the page could not be opened",
  engine_error: "the engine failed",
};

export function reasonText(errorClass: string | null): string {
  if (errorClass !== null && Object.hasOwn(REASONS, errorClass)) return REASONS[errorClass]!;
  return "an unknown error";
}
