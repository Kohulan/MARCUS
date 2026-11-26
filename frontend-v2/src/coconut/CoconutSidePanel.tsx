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
import { saveBlob } from "../ui/saveBlob";
import {
  buildReport,
  getToken,
  loginEnded,
  missingFields,
  NOT_SENT_ERROR,
  recordResults,
  sentIds,
  submitReports,
  unknownIds,
} from "./coconutApi";
import CoconutLogin from "./CoconutLogin";
import { type BuiltFrom, jsonFileName, marcusJson, sideStart, sideStructure } from "./sideForm";
import { EMPTY_ORGANISM, Field, OrganismFields } from "./SubmitForm";
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

export default function CoconutSidePanel({ paper, segment, n, start, built, row, onClose }: Props) {
  const id = useId();
  // the typed fields start from what MARCUS knows when the form opens
  const [first] = useState(() => sideStart(segment, paper, start, built, row));
  const [paperFields, setPaper] = useState<PaperFields>(first.paper);
  const [fields, setFields] = useState<StructureFields>(first.fields);
  const [token, setToken] = useState<string | null>(() => getToken());
  const [busy, setBusy] = useState(false);
  const busyNow = useRef(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [sent, setSent] = useState(
    () => sentIds(paper.id).has(segment.id) || unknownIds(paper.id).has(segment.id),
  );
  const heading = useRef<HTMLHeadingElement>(null);
  // what can be sent is the structure the card shows NOW (an edit or a new read counts); the
  // typed fields keep what the curator wrote
  const { structure, heldReason } = sideStructure(segment, n, paper.engine);
  const tag = structureTag(n);
  const organism = paperFields.organisms[0] ?? EMPTY_ORGANISM;
  // only the organism the form shows is sent
  const shownPaper: PaperFields = {
    ...paperFields,
    organisms: organism.name.trim() ? [organism] : [],
  };
  const missing = [
    ...(fields.name.trim() ? [] : ["name"]),
    ...missingFields(shownPaper, [fields]),
  ];
  const fill = missing.length > 0 ? `Fill in ${missing.join(", ")}` : null;
  const suggested = start.note !== undefined && organism.name === start.organisms[0]?.name;

  useEffect(() => heading.current?.focus(), []);

  const setOrganism = (change: Partial<OrganismDraft>) =>
    setPaper((p) => ({ ...p, organisms: [{ ...organism, ...change }, ...p.organisms.slice(1)] }));

  async function send() {
    if (!structure || !token || busyNow.current || fill !== null) return;
    if (sent && !window.confirm(`${tag} was sent before. Send it again?`)) return;
    busyNow.current = true;
    setBusy(true);
    setProblem(null);
    const report = buildReport(shownPaper, structure, fields);
    const results = await submitReports(token, [{ segmentId: segment.id, report }]); // never rejects
    // sent, or no answer (it may be in COCONUT): either way the next send asks first
    const { ok, lost } = recordResults(paper.id, results);
    if (ok.length + lost.length > 0) setSent(true);
    if (loginEnded(results)) setToken(null); // the login comes back at the end of the form
    const result = results[0];
    if (!result?.ok) setProblem(result?.error ?? NOT_SENT_ERROR);
    busyNow.current = false;
    setBusy(false);
  }

  function download() {
    if (!structure) return;
    const doc = marcusJson(paper, segment, structure, shownPaper, fields, built, row);
    saveBlob(
      new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" }),
      jsonFileName(paper.id, segment.compound_id, n),
    );
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
          <OrganismFields
            idBase={`${id}-org`}
            label="Organism"
            value={organism}
            onChange={setOrganism}
            describedBy={suggested ? `${id}-note` : undefined}
          />
          {suggested && (
            <p id={`${id}-note`} className="coconut-side__note">
              {start.note}
            </p>
          )}
          {input("doi", "DOI")}
          {input("title", "Title")}
          {input("evidence", "Evidence", true)}
          {input("comment", "Comment", true)}
          <Field id={`${id}-sc`} label="Structural comments">
            <textarea id={`${id}-sc`} className="coconut-input" rows={2} value={fields.structuralComments}
              onChange={(e) => setFields((f) => ({ ...f, structuralComments: e.target.value }))} />
          </Field>
          {sent && <p className="coconut-side__sent">Sent to COCONUT</p>}
          {fill !== null && token !== null && <p className="coconut-side__note">{fill}</p>}
          {problem !== null && (
            <p className="coconut-side__problem" role="alert">
              {problem}
            </p>
          )}
          <div className="coconut-side__actions glassbed">
            {token !== null && (
              <GlassButton tint="green" disabled={busy || fill !== null} onClick={() => void send()}>
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
