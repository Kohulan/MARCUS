// The structure editor, opening an engine's answer laid out like the paper (owner, 2026-11-27:
// "Edit and use opens the Ketcher window but the coordinates are lost"). DECIMER and MolParser
// read no atom positions; their answer is laid out on the image's paper layout (the same
// template the drawings use, /tools/smiles-to-molfile with `template`): same atoms and bonds,
// the drawing's positions, applied once at open. Paper workspace and image page alike.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { orientationTemplate } from "../api/engines";
import type { PredictionOut } from "../api/types";
import Editor, { hasImagePositions } from "./Editor";
import { molfileQuery } from "./useCompare";

type EditorProps = Parameters<typeof Editor>[0];
type EditorStart = EditorProps["initial"];

/** How long the editor waits for the laid-out molfile before it opens on the start as it is. */
export const LAYOUT_WAIT_MS = 4000;

/**
 * What the editor opens on: the start laid out like the paper when it is an engine's answer
 * without positions of its own and the image has a paper layout; else the start. null while the
 * laid-out molfile is on its way (at most LAYOUT_WAIT_MS); settled once, never moved after.
 */
export function useLaidOutStart(initial: EditorStart, predictions: readonly PredictionOut[]): EditorStart | null {
  const [template] = useState(() => orientationTemplate(predictions));
  const relayout =
    initial.engine != null && Boolean(initial.smiles) && template !== null && !hasImagePositions(initial);
  const query = useQuery({ ...molfileQuery(initial.smiles ?? "", template), enabled: relayout, retry: false });
  const [late, setLate] = useState(false);
  useEffect(() => {
    if (!relayout) return;
    const timer = setTimeout(() => setLate(true), LAYOUT_WAIT_MS);
    return () => clearTimeout(timer);
  }, [relayout]);
  const settled = useRef<EditorStart | null>(null);
  if (settled.current === null) {
    if (!relayout || query.isError || late) settled.current = initial;
    else if (query.data) settled.current = { ...initial, molfile: query.data };
  }
  return settled.current;
}

export default function PaperLayoutEditor({
  predictions,
  ...props
}: EditorProps & { predictions: readonly PredictionOut[] }) {
  const start = useLaidOutStart(props.initial, predictions);
  return start === null ? null : <Editor {...props} initial={start} />;
}
