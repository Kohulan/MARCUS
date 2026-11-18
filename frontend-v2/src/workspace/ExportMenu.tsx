import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { api } from "../api/client";
import type { ExportFormat, ExportStatus } from "../api/types";
import { GlassButton } from "../ui/GlassButton";
import "./workspace.css";

const FORMATS: { format: ExportFormat; label: string }[] = [
  { format: "json", label: "JSON" },
  { format: "csv", label: "CSV" },
  { format: "sdf", label: "SDF" },
];

const SCOPES: { status: ExportStatus; label: string }[] = [
  { status: "accepted", label: "Accepted only" },
  { status: "all", label: "All" },
];

/**
 * Export: a disclosure with six plain download links (format × accepted only / all), laid
 * out as a small label table. Escape, a click outside or the focus leaving closes it.
 */
export default function ExportMenu({ paperId }: { paperId: string }) {
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

  function onKeyDown(e: KeyboardEvent) {
    if (e.key !== "Escape" || !open) return;
    e.stopPropagation(); // the review keys (F8) must not also see this Escape
    setOpen(false);
    button.current?.focus();
  }

  return (
    <div className="ws-export" ref={root} onKeyDown={onKeyDown}>
      <GlassButton
        ref={button}
        tint="clear"
        expanded={open}
        controls={open ? panelId : undefined}
        onClick={() => setOpen((o) => !o)}
      >
        Export
      </GlassButton>
      {open && (
        <div id={panelId} className="ws-export__panel" role="group" aria-label="Export">
          <table className="ws-export__table">
            <tbody>
              {FORMATS.map(({ format, label }) => (
                <tr key={format}>
                  <th scope="row">{label}</th>
                  {SCOPES.map(({ status, label: scope }) => (
                    <td key={status}>
                      <a
                        className="ws-export__link"
                        href={api.exportUrl(paperId, format, status)}
                        aria-label={`${label}, ${scope.toLowerCase()}`}
                      >
                        {scope}
                      </a>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
