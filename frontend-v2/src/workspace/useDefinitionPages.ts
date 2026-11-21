import { useMemo } from "react";
import { useSteps, useText } from "../api/queries";
import { textAskable } from "./doclingText";
import { definitionPages } from "./rgroups";

/**
 * The 0-based pages whose text defines R-groups (rgroups.definitionPages), from the paper's
 * Docling text, or null while it is not there. The text can be large, so it is asked for only
 * while `enabled` (a structure with R-groups is open) and once it is ready (textAskable); the
 * Paper view's request for it is shared (one cached query).
 */
export function useDefinitionPages(
  paperId: string,
  paperStatus: string,
  enabled: boolean,
): Set<number> | null {
  const stepsQuery = useSteps(paperId);
  const known = stepsQuery.data !== undefined || stepsQuery.isError;
  const askable = textAskable(stepsQuery.data?.steps ?? [], known, paperStatus);
  const text = useText(paperId, enabled && askable);
  return useMemo(() => (text.data ? definitionPages(text.data) : null), [text.data]);
}
