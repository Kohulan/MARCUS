import { useId } from "react";
import { useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { usePaper } from "../api/queries";
import type { PaperDetail } from "../api/types";
import { usePageTitle } from "../pages/meta";
import { GlassButton } from "../ui/GlassButton";
import ExportMenu from "./ExportMenu";
import GonePage from "./GonePage";
import StatusBar from "./StatusBar";
import { useWorkspace, type WorkspaceView } from "./useWorkspace";
import "./workspace.css";

const name = (p: PaperDetail) => p.title || p.display_name;

// Paper ids are UUIDs. Any other id (a mistyped or cut link) is not a paper: it gets the
// gone page at once, without a request the API would answer 422.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default function Workspace() {
  const id = useParams().id ?? "";
  if (!UUID.test(id)) return <NoPaper />;
  return <PaperWorkspace key={id} id={id} />;
}

function NoPaper() {
  usePageTitle("Paper · MARCUS");
  return <GonePage />;
}

/**
 * /app/papers/:id. The paper is read first; only a paper that exists mounts the frame (and
 * with it the live stream). A 404, at first or on any later refresh (deleted in another tab,
 * expired), shows the one gone page and unmounts the frame, so no stream or poll is left.
 */
function PaperWorkspace({ id }: { id: string }) {
  const query = usePaper(id);
  // 404: missing, deleted, expired or another browser's (the API does not say which).
  const gone =
    query.error instanceof ApiError && (query.error.status === 404 || query.error.status === 422);
  usePageTitle(!gone && query.data ? `${name(query.data)} · MARCUS` : "Paper · MARCUS");

  if (gone) return <GonePage />;
  if (query.data) return <Frame id={id} />;
  if (query.isError) {
    return (
      <main className="ws-gone">
        <div className="ws-gone__sheet">
          <h1 className="ws-gone__title">This paper could not be opened.</h1>
          <p className="ws-gone__why">
            {query.error instanceof ApiError ? query.error.detail : "Something went wrong."}
          </p>
          <div className="ws-gone__bed glassbed">
            <GlassButton tint="clear" onClick={() => void query.refetch()}>
              Try again
            </GlassButton>
          </div>
        </div>
      </main>
    );
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
  const reasonId = useId();
  const paper = ws.paper;
  if (!paper) return null; // the outer component mounts the frame only with a paper

  const accepted = paper.accepted;
  return (
    <main className="ws">
      <header className="ws-head">
        <div className="ws-head__title">
          <h1 className="ws-title">{name(paper)}</h1>
          <p className="ws-meta">
            {paper.title && <span className="ws-meta__file">{paper.display_name}</span>}
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
          </p>
        </div>
        <div className="ws-head__actions glassbed">
          <ExportMenu paperId={paper.id} />
          <div className="ws-send">
            {/* F13 opens the COCONUT form from here. */}
            <GlassButton
              tint="green"
              disabled={accepted === 0}
              describedBy={accepted === 0 ? reasonId : undefined}
            >
              {`Send ${accepted} to COCONUT`}
            </GlassButton>
            {accepted === 0 && (
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
        <ul className="ws-counts" aria-label="Counts">
          <li>{`${paper.structures} ${paper.structures === 1 ? "structure" : "structures"}`}</li>
          <li className="ws-counts__accepted">{`${paper.accepted} accepted`}</li>
          <li className="ws-counts__check">{`${paper.to_review} to check`}</li>
          <li className="ws-counts__rejected">{`${paper.rejected} rejected`}</li>
        </ul>
      </div>

      <StatusBar
        paper={paper}
        steps={ws.steps}
        failedPages={ws.failedPages}
        checkFailure={ws.checkFailure}
        live={ws.live}
      />

      {ws.view === "paper" ? (
        <section className="ws-view" aria-label="Paper view" />
      ) : (
        <section className="ws-view" aria-label="Review view" />
      )}
    </main>
  );
}
