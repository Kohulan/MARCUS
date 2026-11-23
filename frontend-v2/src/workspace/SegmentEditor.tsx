// The structure editor for a segment of the paper workspace (opened from focus mode or a card):
// it opens on the structure the card shows and saves through useSaveCuration with
// editorChange, so curationBody keeps the note and a structure still to check is accepted.
import { useState } from "react";
import { api } from "../api/client";
import { useSaveCuration } from "../api/queries";
import type { SegmentOut } from "../api/types";
import { shownStructure } from "./cardState";
import Editor, { editorChange, type EditorStructure } from "./Editor";

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
  // Fixed at open: a live update while the dialog is open does not move the starting point.
  // The host keys this by segment, so the save goes to the segment it opened on.
  const [initial] = useState(() => editorStart(segment, paperEngine));
  // The editor reads its props through a ref refreshed every render, so the status rule
  // sees the curation as it is when Save is pressed. The save's promise goes back to the
  // dialog: a 422 keeps it open with "Save failed: …".
  const onSave = async (s: EditorStructure) => {
    await save(segment.id, editorChange(segment.curation, s));
  };
  // Left of Ketcher: the crop the engines read, and its page with this structure's box.
  const [source] = useState(() => ({
    image: api.segmentImageUrl(segment.id),
    page: { url: api.pageImageUrl(paperId, segment.page), bbox: segment.bbox, page0: segment.page },
  }));
  return <Editor initial={initial} source={source} onSave={onSave} onClose={onClose} />;
}
