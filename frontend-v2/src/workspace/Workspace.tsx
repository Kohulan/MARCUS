import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { isGone, isUuid } from "../api/client";
import { usePaper } from "../api/queries";
import type { PaperDetail } from "../api/types";
import SubmitForm from "../coconut/SubmitForm";
import { coconutCountForDoi, coconutLabel, type CoconutDoiCount } from "../lookup/coconutDoi";
import { usePageTitle } from "../pages/meta";
import { GlassButton } from "../ui/GlassButton";
import GonePage, { OpenFailed } from "../ui/GonePage";
import { paperName } from "../ui/tag";
import ExportMenu from "./ExportMenu";
import FocusMode from "./FocusMode";
import PaperView from "./PaperView";
import ReviewGrid from "./ReviewGrid";
import { coconutStructures, submissionTitle } from "./coconutList";
import { CARD_OPEN_HINT, filterCounts } from "./cardState";
import StatusBar from "./StatusBar";
import { useReviewRows } from "./useReviewRows";
import { useWorkspace, type Workspace as WorkspaceState, type WorkspaceView } from "./useWorkspace";
import "./workspace.css";

/** How many structures COCONUT already has for the paper's DOI (null: unknown or no DOI). */
function useCoconutCount(doi: string | null): CoconutDoiCount | null {
  const [found, setFound] = useState<{ doi: string; count: CoconutDoiCount } | null>(null);
  useEffect(() => {
    if (!doi) return;
    const ctl = new AbortController();
    void coconutCountForDoi(doi, ctl.signal).then((count) => {
      if (!ctl.signal.aborted) setFound(count ? { doi, count } : null);
    });
    return () => ctl.abort();
  }, [doi]);
  return found !== null && found.doi === doi ? found.count : null;
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
  const focused =
    ws.view === "review" && ws.focus ? ws.segments.find((s) => s.id === ws.selection) : undefined;

  const { focus, selection, setSelection, closeFocus } = ws;
  useEffect(() => {
    if (returnTo === null || focus) return;
    setReturnTo(null);
    if (selection !== returnTo) setSelection(returnTo);
    const card = [...(review.current?.querySelectorAll<HTMLElement>("[data-segment-id]") ?? [])].find(
      (el) => el.dataset.segmentId === returnTo,
    );
    (card ?? review.current)?.focus();
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
  const [sending, setSending] = useState(false);
  const sendCount = toCoconut.length;
  return (
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
          <ExportMenu paperId={paper.id} />
          <div className="ws-send">
            <GlassButton
              tint="green"
              disabled={sendCount === 0}
              describedBy={sendCount === 0 ? reasonId : undefined}
              hasPopup="dialog"
              onClick={() => setSending(true)}
            >
              {`Send ${sendCount} to COCONUT`}
            </GlassButton>
            {sendCount === 0 && (
              <span id={reasonId} className="ws-send__why">
                Accept a structure first
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
        {/* From the rows, as the grid's filters count (the server's to_review also holds
            the failed ones); the tool home, which has no rows, keeps the server's counts. */}
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

      <StatusBar
        paper={paper}
        steps={ws.steps}
        failedPages={ws.failedPages}
        checkFailure={ws.checkFailure}
        live={ws.live}
      />

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
            <ReviewGrid ws={ws} rows={rows} />
          </div>
        </section>
      )}

      {sending && (
        <SubmitForm
          paper={{ id: paper.id, title: paper.title, doi: paper.doi }}
          structures={toCoconut}
          // The paper API gives no first author or year (v1 read them from the DOI's
          // metadata): the title keeps what is known.
          initial={{ title: submissionTitle({}) }}
          onClose={() => setSending(false)}
        />
      )}
    </main>
  );
}
