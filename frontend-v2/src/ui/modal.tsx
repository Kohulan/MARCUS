import { useEffect, useRef, type ReactNode, type RefObject } from "react";
import { returnFocus } from "./focus";

// Where focus goes when a dialog closes: back to what had it (the opener). When that cannot
// take it (gone after a decision or a live update, disabled, or it was the page body), to the
// host's fallback: by default the opener's focus home (data-focus-home: the focus-mode
// region), so the review keys, which act only inside that region, keep working. With no
// fallback, focus stays where it fell.

const HOME = "[data-focus-home]";

/**
 * Opens a native <dialog> as a modal (top layer; the page behind is inert), or in place
 * (`inline`), and moves focus to `first`; on unmount gives focus back (returnFocus) with
 * `fallback`, else the host's focus home. jsdom and old engines without showModal get the
 * open attribute.
 */
export function useModal(
  dialog: RefObject<HTMLDialogElement | null>,
  first?: RefObject<HTMLElement | null>,
  opts: { inline?: boolean; fallback?: (() => HTMLElement | null) | undefined } = {},
): void {
  const { inline = false } = opts;
  // Read at close, so a host that re-renders meanwhile does not reopen the dialog.
  const fallback = useRef(opts.fallback);
  fallback.current = opts.fallback;
  useEffect(() => {
    const el = dialog.current;
    const before = document.activeElement;
    // The host's focus home: the opener's, else the dialog's own (an opener that went in the
    // same render as the dialog came is no longer in the page).
    const home = before?.closest<HTMLElement>(HOME) ?? el?.closest<HTMLElement>(HOME) ?? null;
    if (el && !el.open) {
      if (!inline && typeof el.showModal === "function") el.showModal();
      else el.setAttribute("open", "");
    }
    first?.current?.focus();
    const host = fallback;
    return () => returnFocus(before, host.current?.() ?? home);
  }, [dialog, first, inline]);
}

type ModalProps = {
  /** The host's ref to the <dialog>, when it needs one. */
  box?: RefObject<HTMLDialogElement>;
  className: string;
  /** Id of the heading (or text) that names the dialog. */
  labelledBy: string;
  /** Escape, the backdrop (with `backdropClose`), or a native close: the host unmounts it. */
  onClose: () => void;
  /** Where focus starts; without it the host focuses something itself. */
  first?: RefObject<HTMLElement | null>;
  /** Where focus goes on close when the opener cannot take it. */
  fallback?: RefObject<HTMLElement | null>;
  /** In place, not in the top layer (the papers list's delete confirm). */
  inline?: boolean;
  /** A press on the backdrop closes it. */
  backdropClose?: boolean;
  busy?: boolean;
  children: ReactNode;
};

/**
 * The one dialog frame: a native <dialog>, opened by useModal (focus in, focus back), closed
 * by Escape (preventDefault: the review keys never see that Escape), by the native `cancel`
 * and `close` events, and by the backdrop when asked. The host owns whether it is open: it
 * unmounts it in `onClose`. A click inside keeps focus in the box (tabIndex -1), so Escape
 * still reaches it.
 */
export function Modal({
  box: hostBox,
  className,
  labelledBy,
  onClose,
  first,
  fallback,
  inline = false,
  backdropClose = false,
  busy,
  children,
}: ModalProps) {
  const ownBox = useRef<HTMLDialogElement>(null);
  const box = hostBox ?? ownBox;
  useModal(box, first, { inline, fallback: fallback && (() => fallback.current) });
  return (
    <dialog
      ref={box}
      className={className}
      tabIndex={-1}
      aria-labelledby={labelledBy}
      aria-busy={busy}
      onKeyDown={(e) => {
        if (e.key !== "Escape") return;
        e.preventDefault();
        onClose();
      }}
      onCancel={(e) => {
        e.preventDefault(); // the dialog closes by unmounting, which the host owns
        onClose();
      }}
      // A close the browser made itself (a second Escape it does not let us cancel).
      onClose={onClose}
      // A press on the backdrop lands on the dialog itself.
      onMouseDown={backdropClose ? (e) => e.target === e.currentTarget && onClose() : undefined}
    >
      {children}
    </dialog>
  );
}
