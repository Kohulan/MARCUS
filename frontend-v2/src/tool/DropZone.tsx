import { useEffect, useRef, useState } from "react";
import type { DragEvent, ReactNode } from "react";
import { TOO_LARGE } from "../api/client";
import { ENGINES } from "../api/engines";
import type { Engine } from "../api/types";
import { GlassButton } from "../ui/GlassButton";
import "./tool.css";

/** What the backend takes (marcus/api/uploads.py): a PDF, or one PNG, JPEG, TIFF or WebP image. */
export const MAX_BYTES = 20 * 1024 * 1024;
export const WRONG_TYPE = "Use a PDF or a PNG, JPEG, TIFF or WebP image.";
const ONE_FILE = "Drop one file at a time.";

export type FileKind = "pdf" | "image";

const BY_TYPE: Record<string, FileKind> = {
  "application/pdf": "pdf",
  "image/png": "image",
  "image/jpeg": "image",
  "image/tiff": "image",
  "image/webp": "image",
};

// Some systems give no type for a TIFF or WebP: then the extension decides. The server
// checks the bytes either way.
const BY_EXTENSION: Record<string, FileKind> = {
  pdf: "pdf",
  png: "image",
  jpg: "image",
  jpeg: "image",
  tif: "image",
  tiff: "image",
  webp: "image",
};

const ACCEPT = [...Object.keys(BY_TYPE), ...Object.keys(BY_EXTENSION).map((e) => `.${e}`)].join(
  ",",
);

/** "pdf", "image", or null for a type the backend refuses. */
function fileKind(file: File): FileKind | null {
  const byType = BY_TYPE[file.type];
  if (byType) return byType;
  if (file.type !== "" && file.type !== "application/octet-stream") return null;
  const ext = file.name.toLowerCase().split(".").pop() ?? "";
  return BY_EXTENSION[ext] ?? null;
}


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
  /** Open the file picker once on mount (the landing's "Upload a PDF"). */
  openPicker: boolean;
  onPickerOpened: () => void;
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
  openPicker,
  onPickerOpened,
  message,
  wait,
}: DropZoneProps) {
  const input = useRef<HTMLInputElement>(null);
  const opened = useRef(false);
  const [over, setOver] = useState(false);

  useEffect(() => {
    if (!openPicker || opened.current) return;
    opened.current = true; // StrictMode runs this effect twice; the picker opens once
    input.current?.click();
    onPickerOpened();
  }, [openPicker, onPickerOpened]);

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
          <p className="drop__busy" role="status">
            {busy}
          </p>
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
