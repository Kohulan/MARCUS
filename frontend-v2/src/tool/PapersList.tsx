import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ApiError, api } from "../api/client";
import { keys } from "../api/queries";
import type { ImageJobSummary, PaperSummary } from "../api/types";
import { GlassButton, GlassLink } from "../ui/GlassButton";
import StateBadge from "../ui/StateBadge";
import { useToast } from "../ui/Toasts";
import "./tool.css";

const DAY_MS = 86_400_000;
const ASK = "Delete this paper and its results? This cannot be undone.";

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/** "15 structures · 9 accepted · 2 rejected · 4 to check · 1 failed page" (zeros left out). */
export function countsText(p: PaperSummary): string {
  const parts = [plural(p.structures, "structure")];
  if (p.accepted) parts.push(`${p.accepted} accepted`);
  if (p.rejected) parts.push(`${p.rejected} rejected`);
  if (p.to_review) parts.push(`${p.to_review} to check`);
  if (p.failed_pages) parts.push(plural(p.failed_pages, "failed page"));
  return parts.join(" · ");
}

/** "Deleted in N days" (N rounded up), "Deleted today" when less than a day is left. */
export function deletionText(expiresAt: string, now = Date.now()): string {
  const days = (Date.parse(expiresAt) - now) / DAY_MS;
  if (!(days >= 1)) return "Deleted today"; // also an unreadable date
  return `Deleted in ${plural(Math.ceil(days), "day")}`;
}

/** A paper's or image job's state as its word and its shape. */
export function ItemState({ status, notRead }: { status: string; notRead?: boolean }) {
  if (status === "failed") return <StateBadge state="failed" />;
  if (status === "done") {
    if (notRead) return <StateBadge state="not-read" />;
    return (
      <span className="state item-done">
        <span className="item-done__mark" aria-hidden="true" />
        Done
      </span>
    );
  }
  return <StateBadge state="reading" />;
}

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Something went wrong.";
}

function PaperRow({ paper }: { paper: PaperSummary }) {
  const client = useQueryClient();
  const toast = useToast();
  const [asking, setAsking] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const deleteButton = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);

  // The safe choice gets the focus; closing gives it back to Delete.
  useEffect(() => {
    if (asking) dialog.current?.querySelector<HTMLButtonElement>("button")?.focus();
  }, [asking]);

  function close() {
    setAsking(false);
    requestAnimationFrame(() => deleteButton.current?.querySelector("button")?.focus());
  }

  async function confirm() {
    setDeleting(true);
    try {
      await api.deletePaper(paper.id);
      toast("Paper deleted");
      await client.invalidateQueries({ queryKey: keys.papers() });
    } catch (error) {
      toast(errorText(error), "error");
      setDeleting(false);
      close();
    }
  }

  const name = paper.title?.trim() || paper.display_name;
  const askId = `ask-${paper.id}`;

  return (
    <li className="item">
      <div className="item__state">
        <ItemState status={paper.status} notRead={paper.ocsr_mode === "off"} />
      </div>
      <div className="item__main">
        <p className="item__name">{name}</p>
        {paper.title?.trim() ? <p className="item__file">{paper.display_name}</p> : null}
        <p className="item__counts">{countsText(paper)}</p>
      </div>
      <p className="item__expiry">{deletionText(paper.expires_at)}</p>
      <div className="item__actions" ref={deleteButton}>
        <GlassLink tint="clear" size="sm" to={`/app/papers/${encodeURIComponent(paper.id)}`}>
          Open
        </GlassLink>
        <GlassButton tint="clear" size="sm" disabled={asking} onClick={() => setAsking(true)}>
          Delete
        </GlassButton>
      </div>
      {asking ? (
        <dialog
          ref={dialog}
          open
          className="ask"
          aria-labelledby={askId}
          onKeyDown={(e) => {
            if (e.key === "Escape" && !deleting) {
              e.preventDefault();
              close();
            }
          }}
        >
          <p id={askId} className="ask__text">
            {ASK}
          </p>
          <div className="ask__actions">
            <GlassButton tint="clear" size="sm" disabled={deleting} onClick={close}>
              Cancel
            </GlassButton>
            <GlassButton tint="orange" size="sm" disabled={deleting} onClick={() => void confirm()}>
              Delete
            </GlassButton>
          </div>
        </dialog>
      ) : null}
    </li>
  );
}

function ImageRow({ job }: { job: ImageJobSummary }) {
  return (
    <li className="item item--image">
      <div className="item__state">
        <ItemState status={job.status} />
      </div>
      <div className="item__main">
        <p className="item__name item__name--image">{job.display_name}</p>
      </div>
      <p className="item__expiry">{deletionText(job.expires_at)}</p>
      <div className="item__actions">
        <GlassLink tint="clear" size="sm" to={`/app/images/${encodeURIComponent(job.id)}`}>
          Open
        </GlassLink>
      </div>
    </li>
  );
}

type ListState<T> = {
  items: T[] | undefined;
  error: unknown;
  loading: boolean;
  retry: () => void;
};

function Skeleton({ label }: { label: string }) {
  return (
    <div className="items-skeleton" aria-busy="true">
      <p className="visually-hidden" role="status">
        {label}
      </p>
      {[0, 1, 2].map((i) => (
        <div key={i} className="items-skeleton__row" aria-hidden="true">
          <span className="items-skeleton__bar items-skeleton__bar--state" />
          <span className="items-skeleton__bar items-skeleton__bar--name" />
          <span className="items-skeleton__bar items-skeleton__bar--expiry" />
        </div>
      ))}
    </div>
  );
}

function LoadError({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <div className="items-error">
      <p className="items-error__text">{errorText(error)}</p>
      <GlassButton tint="clear" size="sm" onClick={retry}>
        Try again
      </GlassButton>
    </div>
  );
}

/**
 * This browser's papers (title or file name, state, counts, days to deletion, Open,
 * Delete with a confirm) and, below, its single-image jobs. `sample` is the sample-paper
 * button: in the heading row, or alone in the empty state.
 */
export default function PapersList({
  papers,
  images,
  sample,
}: {
  papers: ListState<PaperSummary>;
  images: ListState<ImageJobSummary>;
  sample: ReactNode;
}) {
  const empty = papers.items !== undefined && papers.items.length === 0;
  const jobs = images.items ?? [];

  return (
    <section className="lists" aria-labelledby="papers-heading">
      <div className="lists__head">
        <h2 id="papers-heading" className="lists__title">
          Your papers
        </h2>
        <p className="mono-label lists__note">Only this browser can open them</p>
        {papers.items && !empty ? <div className="lists__sample">{sample}</div> : null}
      </div>

      {papers.items === undefined ? (
        papers.loading ? (
          <Skeleton label="Loading your papers…" />
        ) : (
          <LoadError error={papers.error} retry={papers.retry} />
        )
      ) : empty ? (
        <div className="items-empty">
          <p className="items-empty__text">No papers yet.</p>
          {sample}
        </div>
      ) : (
        <ul className="items" aria-label="Papers">
          {papers.items.map((p) => (
            <PaperRow key={p.id} paper={p} />
          ))}
        </ul>
      )}

      {jobs.length > 0 ? (
        <>
          <h2 className="lists__title lists__title--images" id="images-heading">
            Images
          </h2>
          <ul className="items" aria-label="Images">
            {jobs.map((j) => (
              <ImageRow key={j.id} job={j} />
            ))}
          </ul>
        </>
      ) : images.items === undefined && !images.loading ? (
        <LoadError error={images.error} retry={images.retry} />
      ) : null}
    </section>
  );
}
