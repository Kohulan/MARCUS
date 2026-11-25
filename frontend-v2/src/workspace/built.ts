// Markush Phase 3: structures MARCUS built from a scaffold and its R-group rows. The words, and
// the small pure helpers the cards use.
import type { BuildFailure } from "../api/types";

export const BUILD = "Build structures";
export const COULD_NOT_BUILD = "Could not build";

/** One row that was not built: "3c: unknown substituent "Tig"". */
export const failureText = (f: BuildFailure): string => `${f.compound}: ${f.reason}`;
