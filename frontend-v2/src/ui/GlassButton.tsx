import type { ReactNode } from "react";
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
  children: ReactNode;
};

export function GlassButton({
  tint,
  size = "md",
  type = "button",
  disabled,
  onClick,
  children,
}: GlassButtonProps) {
  return (
    <button type={type} className={glassClass(tint, size)} disabled={disabled} onClick={onClick}>
      {children}
    </button>
  );
}

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
