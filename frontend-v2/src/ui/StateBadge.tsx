import "./ui.css";

/** A structure's state (spec §7 state table). The API's `unchecked` (and no curation) is "to-check". */
export type CardState = "accepted" | "rejected" | "to-check" | "reading" | "failed" | "not-read";

/** The state's word (exact, spec §7 state table). */
export const STATE_WORD: Record<CardState, string> = {
  accepted: "Accepted",
  rejected: "Rejected",
  "to-check": "To check",
  reading: "Reading…",
  failed: "Failed",
  "not-read": "Not read yet",
};

/** A state as its exact word and its shape, never colour alone (spec §7 state table). */
export default function StateBadge({ state }: { state: CardState }) {
  const word = STATE_WORD[state];
  switch (state) {
    case "accepted":
      // Green text sits on paper or surface only, never on sunken (4.4:1 there).
      return <span className="state state--accepted">{word}</span>;
    case "to-check":
      return <span className="state badge badge--orange">{word}</span>;
    case "rejected":
      return (
        <span className="state state--rejected">
          <span aria-hidden="true">✕ </span>
          {word}
        </span>
      );
    case "failed":
      return <span className="state tag tag--charcoal">{word}</span>;
    case "reading":
      return <span className="state badge badge--dashed">{word}</span>;
    case "not-read":
      return (
        <span className="state state--not-read">
          <span aria-hidden="true">□ </span>
          {word}
        </span>
      );
  }
}

/**
 * A paper's or image job's state as its word and its shape. `annotating`: a busy paper whose
 * only work is its annotation says so, in the Reading shape.
 */
export function ItemState({
  status,
  notRead,
  annotating,
}: {
  status: string;
  notRead?: boolean;
  annotating?: boolean;
}) {
  if (status === "failed") return <StateBadge state="failed" />;
  if (status === "done") {
    if (notRead) return <StateBadge state="not-read" />;
    return (
      <span className="state item-done">
        <span className="item-done__mark" aria-hidden="true" />
        Done
      </span>
    );
  }
  if (annotating) return <span className="state badge badge--dashed">Annotating…</span>;
  return <StateBadge state="reading" />;
}
