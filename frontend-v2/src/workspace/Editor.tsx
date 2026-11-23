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
import ProgressBar from "../ui/ProgressBar";
import { Modal } from "../ui/modal";
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
 * structure still to check becomes accepted (a curator who fixed it has checked it: a
 * decision). Any other status stays, so the change has no status key (an edit that keeps the
 * status is no decision: on a main-figure structure it must not reach the repeats). No note
 * key, so curationBody keeps the stored note.
 */
export function editorChange(
  current: CurationOut | null,
  structure: EditorStructure,
): CurationChange {
  return !current || current.status === "unchecked" ? { status: "accepted", structure } : { structure };
}

export default function Editor({ initial, onSave, onClose }: EditorProps) {
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

  // Where the curator's focus was in the dialog (outside the frame), and when they last
  // pressed Tab: a marcus:unfocus puts the focus back there, unless they just tabbed into
  // the frame themselves.
  const lastFocus = useRef<HTMLElement | null>(null);
  const tabbedAt = useRef(-Infinity);
  useEffect(() => {
    const onFocus = (e: FocusEvent) => {
      if (e.target instanceof HTMLElement && e.target !== iframe.current) lastFocus.current = e.target;
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Tab") tabbedAt.current = performance.now();
    };
    document.addEventListener("focusin", onFocus);
    document.addEventListener("keydown", onKey, { capture: true });
    return () => {
      document.removeEventListener("focusin", onFocus);
      document.removeEventListener("keydown", onKey, { capture: true });
    };
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
          } else if (message.type === "marcus:unfocus") {
            const tabbedIn = performance.now() - tabbedAt.current < 1000;
            if (document.activeElement === iframe.current && !tabbedIn) {
              (lastFocus.current?.isConnected ? lastFocus.current : field.current)?.focus();
            }
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
    <Modal className="editor" labelledBy="editor-title" onClose={close} first={field}>
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
        {ready ? null : (
          <div className="editor__loading">
            <p>Loading editor…</p>
            <ProgressBar value={null} label="Loading editor" size="sm" />
          </div>
        )}
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
    </Modal>
  );
}
