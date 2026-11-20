// COCONUT batch submit: a modal sheet opened from the paper ("Send N to COCONUT"). Login
// first (the curator's own COCONUT account), then the paper's fields filled once and
// inherited by every structure, a row per structure for its own values, and the results.
// Structures this browser already sent for the paper, and those whose send ended without an
// answer ("Unknown": they may be in COCONUT), are left out unless the curator ticks
// "Send again" and confirms. One submit at a time; the dialog stays open while it runs.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { GlassButton } from "../ui/GlassButton";
import { Modal } from "../ui/modal";
import { structureTag } from "../ui/tag";
import {
  AUTH_ERROR,
  buildReport,
  clearToken,
  getToken,
  markSent,
  markUnknown,
  organismsFor,
  sentIds,
  submitReports,
  UNKNOWN_ERROR,
  unknownIds,
} from "./coconutApi";
import CoconutLogin from "./CoconutLogin";
import SubmitResults from "./SubmitResults";
import type {
  OrganismDraft,
  PaperFields,
  StructureFields,
  SubmitResult,
  SubmitStructure,
} from "./types";
import "./coconut.css";

export type SubmitFormProps = {
  /** The paper: its id keys the "already sent" record; title and DOI fill the form. */
  paper: { id: string; title: string | null; doi: string | null };
  /** The accepted structures to send, in (page, idx) order. */
  structures: SubmitStructure[];
  /** Starting values for the paper's fields (for example a submission title). */
  initial?: Partial<PaperFields>;
  /** Said by the organisms when their starting values are a model's suggestion. */
  organismsNote?: string | undefined;
  onClose: () => void;
};

type Phase =
  | { kind: "form" }
  | { kind: "sending"; done: number; total: number }
  | { kind: "results"; results: SubmitResult[]; structures: SubmitStructure[] };

const EMPTY_ORGANISM: OrganismDraft = { name: "", parts: "", location: "", ecosystems: "" };

function startFields(
  paper: SubmitFormProps["paper"],
  initial: Partial<PaperFields> | undefined,
): PaperFields {
  return {
    title: initial?.title ?? "",
    doi: initial?.doi ?? paper.doi ?? "",
    evidence: initial?.evidence ?? paper.title ?? "",
    comment: initial?.comment ?? "",
    organisms: initial?.organisms?.length ? initial.organisms : [EMPTY_ORGANISM],
  };
}

function startRows(structures: SubmitStructure[]): Record<string, StructureFields> {
  return Object.fromEntries(
    structures.map((s) => [s.segmentId, { name: s.name ?? "", structuralComments: "" }]),
  );
}

export default function SubmitForm({
  paper,
  structures,
  initial,
  organismsNote,
  onClose,
}: SubmitFormProps) {
  const [token, setToken] = useState<string | null>(() => getToken());
  const [fields, setFields] = useState<PaperFields>(() => startFields(paper, initial));
  const [rows, setRows] = useState(() => startRows(structures));
  const [sent, setSent] = useState<Set<string>>(() => sentIds(paper.id));
  const [unknown, setUnknown] = useState<Set<string>>(() => unknownIds(paper.id));
  const [again, setAgain] = useState<Set<string>>(() => new Set());
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [phase, setPhase] = useState<Phase>({ kind: "form" });
  const busy = useRef(false);
  // What the form started with, to ask before Close throws typed values away.
  const snapshot = JSON.stringify([fields, rows]);
  const [startSnapshot] = useState(snapshot);

  function close() {
    if (busy.current) return;
    const typed = phase.kind === "form" && token !== null && snapshot !== startSnapshot;
    if (typed && !window.confirm("Close and lose what you typed?")) return;
    onClose();
  }

  // showModal focuses the first button (Close): start in the first field instead, also when
  // the form appears after the login or "Back to form". The results focus their own heading.
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (phase.kind === "form") dialog.current?.querySelector<HTMLElement>("input, textarea")?.focus();
  }, [phase.kind, token]);

  const rowOf = (id: string): StructureFields => rows[id] ?? { name: "", structuralComments: "" };
  const held = (id: string) => sent.has(id) || unknown.has(id);
  const toSend = structures.filter((s) => !held(s.segmentId) || again.has(s.segmentId));
  const unnamed = toSend.filter((s) => !rowOf(s.segmentId).name.trim()).length;
  const noOrganism = toSend.some((s) => organismsFor(fields, rowOf(s.segmentId)).length === 0);
  const missing = [
    !fields.title.trim() && "title",
    !fields.evidence.trim() && "evidence",
    noOrganism && "organism",
  ].filter(Boolean);
  const problem =
    missing.length > 0
      ? `Fill in ${missing.join(", ")}`
      : unnamed > 0
        ? `${unnamed} ${unnamed === 1 ? "structure needs" : "structures need"} a name`
        : null;
  const sending = phase.kind === "sending";
  const canSend = toSend.length > 0 && problem === null && !sending && token !== null;

  function setPaper<K extends keyof PaperFields>(key: K, value: PaperFields[K]) {
    setFields((f) => ({ ...f, [key]: value }));
  }

  function setOrganism(i: number, change: Partial<OrganismDraft>) {
    setFields((f) => ({
      ...f,
      organisms: f.organisms.map((o, j) => (j === i ? { ...o, ...change } : o)),
    }));
  }

  function setRow(id: string, change: Partial<StructureFields>) {
    setRows((r) => ({ ...r, [id]: { name: "", structuralComments: "", ...r[id], ...change } }));
  }

  function setRowOrganism(id: string, change: Partial<OrganismDraft>) {
    setRows((r) => {
      const cur = r[id] ?? { name: "", structuralComments: "" };
      return {
        ...r,
        [id]: { ...cur, organism: { ...(cur.organism ?? EMPTY_ORGANISM), ...change } },
      };
    });
  }

  function toggle(set: Set<string>, id: string, on: boolean): Set<string> {
    const next = new Set(set);
    if (on) next.add(id);
    else next.delete(id);
    return next;
  }

  function sendAgain(id: string, on: boolean) {
    const ask = sent.has(id)
      ? "This structure is already in COCONUT. Send it again?"
      : "COCONUT may already have this structure. Check COCONUT first. Send it again?";
    if (on && !window.confirm(ask)) return;
    setAgain((a) => toggle(a, id, on));
  }

  async function send() {
    if (busy.current || !canSend || token === null) return;
    busy.current = true;
    const list = toSend;
    const items = list.map((s) => ({
      segmentId: s.segmentId,
      report: buildReport(fields, s, rowOf(s.segmentId)),
    }));
    setPhase({ kind: "sending", done: 0, total: items.length });
    const results = await submitReports(token, items, (done, total, chunk) => {
      const ok = chunk.filter((r) => r.ok).map((r) => r.segmentId);
      const lost = chunk.filter((r) => !r.ok && r.error === UNKNOWN_ERROR).map((r) => r.segmentId);
      markSent(paper.id, ok);
      markUnknown(paper.id, lost);
      setSent((s) => new Set([...s, ...ok]));
      setUnknown((u) => new Set([...u].filter((id) => !ok.includes(id)).concat(lost)));
      setPhase({ kind: "sending", done, total });
    });
    if (results.some((r) => !r.ok && r.error === AUTH_ERROR)) {
      clearToken();
      setToken(null);
    }
    setAgain(new Set());
    busy.current = false;
    setPhase({ kind: "results", results, structures: list });
  }

  function logOut() {
    clearToken();
    setToken(null);
  }

  let body;
  if (phase.kind === "results") {
    body = (
      <SubmitResults
        structures={phase.structures}
        results={phase.results}
        onBack={() => setPhase({ kind: "form" })}
        onClose={close}
      />
    );
  } else if (token === null) {
    body = (
      <div className="coconut__login">
        <CoconutLogin onLoggedIn={setToken} />
      </div>
    );
  } else {
    body = (
      // Enter in a field never sends: only the button does.
      <form className="coconut__form" onSubmit={(e) => e.preventDefault()}>
        <div className="coconut__columns">
          <fieldset className="coconut-paper" disabled={sending}>
            <legend className="coconut-paper__legend">Paper</legend>
            <Field id="coconut-title" label="Title" required>
              <input
                id="coconut-title"
                className="coconut-input"
                aria-required="true"
                value={fields.title}
                onChange={(e) => setPaper("title", e.target.value)}
              />
            </Field>
            <Field id="coconut-doi" label="DOI">
              <input
                id="coconut-doi"
                className="coconut-input coconut-input--mono"
                value={fields.doi}
                onChange={(e) => setPaper("doi", e.target.value)}
                spellCheck={false}
              />
            </Field>
            <Field id="coconut-evidence" label="Evidence" required>
              <textarea
                id="coconut-evidence"
                className="coconut-input coconut-input--area"
                aria-required="true"
                rows={3}
                value={fields.evidence}
                onChange={(e) => setPaper("evidence", e.target.value)}
              />
            </Field>
            <Field id="coconut-comment" label="Comment">
              <textarea
                id="coconut-comment"
                className="coconut-input coconut-input--area"
                rows={2}
                value={fields.comment}
                onChange={(e) => setPaper("comment", e.target.value)}
              />
            </Field>
            {organismsNote ? (
              <p id="coconut-org-note" className="mono-label coconut-paper__note">
                {organismsNote}
              </p>
            ) : null}
            {fields.organisms.map((o, i) => (
              <OrganismFields
                key={i}
                idBase={`coconut-org-${i}`}
                describedBy={organismsNote ? "coconut-org-note" : undefined}
                label={i === 0 ? "Organism" : `Organism ${i + 1}`}
                required={i === 0}
                value={o}
                onChange={(change) => setOrganism(i, change)}
                onRemove={
                  i > 0
                    ? () =>
                        setFields((f) => ({
                          ...f,
                          organisms: f.organisms.filter((_, j) => j !== i),
                        }))
                    : undefined
                }
              />
            ))}
            <div className="coconut-paper__add">
              <GlassButton
                tint="clear"
                size="sm"
                disabled={sending}
                onClick={() =>
                  setFields((f) => ({ ...f, organisms: [...f.organisms, EMPTY_ORGANISM] }))
                }
              >
                Add organism
              </GlassButton>
            </div>
          </fieldset>

          <div className="coconut-structures">
            <div className="coconut-structures__head" aria-hidden="true">
              <span className="mono-label">Structure</span>
              <span className="mono-label">Name</span>
            </div>
            <ol className="coconut-rows">
              {structures.map((s) => {
                const id = s.segmentId;
                const row = rowOf(id);
                const wasSent = sent.has(id);
                const isUnknown = !wasSent && unknown.has(id);
                const open = expanded.has(id);
                const tagId = `coconut-tag-${id}`;
                const moreId = `coconut-more-${id}`;
                const out = held(id) && !again.has(id);
                return (
                  <li
                    key={id}
                    aria-labelledby={tagId}
                    className={out ? "coconut-row coconut-row--out" : "coconut-row"}
                  >
                    <span id={tagId} className="coconut-row__tag">
                      {structureTag(s.n)}
                    </span>
                    <code className="coconut-row__smiles" title={s.smiles}>
                      {s.smiles}
                    </code>
                    <input
                      className="coconut-input coconut-row__name"
                      aria-label={`Name for structure ${s.n}`}
                      aria-required={!out}
                      placeholder="Name"
                      value={row.name}
                      disabled={sending}
                      onChange={(e) => setRow(id, { name: e.target.value })}
                    />
                    <span className="coconut-row__state">
                      {wasSent || isUnknown ? (
                        <>
                          {wasSent ? (
                            <span className="coconut-row__sent">Already sent</span>
                          ) : (
                            <span className="coconut-row__sent coconut-row__sent--unknown">
                              Unknown
                            </span>
                          )}
                          <label className="coconut-row__again">
                            <input
                              type="checkbox"
                              checked={again.has(id)}
                              disabled={sending}
                              onChange={(e) => sendAgain(id, e.target.checked)}
                            />
                            Send again
                          </label>
                        </>
                      ) : null}
                    </span>
                    <button
                      type="button"
                      className="coconut-row__more"
                      aria-expanded={open}
                      aria-controls={open ? moreId : undefined}
                      aria-describedby={tagId}
                      onClick={() => setExpanded((x) => toggle(x, id, !open))}
                    >
                      More
                    </button>
                    {open ? (
                      <fieldset id={moreId} className="coconut-row__detail" disabled={sending}>
                        <legend className="visually-hidden">Own values for {structureTag(s.n)}</legend>
                        <Field id={`${moreId}-comment`} label="Comment">
                          <textarea
                            id={`${moreId}-comment`}
                            className="coconut-input coconut-input--area"
                            rows={2}
                            placeholder={fields.comment || "As the paper"}
                            value={row.comment ?? ""}
                            onChange={(e) => setRow(id, { comment: e.target.value })}
                          />
                        </Field>
                        <Field id={`${moreId}-structural`} label="Structural comments">
                          <textarea
                            id={`${moreId}-structural`}
                            className="coconut-input coconut-input--area"
                            rows={2}
                            value={row.structuralComments}
                            onChange={(e) => setRow(id, { structuralComments: e.target.value })}
                          />
                        </Field>
                        <OrganismFields
                          idBase={`${moreId}-org`}
                          label="Organism"
                          placeholder={fields.organisms[0]?.name || "As the paper"}
                          value={row.organism ?? EMPTY_ORGANISM}
                          onChange={(change) => setRowOrganism(id, change)}
                        />
                      </fieldset>
                    ) : null}
                  </li>
                );
              })}
            </ol>
          </div>
        </div>

        <footer className="coconut__foot glassbed">
          <p id="coconut-status" className="coconut__status" role="status" aria-live="polite">
            {sending ? `Sent ${phase.done} of ${phase.total}` : (token && problem) || ""}
          </p>
          <GlassButton
            tint="green"
            disabled={!canSend}
            describedBy="coconut-status"
            onClick={() => void send()}
          >
            {`Send ${toSend.length} to COCONUT`}
          </GlassButton>
        </footer>
      </form>
    );
  }

  return (
    <Modal
      box={dialog}
      className="coconut"
      labelledBy="coconut-title-head"
      onClose={close}
      busy={sending}
    >
      <header className="coconut__head">
        <h2 id="coconut-title-head" className="coconut__title">
          Send to COCONUT
        </h2>
        <div className="coconut__head-actions">
          {token !== null && phase.kind === "form" ? (
            <GlassButton tint="clear" size="sm" onClick={logOut}>
              Log out
            </GlassButton>
          ) : null}
          <GlassButton tint="clear" size="sm" disabled={sending} onClick={close}>
            Close
          </GlassButton>
        </div>
      </header>
      {body}
    </Modal>
  );
}

type FieldProps = { id: string; label: string; required?: boolean | undefined; children: ReactNode };

/**
 * A labelled field. Required: a visible "Required" beside the label, kept out of the name
 * (the input carries aria-required, so a screen reader hears the state with the name).
 */
function Field({ id, label, required, children }: FieldProps) {
  const name = (
    <label className="mono-label coconut-field__label" htmlFor={id}>
      {label}
    </label>
  );
  return (
    <div className="coconut-field">
      {required ? (
        <span className="coconut-field__head">
          {name}
          <span className="mono-label coconut-field__req" aria-hidden="true">
            · Required
          </span>
        </span>
      ) : (
        name
      )}
      {children}
    </div>
  );
}

type OrganismFieldsProps = {
  idBase: string;
  label: string;
  placeholder?: string;
  /** The paper's first organism: required unless every structure has its own. */
  required?: boolean | undefined;
  value: OrganismDraft;
  onChange: (change: Partial<OrganismDraft>) => void;
  onRemove?: (() => void) | undefined;
  /** Id of a note about the starting values (a model's suggestion). */
  describedBy?: string | undefined;
};

/** An organism: name, parts, one location and its ecosystems (lists are comma-separated). */
function OrganismFields({
  idBase,
  label,
  placeholder,
  required,
  value,
  onChange,
  onRemove,
  describedBy,
}: OrganismFieldsProps) {
  return (
    <div className="coconut-organism">
      <div className="coconut-organism__name">
        <Field id={`${idBase}-name`} label={label} required={required}>
          <input
            id={`${idBase}-name`}
            className="coconut-input"
            aria-required={required || undefined}
            aria-describedby={describedBy}
            placeholder={placeholder}
            value={value.name}
            onChange={(e) => onChange({ name: e.target.value })}
          />
        </Field>
        {onRemove ? (
          <button type="button" className="coconut-organism__remove" onClick={onRemove}>
            Remove
          </button>
        ) : null}
      </div>
      <div className="coconut-organism__grid">
        <Field id={`${idBase}-parts`} label="Parts">
          <input
            id={`${idBase}-parts`}
            className="coconut-input"
            placeholder="Comma-separated"
            value={value.parts}
            onChange={(e) => onChange({ parts: e.target.value })}
          />
        </Field>
        <Field id={`${idBase}-location`} label="Location">
          <input
            id={`${idBase}-location`}
            className="coconut-input"
            value={value.location}
            onChange={(e) => onChange({ location: e.target.value })}
          />
        </Field>
        <Field id={`${idBase}-eco`} label="Ecosystems">
          <input
            id={`${idBase}-eco`}
            className="coconut-input"
            placeholder="Comma-separated"
            value={value.ecosystems}
            onChange={(e) => onChange({ ecosystems: e.target.value })}
          />
        </Field>
      </div>
    </div>
  );
}
