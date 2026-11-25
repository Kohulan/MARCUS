// The Paper view's COCONUT side form (owner decision 2026-11-25): one accepted structure, its
// form filled as far as MARCUS knows; the COCONUT login at the end when there is no token, and
// the same content as MARCUS JSON for a curator who sends later.
import { useEffect, useId, useRef, useState } from "react";
import { api } from "../api/client";
import { depictionKey } from "../api/depictionKey";
import type { PaperDetail, RgroupRow, SegmentOut } from "../api/types";
import { GlassButton } from "../ui/GlassButton";
import { structureTag } from "../ui/tag";
import type { CoconutStart } from "../workspace/coconutList";
import { buildReport, getToken, markSent, sentIds, submitReports } from "./coconutApi";
import CoconutLogin from "./CoconutLogin";
import { type BuiltFrom, jsonFileName, marcusJson, sideStart } from "./sideForm";
import { Field, OrganismFields } from "./SubmitForm";
import type { OrganismDraft, PaperFields, StructureFields } from "./types";
import "./coconut.css";

type Props = {
  paper: PaperDetail;
  segment: SegmentOut;
  /** The structure's [nn] number. */
  n: number;
  start: CoconutStart;
  built: BuiltFrom | null;
  /** The scaffold's row this structure was built from (null otherwise). */
  row: RgroupRow | null;
  onClose: () => void;
};

const EMPTY: OrganismDraft = { name: "", parts: "", location: "", ecosystems: "" };

export default function CoconutSidePanel({ paper, segment, n, start, built, row, onClose }: Props) {
  const id = useId();
  const first = useRef(sideStart(segment, n, paper, start, built, row));
  const [paperFields, setPaper] = useState<PaperFields>(first.current.paper);
  const [fields, setFields] = useState<StructureFields>(first.current.fields);
  const [token, setToken] = useState<string | null>(() => getToken());
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [sent, setSent] = useState(() => sentIds(paper.id).has(segment.id));
  const heading = useRef<HTMLHeadingElement>(null);
  const { structure, heldReason } = first.current;
  const tag = structureTag(n);
  const organism = paperFields.organisms[0] ?? EMPTY;

  useEffect(() => heading.current?.focus(), []);

  const setOrganism = (change: Partial<OrganismDraft>) =>
    setPaper((p) => ({ ...p, organisms: [{ ...organism, ...change }, ...p.organisms.slice(1)] }));

  async function send() {
    if (!structure || !token || busy) return;
    if (sent && !window.confirm(`${tag} was sent before. Send it again?`)) return;
    setBusy(true);
    setProblem(null);
    try {
      const report = buildReport(paperFields, structure, fields);
      const [result] = await submitReports(token, [{ segmentId: segment.id, report }]);
      if (result?.ok) {
        markSent(paper.id, [segment.id]);
        setSent(true);
      } else {
        setProblem(result && !result.ok ? result.error : "Not sent");
      }
    } catch (err) {
      setProblem(err instanceof Error ? err.message : "Not sent");
    } finally {
      setBusy(false);
    }
  }

  function download() {
    if (!structure) return;
    const doc = marcusJson(paper, segment, n, structure, paperFields, fields, built, row);
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = jsonFileName(paper.id, segment.compound_id, n);
    a.click();
    URL.revokeObjectURL(url);
  }

  const input = (key: keyof PaperFields, label: string, multiline = false) => {
    const fid = `${id}-${key}`;
    const value = paperFields[key] as string;
    const change = (v: string) => setPaper((p) => ({ ...p, [key]: v }));
    return (
      <Field id={fid} label={label}>
        {multiline ? (
          <textarea id={fid} className="coconut-input" rows={2} value={value}
            onChange={(e) => change(e.target.value)} />
        ) : (
          <input id={fid} className="coconut-input" value={value}
            onChange={(e) => change(e.target.value)} />
        )}
      </Field>
    );
  }; // fmt: skip

  return (
    <aside
      className="coconut-side"
      aria-labelledby={`${id}-title`}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onClose();
        }
      }}
    >
      <div className="coconut-side__head">
        <h2 id={`${id}-title`} className="coconut-side__title" tabIndex={-1} ref={heading}>
          {`COCONUT ${tag}`}
        </h2>
        <GlassButton tint="clear" size="sm" onClick={onClose}>
          Close
        </GlassButton>
      </div>
      <img
        className="coconut-side__drawing"
        src={api.depictionUrl(segment.id, depictionKey(segment))}
        alt={`Structure ${tag}`}
      />
      {heldReason !== null ? (
        <p className="coconut-side__held">{heldReason}</p>
      ) : (
        <div className="coconut-side__fields">
          <Field id={`${id}-name`} label="Name">
            <input id={`${id}-name`} className="coconut-input" value={fields.name}
              onChange={(e) => setFields((f) => ({ ...f, name: e.target.value }))} />
          </Field>
          <OrganismFields idBase={`${id}-org`} label="Organism" value={organism} onChange={setOrganism} />
          {input("doi", "DOI")}
          {input("title", "Title")}
          {input("evidence", "Evidence", true)}
          {input("comment", "Comment", true)}
          <Field id={`${id}-sc`} label="Structural comments">
            <textarea id={`${id}-sc`} className="coconut-input" rows={2} value={fields.structuralComments}
              onChange={(e) => setFields((f) => ({ ...f, structuralComments: e.target.value }))} />
          </Field>
          {sent && <p className="coconut-side__sent">Sent to COCONUT</p>}
          {problem !== null && (
            <p className="coconut-side__problem" role="alert">
              {problem}
            </p>
          )}
          <div className="coconut-side__actions glassbed">
            {token !== null && (
              <GlassButton tint="green" disabled={busy} onClick={() => void send()}>
                Send to COCONUT
              </GlassButton>
            )}
            <GlassButton tint="clear" onClick={download}>
              Download JSON
            </GlassButton>
          </div>
          {token === null && <CoconutLogin onLoggedIn={setToken} />}
        </div>
      )}
    </aside>
  );
}
