import "./ui.css";

/**
 * A structure's state (spec §7 state table). The API's `unchecked` (and no curation) is
 * "to-review" when the engines agree on the structure, else "to-check" (owner decision
 * 2026-11-26).
 */
export type CardState =
  | "accepted"
  | "rejected"
  | "to-check"
  | "to-review"
  | "reading"
  | "failed"
  | "not-read";

/** The state's word (exact, spec §7 state table). */
export const STATE_WORD: Record<CardState, string> = {
  accepted: "Accepted",
  rejected: "Rejected",
  "to-check": "To check",
  "to-review": "To review",
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
      // Amber fill: the engines differ (not red, not the brand orange: owner, 2026-11-26).
      return <span className="state badge badge--amber">{word}</span>;
    case "to-review":
      // A calm grey outline: the engines agree, a person still decides.
      return <span className="state badge badge--outline">{word}</span>;
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

/** A paper's or image job's state as its word and its shape. */
export function ItemState({
  status,
  notRead,
  choose,
}: {
  status: string;
  notRead?: boolean;
  /** The paper waits for "Read all pages" / "Pick a structure". */
  choose?: boolean;
}) {
  if (status === "failed") return <StateBadge state="failed" />;
  if (status === "done" && choose) return <span className="state badge badge--orange">Choose</span>;
  if (status === "done") {
    if (notRead) return <StateBadge state="not-read" />;
    return (
      <span className="state item-done">
        <span className="item-done__mark" aria-hidden="true" />
        Done
      </span>
    );
  }
  return <StateBadge state="reading" />;
}
