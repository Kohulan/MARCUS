import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

/**
 * A disclosure (a menu button and its panel): open and close, and Escape, a click or focus
 * outside close it. `close(true)` also puts focus back on its button, where a dialog opened
 * from the panel returns it. Escape is handled here, so it calls preventDefault (the review
 * keys skip a key a component handled).
 */
export function useDisclosure() {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panelId = useId();

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

  return { open, setOpen, root, button, panelId, close, onKeyDown };
}
