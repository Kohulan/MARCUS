import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { useAnchoredPanel, type PlaceOptions } from "./anchor";

/**
 * A disclosure (a menu button and its panel): open and close, and Escape, a click or focus
 * outside close it. `close(true)` also puts focus back on its button, where a dialog opened
 * from the panel returns it. Escape is handled here, so it calls preventDefault (the review
 * keys skip a key a component handled).
 *
 * The panel (`panel` ref) opens in the top layer next to its button, inside the viewport
 * (useAnchoredPanel: `place` says which side is tried first and which edges line up), so a
 * scrolling column or a sticky caption never cuts it off. Scrolled out of sight with its
 * button, it closes; focus that was in it goes back to the button.
 */
export function useDisclosure(place: Pick<PlaceOptions, "prefer" | "align"> = DOWN_END) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const panelId = useId();

  useAnchoredPanel(open, button, panel, place, () => {
    const had = panel.current?.contains(document.activeElement) ?? false;
    setOpen(false);
    if (had) button.current?.focus({ preventScroll: true });
  });

  useEffect(() => {
    if (!open) return;
    const outside = (e: Event) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("focusin", outside);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("focusin", outside);
    };
  }, [open]);

  const close = (refocus: boolean) => {
    setOpen(false);
    if (refocus) button.current?.focus();
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key !== "Escape" || !open) return;
    e.preventDefault();
    close(true);
  };

  return { open, setOpen, root, button, panel, panelId, close, onKeyDown };
}

const DOWN_END = { prefer: "below", align: "end" } as const;
