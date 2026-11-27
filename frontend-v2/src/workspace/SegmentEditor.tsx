// The structure editor for a segment of the paper workspace (opened from focus mode or a card):
// it opens on the structure the card shows and saves through useSaveCuration with
// editorChange, so curationBody keeps the note and a structure still to check is accepted.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { orientationTemplate } from "../api/engines";
import { useSaveCuration } from "../api/queries";
import type { SegmentOut } from "../api/types";
import { shownStructure } from "./cardState";
import Editor, { editorChange, hasImagePositions, type EditorStructure } from "./Editor";

/**
 * What the editor opens with: the structure the card shows (the curated one, else the shown
 * prediction: a curator who presses E on a prediction wants to fix that one), else empty.
 */
export function editorStart(
  segment: SegmentOut,
  paperEngine: string,
): { smiles: string | null; molfile: string | null; engine: string | null } {
  const { smiles, molfile, edited, prediction } = shownStructure(segment, paperEngine);
  return { smiles, molfile, engine: edited ? null : (prediction?.engine ?? null) };
}

export function SegmentEditor({
  paperId,
  paperEngine,
  segment,
  start,
  accept = false,
  onSaved,
  onClose,
}: {
  paperId: string;
  paperEngine: string;
  segment: SegmentOut;
  /** Open on this structure (Compare's "Edit and use": one engine's answer). */
  start?: { smiles: string | null; molfile: string | null; engine: string | null };
  /** The save is a choice, as "Use this one": accepted whatever the card's status was. */
  accept?: boolean;
  /** After the save landed. */
  onSaved?: (() => void) | undefined;
  onClose: () => void;
}) {
  const { save } = useSaveCuration(paperId);
  // Fixed at open: a live update while the dialog is open does not move the starting point.
  // The host keys this by segment, so the save goes to the segment it opened on.
  const [initial] = useState(() => start ?? editorStart(segment, paperEngine));
  // An engine's answer without positions of its own (DECIMER, MolParser) opens laid out like the
  // paper, as Compare draws it: same atoms and bonds, the drawing's positions (owner, 2026-11-27:
  // Edit and use lost the coordinates). Fetched once at open; on failure, the start as it is.
  const [template] = useState(() => orientationTemplate(segment.predictions)?.molfile ?? null);
  const relayout = initial.engine != null && Boolean(initial.smiles) && template !== null && !hasImagePositions(initial);
  const [ready, setReady] = useState(relayout ? null : initial);
  useEffect(() => {
    if (!relayout) return;
    let live = true;
    api.smilesToMolfile(initial.smiles!, template).then(
      (molfile) => live && setReady({ ...initial, molfile }),
      () => live && setReady(initial),
    );
    return () => {
      live = false;
    };
  }, [relayout, initial, template]);
  // The editor reads its props through a ref refreshed every render, so the status rule
  // sees the curation as it is when Save is pressed. The save's promise goes back to the
  // dialog: a 422 keeps it open with "Save failed: …".
  const onSave = async (s: EditorStructure) => {
    await save(segment.id, accept ? { status: "accepted", structure: s } : editorChange(segment.curation, s));
    onSaved?.();
  };
  // Left of Ketcher: the crop the engines read, and its page with this structure's box.
  const source = {
    image: api.segmentImageUrl(segment.id),
    page: { url: api.pageImageUrl(paperId, segment.page), bbox: segment.bbox, page0: segment.page },
  };
  if (ready === null) return null; // the laid-out molfile is on its way (well under a second)
  return <Editor initial={ready} source={source} onSave={onSave} onClose={onClose} />;
}
