import "./ui.css";

export type StructureState =
  "accepted" | "rejected" | "to-check" | "failed" | "reading" | "not-read";

/**
 * A state as its exact word and its shape, never colour alone (spec §7 state table).
 * The API's `unchecked` (and no curation) is "to-check" here.
 */
export default function StateBadge({ state }: { state: StructureState }) {
  switch (state) {
    case "accepted":
      // Green text sits on paper or surface only, never on sunken (4.4:1 there).
      return <span className="state state--accepted">Accepted</span>;
    case "to-check":
      return <span className="state badge badge--orange">To check</span>;
    case "rejected":
      return (
        <span className="state state--rejected">
          <span aria-hidden="true">✕ </span>Rejected
        </span>
      );
    case "failed":
      return <span className="state tag tag--charcoal">Failed</span>;
    case "reading":
      return <span className="state badge badge--dashed">Reading…</span>;
    case "not-read":
      return (
        <span className="state state--not-read">
          <span aria-hidden="true">□ </span>Not read yet
        </span>
      );
  }
}
