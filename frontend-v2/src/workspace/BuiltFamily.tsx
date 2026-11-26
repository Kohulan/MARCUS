// The built structures of one scaffold, together in one tinted box under it (owner,
// 2026-11-26): the grid, the Paper view's list and the pick page's column all use it.
import { faArrowTurnUp } from "@fortawesome/free-solid-svg-icons";
import type { ReactNode } from "react";
import Icon from "../ui/Icon";
import { builtFromText } from "./built";
import "./builtFamily.css";

export default function BuiltFamily({
  n,
  count,
  wide = false,
  children,
}: {
  /** The scaffold's [nn] number. */
  n: number;
  count: number;
  /** In the review grid: the box takes a whole row, its cards on the grid's columns. */
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      className={wide ? "built-family built-family--wide" : "built-family"}
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
