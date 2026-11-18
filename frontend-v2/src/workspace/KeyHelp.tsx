import { useId, useRef, type KeyboardEvent } from "react";
import { GlassButton } from "../ui/GlassButton";
import Kbd from "../ui/Kbd";
import { useModal } from "../ui/modal";

/** The focus-mode keys (Global Constraints, exact). */
export const REVIEW_KEYS: { keys: string[]; label: string }[] = [
  { keys: ["A"], label: "Accept" },
  { keys: ["R"], label: "Reject" },
  { keys: ["E"], label: "Edit" },
  { keys: ["C"], label: "Compare engines" },
  { keys: ["←"], label: "Previous" },
  { keys: ["→"], label: "Next" },
  { keys: ["Esc"], label: "Back to grid" },
  { keys: ["?"], label: "This list" },
];

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Keeps Tab and Shift+Tab inside `box` (a modal dialog's focus trap). */
export function trapTab(e: KeyboardEvent<HTMLElement>, box: HTMLElement | null): void {
  if (e.key !== "Tab" || !box) return;
  const items = [...box.querySelectorAll<HTMLElement>(FOCUSABLE)];
  const first = items[0];
  const last = items[items.length - 1];
  if (!first || !last) return;
  const active = document.activeElement;
  if (e.shiftKey && (active === first || !box.contains(active))) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && (active === last || !box.contains(active))) {
    e.preventDefault();
    first.focus();
  }
}

/**
 * The key list: a modal dialog named "Keys". Focus moves into it, Tab stays inside it, and
 * Escape (or Close) closes it and gives focus back to where it was.
 */
export default function KeyHelp({ onClose }: { onClose: () => void }) {
  const titleId = useId();
  const box = useRef<HTMLDialogElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  useModal(box, close);

  const onKeyDown = (e: KeyboardEvent<HTMLDialogElement>) => {
    if (e.key === "Escape") {
      e.stopPropagation(); // Esc closes the list, not focus mode
      e.preventDefault();
      onClose();
      return;
    }
    trapTab(e, box.current);
  };

  return (
    <dialog
      ref={box}
      className="keyhelp"
      // A click on the list keeps focus in the box (not the body), so Esc still closes it.
      tabIndex={-1}
      aria-labelledby={titleId}
      onKeyDown={onKeyDown}
      onCancel={(e) => {
        e.preventDefault(); // the dialog closes by unmounting, which the caller owns
        onClose();
      }}
      // A press on the backdrop lands on the dialog itself.
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="keyhelp__head">
        <h2 id={titleId} className="keyhelp__title">
          Keys
        </h2>
        <GlassButton ref={close} tint="clear" size="sm" onClick={onClose}>
          Close
        </GlassButton>
      </div>
      <dl className="keyhelp__list">
        {REVIEW_KEYS.map(({ keys, label }) => (
          <div key={label} className="keyhelp__row">
            <dt>
              {keys.map((k) => (
                <Kbd key={k}>{k}</Kbd>
              ))}
            </dt>
            <dd>{label}</dd>
          </div>
        ))}
      </dl>
    </dialog>
  );
}
