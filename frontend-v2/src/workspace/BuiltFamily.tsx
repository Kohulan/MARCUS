// The built structures of one scaffold, together in one tinted box under it (owner,
// 2026-11-26): the Paper view's list and the pick page's column (the grid keeps them in its
// flow, each on a mint cell: ReviewGrid).
import { faArrowTurnUp } from "@fortawesome/free-solid-svg-icons";
import type { ReactNode } from "react";
import Icon from "../ui/Icon";
import { builtFromText } from "./built";
import "./builtFamily.css";

export default function BuiltFamily({
  n,
  count,
  children,
}: {
  /** The scaffold's [nn] number. */
  n: number;
  count: number;
  children: ReactNode;
}) {
  return (
    <div
      className="built-family"
      role="group"
      aria-label={builtFromText(n)}
    >
      <p className="built-family__cap" aria-hidden="true">
        <Icon icon={faArrowTurnUp} className="built-family__icon" />
        {`${builtFromText(n)} · ${count}`}
      </p>
      <div className="built-family__cards">{children}</div>
    </div>
  );
}
