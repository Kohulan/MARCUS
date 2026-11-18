import { forwardRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import "./glass.css";

export type GlassTint = "orange" | "green" | "clear";
type GlassSize = "md" | "sm";

/**
 * Pill buttons (spec §7 decision 4). Orange: the main action of a screen. Green: accept,
 * send, save. Clear: everything secondary. Only on light grounds, never on charcoal or a
 * picture. Look and fallbacks are all in glass.css.
 */
function glassClass(tint: GlassTint, size: GlassSize): string {
  return size === "sm" ? `glass glass--${tint} glass--sm` : `glass glass--${tint}`;
}

type GlassButtonProps = {
  tint: GlassTint;
  size?: GlassSize;
  type?: "button" | "submit";
  disabled?: boolean;
  onClick?: () => void;
  /** Accessible name when the label alone is not enough ("Retry page 5"). */
  label?: string | undefined;
  /** Id of the text that says why the button is disabled, or what it does. */
  describedBy?: string | undefined;
  /** For a button that opens a menu or panel: its state and the id of what it opens. */
  expanded?: boolean | undefined;
  controls?: string | undefined;
  children: ReactNode;
};

export const GlassButton = forwardRef<HTMLButtonElement, GlassButtonProps>(function GlassButton(
  { tint, size = "md", type = "button", disabled, onClick, label, describedBy, expanded, controls, children },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={glassClass(tint, size)}
      disabled={disabled}
      onClick={onClick}
      aria-label={label}
      aria-describedby={describedBy}
      aria-expanded={expanded}
      aria-controls={controls}
    >
      {children}
    </button>
  );
});

type GlassLinkProps = {
  tint: GlassTint;
  size?: GlassSize;
  to: string;
  /** Router state handed to the next page (the landing's "Upload a PDF" asks /app to open the file picker). */
  state?: unknown;
  children: ReactNode;
};

/** A route link that looks like a glass button ("Upload a PDF", "Try a sample paper"). */
export function GlassLink({ tint, size = "md", to, state, children }: GlassLinkProps) {
  return (
    <Link to={to} state={state} className={glassClass(tint, size)}>
      {children}
    </Link>
  );
}
