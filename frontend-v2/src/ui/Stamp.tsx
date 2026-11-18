import { usePrefersReducedMotion } from "./motion";
import "./ui.css";

type StampProps = {
  state: "accepted" | "rejected";
  size?: "sm" | "lg";
  /** Land the stamp: it scales down from 1.4 and settles in 160 ms (never under reduced motion). */
  animate?: boolean;
};

const WORD = { accepted: "Accepted", rejected: "Rejected" } as const;

/** The round decision stamp, rotated −12°: green for Accepted, charcoal for Rejected. */
export default function Stamp({ state, size = "sm", animate = false }: StampProps) {
  const reduce = usePrefersReducedMotion();
  const classes = [
    "stamp",
    state === "accepted" ? "stamp--accepted" : "stamp--charcoal",
    `stamp--${size}`,
  ];
  if (animate && !reduce) classes.push("stamp--landing");
  return (
    <span role="img" aria-label={WORD[state]} className={classes.join(" ")}>
      <span aria-hidden="true" className="stamp__word">
        {WORD[state]}
      </span>
    </span>
  );
}
