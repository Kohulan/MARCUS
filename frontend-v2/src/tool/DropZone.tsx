import { useEffect, useRef, useState } from "react";
import type { DragEvent, ReactNode } from "react";
import { TOO_LARGE } from "../api/client";
import { ENGINES } from "../api/engines";
import type { Engine } from "../api/types";
import { GlassButton } from "../ui/GlassButton";
import ProgressBar from "../ui/ProgressBar";
import { ACCEPT, fileKind, MAX_BYTES, type FileKind } from "./files";
import "./tool.css";

export const WRONG_TYPE = "Use a PDF or a PNG, JPEG, TIFF or WebP image.";
const ONE_FILE = "Drop one file at a time.";

type DropZoneProps = {
  engine: Engine;
  onEngine: (engine: Engine) => void;
  /** `ocsr` auto (true) or off (false); PDFs only. */
  auto: boolean;
  onAuto: (auto: boolean) => void;
  /** A file the browser accepts: the right type and at most 20 MB. */
  onFile: (file: File, kind: FileKind) => void;
  /** A file refused in the browser, with the reason. */
  onRefuse: (reason: string) => void;
  /** What is being uploaded, or null. Everything is disabled meanwhile. */
  busy: string | null;
  /** Problems of the last try (refused file, upload error), shown in the drop area. */
  message: ReactNode;
  /** A live countdown shown under the message, outside the alert (never re-announced). */
  wait?: ReactNode;
};

/**
 * The upload strip of the tool home: one drop area, the engine and the "find structures"
 * switch, and the file button. Checks type and size before anything is sent.
 */
export default function DropZone({
  engine,
  onEngine,
  auto,
  onAuto,
  onFile,
  onRefuse,
  busy,
  message,
  wait,
}: DropZoneProps) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  // A file dropped beside the drop area would make the browser leave the tool to show it.
  useEffect(() => {
    const keep = (e: globalThis.DragEvent) => {
      if (e.dataTransfer?.types.includes("Files")) e.preventDefault();
    };
    window.addEventListener("dragover", keep);
    window.addEventListener("drop", keep);
    return () => {
      window.removeEventListener("dragover", keep);
      window.removeEventListener("drop", keep);
    };
  }, []);

  function take(files: FileList | File[] | null | undefined) {
    const list = files ? Array.from(files) : [];
    if (list.length === 0) return;
    if (list.length > 1) return onRefuse(ONE_FILE);
    const file = list[0]!;
    const kind = fileKind(file);
    if (kind === null) return onRefuse(WRONG_TYPE);
    if (file.size > MAX_BYTES) return onRefuse(TOO_LARGE);
    onFile(file, kind);
  }

  function onDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    if (busy) {
      e.dataTransfer.dropEffect = "none";
      return;
    }
    e.dataTransfer.dropEffect = "copy";
    setOver(true);
  }

  function onDragLeave(e: DragEvent<HTMLDivElement>) {
    if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
    setOver(false);
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setOver(false);
    if (!busy) take(e.dataTransfer.files);
  }

  const areaClass = ["drop__area", over ? "drop__area--over" : "", busy ? "drop__area--busy" : ""]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="drop">
      <div
        className={areaClass}
        data-testid="drop-area"
        onDragOver={onDragOver}
        onDragEnter={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        <span className="drop__mark" aria-hidden="true" />
        <h1 className="drop__title">Drop a PDF here</h1>
        <p className="drop__hint">or one structure image · PNG, JPEG, TIFF, WebP · max 20 MB</p>
        {busy ? (
          <div className="drop__progress">
            <p className="drop__busy" role="status">
              {busy}
            </p>
            {/* fetch reports no upload progress: the indeterminate bar, no number */}
            <ProgressBar value={null} label="Upload" size="sm" />
          </div>
        ) : null}
        <div className="drop__message" role="alert">
          {message}
        </div>
        {wait}
      </div>

      <div className="drop__options">
        <label className="field">
          <span className="mono-label field__label">Engine</span>
          <select
            className="field__select"
            value={engine}
            disabled={busy !== null}
            onChange={(e) => onEngine(e.target.value as Engine)}
          >
            {ENGINES.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </select>
        </label>
        <label className="switch">
          <input
            type="checkbox"
            role="switch"
            className="switch__input"
            aria-label="Find structures automatically"
            checked={auto}
            disabled={busy !== null}
            onChange={(e) => onAuto(e.target.checked)}
          />
          <span className="switch__text">
            Find structures automatically
            <span className="switch__note">PDF only</span>
          </span>
        </label>
      </div>

      <div className="drop__cta glassbed">
        <GlassButton tint="orange" disabled={busy !== null} onClick={() => input.current?.click()}>
          Choose a file<span aria-hidden="true">→</span>
        </GlassButton>
        <input
          ref={input}
          type="file"
          className="visually-hidden"
          accept={ACCEPT}
          tabIndex={-1}
          aria-hidden="true"
          onChange={(e) => {
            take(e.target.files);
            e.target.value = ""; // the same file can be chosen again
          }}
        />
      </div>
    </div>
  );
}
