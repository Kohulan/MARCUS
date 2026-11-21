import { useId, useRef } from "react";
import { GlassButton } from "../ui/GlassButton";
import Kbd from "../ui/Kbd";
import { Modal } from "../ui/modal";
import { REVIEW_KEYS } from "./useReviewKeys";

/**
 * The key list: a modal dialog named "Keys". Focus moves into it, and Escape (or Close)
 * closes it and gives focus back to where it was.
 */
export default function KeyHelp({ onClose }: { onClose: () => void }) {
  const titleId = useId();
  const close = useRef<HTMLButtonElement>(null);
  return (
    <Modal className="keyhelp" labelledBy={titleId} onClose={onClose} first={close} backdropClose>
      <div className="keyhelp__head">
        <h2 id={titleId} className="keyhelp__title">
          Keys
        </h2>
        <GlassButton ref={close} tint="clear" size="sm" onClick={onClose}>
          Close
        </GlassButton>
      </div>
      <dl className="keyhelp__list">
        {REVIEW_KEYS.map(({ shown, label }) => (
          <div key={label} className="keyhelp__row">
            <dt>
              <Kbd>{shown}</Kbd>
            </dt>
            <dd>{label}</dd>
          </div>
        ))}
      </dl>
    </Modal>
  );
}
