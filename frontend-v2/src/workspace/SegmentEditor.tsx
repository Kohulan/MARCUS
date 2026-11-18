// The structure editor for a segment of the paper workspace (focus mode, the card menu):
// it opens on the structure the card shows and saves through useSaveCuration with
// editorChange, so curationBody keeps the note and a structure still to check is accepted.
import { useState } from "react";
import { useSaveCuration } from "../api/queries";
import type { SegmentOut } from "../api/types";
import { shownStructure } from "./cardState";
import Editor, { editorChange, type EditorStructure } from "./Editor";
import type { Workspace } from "./useWorkspace";

/**
 * What the editor opens with: the structure the card shows (the curated one, else the shown
 * prediction: a curator who presses E on a prediction wants to fix that one), else empty.
 */
function editorStart(
  segment: SegmentOut,
  paperEngine: string,
): { smiles: string | null; molfile: string | null } {
  const { smiles, molfile } = shownStructure(segment, paperEngine);
  return { smiles, molfile };
}

export function SegmentEditor({
  paperId,
  paperEngine,
  segment,
  onClose,
}: {
  paperId: string;
  paperEngine: string;
  segment: SegmentOut;
  onClose: () => void;
}) {
  const { save } = useSaveCuration(paperId);
  // Fixed at open: a live update while the dialog is open does not move the starting point,
  // and the save goes to the segment it opened on, whatever the host shows meanwhile.
  const [initial] = useState(() => editorStart(segment, paperEngine));
  const [target] = useState(segment.id);
  // The editor reads its props through a ref refreshed every render, so the status rule
  // sees the curation as it is when Save is pressed. The save's promise goes back to the
  // dialog: a 422 keeps it open with "Save failed: …".
  const onSave = async (s: EditorStructure) => {
    // A host that swapped the segment under an open editor: refuse rather than overwrite.
    if (segment.id !== target) throw new Error("The structure changed. Close and edit again.");
    await save(target, editorChange(segment.curation, s));
  };
  return (
    <Editor initial={initial} onSave={onSave} onClose={onClose} />
  );
}

/** The editor opened from a card (grid or Paper view): the segment by id. */
export function CardEditor({
  ws,
  segmentId,
  onClose,
}: {
  ws: Workspace;
  segmentId: string;
  onClose: () => void;
}) {
  const segment = ws.segments.find((s) => s.id === segmentId);
  if (!ws.paper || !segment) return null;
  return (
    <SegmentEditor
      paperId={ws.paper.id}
      paperEngine={ws.paper.engine}
      segment={segment}
      onClose={onClose}
    />
  );
}
