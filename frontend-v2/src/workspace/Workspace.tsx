import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { isGone, isUuid } from "../api/client";
import { usePaper, useSteps } from "../api/queries";
import type { AnnotationOut, PaperDetail } from "../api/types";
import { heldOnlyReason } from "../coconut/held";
import SubmitForm from "../coconut/SubmitForm";
import type { OrganismDraft } from "../coconut/types";
import { coconutCountForDoi, coconutLabel, type CoconutDoiCount } from "../lookup/coconutDoi";
import { usePageTitle } from "../pages/meta";
import { GlassButton } from "../ui/GlassButton";
import GonePage, { OpenFailed } from "../ui/GonePage";
import { focusLost } from "../ui/focus";
import { paperName, structureTag } from "../ui/tag";
import { SegmentCompare } from "./Compare";
import ExportMenu from "./ExportMenu";
import FocusMode from "./FocusMode";
import PaperView from "./PaperView";
import ReviewGrid from "./ReviewGrid";
import { SegmentEditor } from "./SegmentEditor";
import { coconutStructures, submissionTitle } from "./coconutList";
import { CARD_OPEN_HINT, filterCounts, hasScaffold, segmentCard } from "./cardState";
import StatusBar from "./StatusBar";
import { useAnnotation, useAutoRunRefresh } from "./useAnnotation";
import { useCardActions } from "./useCardActions";
import { useReviewRows, type ReviewRow } from "./useReviewRows";
import { RgroupPaper, useRgroupList } from "./useRgroupRows";
import { useWorkspace, type Workspace as WorkspaceState, type WorkspaceView } from "./useWorkspace";
import "./workspace.css";

/** The COCONUT form's starting organisms, and the note they carry when they are the model's. */
type CoconutStart = { organisms: OrganismDraft[]; note: string | undefined };

/**
 * The annotation's organisms start the COCONUT form (the curator can change them), labelled as
 * the model's suggestion unless they come from the curator's corrections; COCONUT has no
 * kingdom field, so the kingdom is not carried over.
 */
function coconutStart(annotation: AnnotationOut | undefined): CoconutStart {
  const organisms = (annotation?.coconut?.organisms ?? []).map((o) => ({
    name: o.name,
    parts: o.parts,
    location: o.location,
    ecosystems: o.ecosystems,
  }));
  const suggested = organisms.length > 0 && annotation?.curated === null;
  return { organisms, note: suggested ? "Organisms: model suggestion" : undefined };
}

/**
 * How many structures COCONUT already has for the paper's DOI (null: unknown or no DOI).
 * An answer is kept for the tab (each open of the paper, each Back to it, reads it); no
 * answer is not kept, so the next open asks again.
 */
function useCoconutCount(doi: string | null): CoconutDoiCount | null {
  const query = useQuery({
    queryKey: ["coconut-doi", doi],
    queryFn: async ({ signal }) => {
      const count = await coconutCountForDoi(doi ?? "", signal);
      if (count === null) throw new Error("no answer from COCONUT");
      return count;
    },
    enabled: Boolean(doi),
    staleTime: Infinity,
    retry: false,
  });
  return (doi && query.data) || null;
}

export default function Workspace() {
  const id = useParams().id ?? "";
  if (!isUuid(id)) return <NoPaper />;
  return <PaperWorkspace key={id} id={id} />;
}

function NoPaper() {
  usePageTitle("Paper · MARCUS");
  return <GonePage noun="paper" />;
}

/**
 * /app/papers/:id. The paper is read first; only a paper that exists mounts the frame (and
 * with it the live stream). A 404 or 422, at first or on any later refresh (deleted in another
 * tab, expired), shows the one gone page and unmounts the frame, so no stream or poll is left.
 */
function PaperWorkspace({ id }: { id: string }) {
  const query = usePaper(id);
  useSteps(id); // asked for with the paper, not after it (the frame reads it)
  const gone = isGone(query.error);
  usePageTitle(!gone && query.data ? `${paperName(query.data)} · MARCUS` : "Paper · MARCUS");

  if (gone) return <GonePage noun="paper" />;
  if (query.data) return <Frame id={id} />;
  if (query.isError) {
    return <OpenFailed noun="paper" error={query.error} onRetry={() => void query.refetch()} />;
  }
  return (
    <main className="ws" aria-busy="true">
      <div className="ws-head">
        <div className="ws-head__title">
          <span className="ws-skeleton ws-skeleton--title" aria-hidden="true" />
          <span className="ws-skeleton ws-skeleton--meta" aria-hidden="true" />
          <p className="visually-hidden" role="status">
            Loading the paper…
          </p>
        </div>
      </div>
    </main>
  );
}

const VIEWS: { view: WorkspaceView; label: string }[] = [
  { view: "review", label: "Review" },
  { view: "paper", label: "Paper" },
];

function Frame({ id }: { id: string }) {
  const ws = useWorkspace(id);
  const paper = ws.paper;
  if (!paper) return null; // the outer component mounts the frame only with a paper
  return <PaperFrame ws={ws} paper={paper} />;
}

function PaperFrame({ ws, paper }: { ws: WorkspaceState; paper: PaperDetail }) {
  const reasonId = useId();
  const rows = useReviewRows(paper, ws.segments, ws.steps);
  const counts = useMemo(() => filterCounts(rows), [rows]);
  const review = useRef<HTMLDivElement>(null);
  // Esc in focus mode: the grid comes back with this segment's card selected and focused.
  const [returnTo, setReturnTo] = useState<string | null>(null);
  const picked =
    ws.view === "review" && ws.focus ? ws.segments.find((s) => s.id === ws.selection) : undefined;
  // A repeat of a main-figure structure has no row: focus mode shows that structure.
  const focused = picked?.repeat_of
    ? ws.segments.find((s) => s.id === picked.repeat_of)
    : picked;

  const { focus, selection, setSelection, closeFocus } = ws;
  useEffect(() => {
    if (returnTo === null || focus) return;
    setReturnTo(null);
    if (selection !== returnTo) setSelection(returnTo);
    (segmentCard(review.current, returnTo) ?? review.current)?.focus();
  }, [returnTo, focus, selection, setSelection]);

  const close = (segmentId: string) => {
    setReturnTo(segmentId);
    closeFocus();
  };

  const inCoconut = useCoconutCount(paper.doi);
  // Accepted structures that have one, numbered as their tags (all segments, before filters).
  const toCoconut = useMemo(
    () => coconutStructures(ws.segments, paper.engine),
    [ws.segments, paper.engine],
  );
  // The open form's starting organisms, fixed when it opens (a later change of the annotation
  // does not rewrite them); `waiting`: the annotation had not answered yet, so its first answer
  // still starts them (the form takes them only if the curator has not typed organisms).
  const [sending, setSending] = useState<(CoconutStart & { waiting: boolean }) | null>(null);
  const sendCount = toCoconut.send.length;
  const annotation = useAnnotation(paper.id).data;
  useAutoRunRefresh(paper.id, ws.steps);
  // R-group rows: one list for the paper's scaffolds, polled while a reading is in flight
  const scaffolds = useMemo(
    () => ws.segments.some((s) => hasScaffold(s, paper.engine)),
    [ws.segments, paper.engine],
  );
  useRgroupList(paper.id, scaffolds);
  if (sending?.waiting && annotation !== undefined) {
    setSending({ ...coconutStart(annotation), waiting: false });
  }
  return (
    <RgroupPaper.Provider value={paper.id}>
    <main className="ws">
      <header className="ws-head">
        <div className="ws-head__title">
          <h1 className="ws-title">{paperName(paper)}</h1>
          <p className="ws-meta">
            {paper.title?.trim() && <span className="ws-meta__file">{paper.display_name}</span>}
            {paper.doi && (
              <a
                className="ws-meta__doi"
                href={`https://doi.org/${encodeURI(paper.doi)}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                {paper.doi}
              </a>
            )}
            {inCoconut && (
              <a
                href={inCoconut.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {coconutLabel(inCoconut)}
              </a>
            )}
          </p>
        </div>
        <div className="ws-head__actions glassbed">
          <ExportMenu paperId={paper.id} annotated={Boolean(annotation?.values)} />
          <div className="ws-send">
            <GlassButton
              tint="green"
              disabled={sendCount === 0}
              describedBy={sendCount === 0 ? reasonId : undefined}
              hasPopup="dialog"
              onClick={() =>
                setSending({ ...coconutStart(annotation), waiting: annotation === undefined })
              }
            >
              {`Send ${sendCount} to COCONUT`}
            </GlassButton>
            {sendCount === 0 && (
              <span id={reasonId} className="ws-send__why">
                {toCoconut.held.length > 0
                  ? heldOnlyReason(toCoconut.held)
                  : "Accept a structure first"}
              </span>
            )}
          </div>
        </div>
      </header>

      <div className="ws-tools">
        <div className="ws-toggle" role="group" aria-label="View">
          {VIEWS.map(({ view, label }) => (
            <button
              key={view}
              type="button"
              className="ws-toggle__button"
              aria-pressed={ws.view === view}
              onClick={() => ws.setView(view)}
            >
              {label}
            </button>
          ))}
        </div>
        {/* From the rows, as the grid's filters count; the tool home, which has no rows,
            reads the server's counts (GET /papers). */}
        <ul className="ws-counts" aria-label="Counts">
          <li>{`${counts.all} ${counts.all === 1 ? "structure" : "structures"}`}</li>
          <li className="ws-counts__accepted">{`${counts.accepted} accepted`}</li>
          <li className="ws-counts__check">{`${counts["to-check"]} to check`}</li>
          <li className="ws-counts__rejected">{`${counts.rejected} rejected`}</li>
          {counts.failed > 0 && <li className="ws-counts__failed">{`${counts.failed} failed`}</li>}
        </ul>
      </div>
      {/* Every structure card points here (aria-describedby): Enter opens it. */}
      <span id={CARD_OPEN_HINT} className="visually-hidden">
        Enter: open
      </span>

      <StatusBar paper={paper} steps={ws.steps} live={ws.live} />

      {ws.view === "paper" ? (
        <section className="ws-view ws-view--paper" aria-label="Paper view">
          <PaperView ws={ws} rows={rows} />
        </section>
      ) : (
        <section className="ws-view ws-view--review" aria-label="Review view">
          {focused && (
            <FocusMode
              ws={ws}
              rows={rows}
              segment={focused}
              onClose={close}
            />
          )}
          {/* Hidden, not unmounted, in focus mode: the grid keeps its filter and selection. */}
          <div ref={review} className="ws-review" hidden={focused !== undefined} tabIndex={-1}>
            <ReviewGrid ws={ws} rows={rows} counts={counts} />
          </div>
        </section>
      )}

      <OpenDialog ws={ws} paper={paper} rows={rows} />

      {sending && (
        <SubmitForm
          paper={{ id: paper.id, title: paper.title, doi: paper.doi }}
          structures={toCoconut.send}
          held={toCoconut.held}
          initial={{
            title: submissionTitle({ firstAuthor: paper.first_author, year: paper.year }),
            ...(sending.organisms.length > 0 ? { organisms: sending.organisms } : {}),
          }}
          organismsNote={sending.note}
          onClose={() => setSending(null)}
        />
      )}
    </main>
    </RgroupPaper.Provider>
  );
}

/**
 * Compare engines or the structure editor, wherever it was opened (focus mode, a card, the
 * Paper view's list): one place, pinned to its segment, gone with it.
 */
function OpenDialog({
  ws,
  paper,
  rows,
}: {
  ws: WorkspaceState;
  paper: PaperDetail;
  rows: ReviewRow[];
}) {
  const { started } = useCardActions(paper.id, ws.live.reconnect);
  const segment = ws.dialog && ws.segments.find((s) => s.id === ws.dialog!.segmentId);
  if (!ws.dialog || !segment) return null;
  if (ws.dialog.kind === "edit") {
    return (
      <SegmentEditor
        key={segment.id}
        paperId={paper.id}
        paperEngine={paper.engine}
        segment={segment}
        onClose={ws.closeDialog}
      />
    );
  }
  const at = rows.findIndex((r) => r.segmentId === segment.id);
  return (
    <SegmentCompare
      key={segment.id}
      paperId={paper.id}
      paperEngine={paper.engine}
      segment={segment}
      steps={ws.steps}
      tag={structureTag(rows[at]?.n ?? at + 1)}
      onStarted={started}
      onClose={ws.closeDialog}
      // "Use this one" accepts: the card's Compare button goes (it leaves To check), so a
      // focus that fell with it goes to the card (after the next frame, once re-rendered).
      onSaved={() =>
        requestAnimationFrame(() => {
          if (focusLost()) segmentCard(document, segment.id)?.focus();
        })
      }
    />
  );
}
