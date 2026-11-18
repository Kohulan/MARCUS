// The structure editor: a modal dialog with a SMILES field above the Ketcher frame
// (/ketcher/, its own CSP). The editor never writes a curation itself: the caller's onSave
// decides (a segment saves through useSaveCuration with editorChange, so curationBody keeps
// the note; the single-image view keeps it local). Ketcher loads only while this is open:
// the iframe is created with the dialog.
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { errorText } from "../api/client";
import type { CurationChange } from "../api/curation";
import type { CurationOut } from "../api/types";
import { GlassButton } from "../ui/GlassButton";
import { returnFocus } from "../ui/modal";
import { listenToFrame, postToFrame } from "./editorBridge";
import "./editor.css";

/** What a save hands to the caller. The SMILES field sends `molfile: null`. */
export type EditorStructure = { smiles: string; molfile: string | null };

type EditorProps = {
  initial: { smiles: string | null; molfile: string | null };
  /** Rejects to keep the dialog open with "Save failed: <detail>". Resolves to close it. */
  onSave: (structure: EditorStructure) => Promise<void>;
  onClose: () => void;
};

/**
 * The change a segment caller passes to `save(segmentId, …)`: the edited structure, and a
 * structure still to check becomes accepted (a curator who fixed it has checked it). Any
 * other status stays. No note key, so curationBody keeps the stored note.
 */
export function editorChange(
  current: CurationOut | null,
  structure: EditorStructure,
): CurationChange {
  const status = !current || current.status === "unchecked" ? "accepted" : current.status;
  return { status, structure };
}

export default function Editor({ initial, onSave, onClose }: EditorProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const iframe = useRef<HTMLIFrameElement>(null);
  const field = useRef<HTMLInputElement>(null);
  const [smiles, setSmiles] = useState(initial.smiles ?? "");
  const [ready, setReady] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Read through refs inside the one message listener, so it is added once per dialog.
  const savingNow = useRef(false);
  const latest = useRef({ initial, onSave, onClose });
  latest.current = { initial, onSave, onClose };

  const save = useCallback(async (structure: EditorStructure) => {
    if (savingNow.current) return;
    savingNow.current = true;
    setSaving(true);
    setError(null);
    try {
      await latest.current.onSave(structure);
      latest.current.onClose();
    } catch (err) {
      setError(`Save failed: ${errorText(err)}`);
      field.current?.focus(); // the disabled button dropped it; the field is where to fix it
    } finally {
      savingNow.current = false;
      setSaving(false);
    }
  }, []);

  const close = useCallback(() => {
    if (!savingNow.current) latest.current.onClose();
  }, []);

  // Modal in the browser (top layer, the page behind is inert); jsdom has no showModal.
  useEffect(() => {
    const el = dialog.current;
    const before = document.activeElement;
    if (el && !el.open) {
      if (typeof el.showModal === "function") el.showModal();
      else el.setAttribute("open", "");
    }
    field.current?.focus();
    return () => returnFocus(before);
  }, []);

  useEffect(
    () =>
      listenToFrame(
        () => iframe.current?.contentWindow ?? null,
        (message) => {
          const frame = iframe.current?.contentWindow;
          if (message.type === "marcus:ready") {
            // also after a reload of the frame: load the structure again
            if (frame) postToFrame(frame, latest.current.initial);
            setReady(true);
          } else if (message.type === "marcus:cancel") {
            close();
          } else if (message.smiles.trim() === "") {
            setError("Draw a structure first.");
          } else {
            void save({ smiles: message.smiles, molfile: message.molfile });
          }
        },
      ),
    [close, save],
  );

  // The field saves only a SMILES the curator changed: saving the starting text would drop
  // the stored molfile (and accept an unchecked structure) on one stray Enter, since the
  // dialog opens with the focus in this field.
  const startSmiles = (initial.smiles ?? "").trim();
  const fieldValue = smiles.trim();
  const fieldChanged = fieldValue !== "" && fieldValue !== startSmiles;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (fieldChanged) void save({ smiles: fieldValue, molfile: null });
  };

  return (
    <dialog
      ref={dialog}
      className="editor"
      aria-labelledby="editor-title"
      onCancel={(e) => {
        e.preventDefault(); // the dialog closes by unmounting, which the caller owns
        close();
      }}
      onKeyDown={(e) => {
        // As in Compare: no key typed in the dialog reaches the review keys on `document`.
        e.stopPropagation();
        if (e.key === "Escape") {
          e.preventDefault();
          close();
        }
      }}
    >
      <header className="editor__head">
        <h2 id="editor-title" className="editor__title">
          Edit structure
        </h2>
        <GlassButton tint="clear" size="sm" disabled={saving} onClick={close}>
          Close
        </GlassButton>
      </header>

      <form className="editor__smiles" onSubmit={submit}>
        <label className="mono-label editor__label" htmlFor="editor-smiles">
          SMILES
        </label>
        <input
          ref={field}
          id="editor-smiles"
          className="editor__input"
          value={smiles}
          onChange={(e) => setSmiles(e.target.value)}
          spellCheck={false}
          autoComplete="off"
          autoCapitalize="off"
          autoCorrect="off"
        />
        <GlassButton tint="green" size="sm" type="submit" disabled={saving || !fieldChanged}>
          Save SMILES
        </GlassButton>
      </form>

      {error ? (
        <p className="editor__error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="editor__frame" aria-busy={!ready}>
        {ready ? null : <p className="editor__loading">Loading editor…</p>}
        {/* sandbox is kept with the frame's own CSP; same-origin, it does not isolate the
            frame from the app: the bridge's source and origin checks do that. */}
        <iframe
          ref={iframe}
          className="editor__ketcher"
          title="Structure editor"
          src="/ketcher/"
          sandbox="allow-scripts allow-same-origin"
        />
      </div>
    </dialog>
  );
}
