import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api, errorText } from "../api/client";
import { keys } from "../api/queries";
import type { ImageJobSummary, PaperList, PaperSummary } from "../api/types";
import { GlassButton, GlassLink } from "../ui/GlassButton";
import { Modal } from "../ui/modal";
import ReadingProgress, { useShownProgress } from "../ui/ReadingProgress";
import { ItemState } from "../ui/StateBadge";
import { paperName } from "../ui/tag";
import { useToast } from "../ui/Toasts";
import { isAnnotating } from "../workspace/annotation";
import { progressOf } from "../workspace/readingProgress";
import "./tool.css";

const DAY_MS = 86_400_000;
const ASK = "Delete this paper and its results? This cannot be undone.";

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/**
 * "15 structures · 9 accepted · 3 to check · 2 rejected · 1 failed · 1 failed page" (zeros
 * left out), in the workspace's order. A failed structure is never counted as to check.
 */
function countsText(p: PaperSummary): string {
  const parts = [plural(p.structures, "structure")];
  if (p.accepted) parts.push(`${p.accepted} accepted`);
  if (p.to_review) parts.push(`${p.to_review} to check`);
  if (p.rejected) parts.push(`${p.rejected} rejected`);
  if (p.failed) parts.push(`${p.failed} failed`);
  if (p.failed_pages) parts.push(plural(p.failed_pages, "failed page"));
  return parts.join(" · ");
}

/** "Deleted in N days" (N rounded up), "Deleted today" when less than a day is left. */
function deletionText(expiresAt: string, now = Date.now()): string {
  const days = (Date.parse(expiresAt) - now) / DAY_MS;
  if (!(days >= 1)) return "Deleted today"; // also an unreadable date
  return `Deleted in ${plural(Math.ceil(days), "day")}`;
}

/**
 * A busy paper's thin progress bar and its stage in a few words, from the read's counts the
 * list brings (no steps asked for); an annotate run ends on its full bar for a moment.
 */
function RowProgress({ paper }: { paper: PaperSummary }) {
  const model = useShownProgress(useMemo(() => progressOf(paper), [paper]));
  if (model === null) return null;
  return (
    <ReadingProgress progress={model} label={`Progress of ${paperName(paper)}`} compact />
  );
}

function PaperRow({ paper }: { paper: PaperSummary }) {
  const client = useQueryClient();
  const toast = useToast();
  const [asking, setAsking] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // The safe choice gets the focus; closing gives it back to Delete.
  const deleteButton = useRef<HTMLButtonElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  const close = () => setAsking(false);

  async function confirm() {
    setDeleting(true);
    try {
      await api.deletePaper(paper.id);
      toast("Paper deleted");
      // The row goes at once: a list refresh that then fails must not leave it standing
      // with a confirm whose buttons are disabled.
      client.setQueryData<PaperList>(keys.papers(), (old) =>
        old ? { ...old, papers: old.papers.filter((p) => p.id !== paper.id) } : old,
      );
      void client.invalidateQueries({ queryKey: keys.papers() });
    } catch (error) {
      toast(errorText(error), "error");
      setDeleting(false);
      close();
    }
  }

  const askId = `ask-${paper.id}`;

  return (
    <li className="item">
      <div className="item__state">
        <ItemState
          status={paper.status}
          notRead={paper.ocsr_mode === "off"}
          annotating={isAnnotating(paper)}
        />
      </div>
      <div className="item__main">
        <p className="item__name">{paperName(paper)}</p>
        {paper.title?.trim() ? <p className="item__file">{paper.display_name}</p> : null}
        <p className="item__counts">{countsText(paper)}</p>
        <RowProgress paper={paper} />
      </div>
      <p className="item__expiry">{deletionText(paper.expires_at)}</p>
      <div className="item__actions">
        <GlassLink tint="clear" size="sm" to={`/app/papers/${encodeURIComponent(paper.id)}`}>
          Open
        </GlassLink>
        <GlassButton
          ref={deleteButton}
          tint="clear"
          size="sm"
          disabled={asking}
          onClick={() => setAsking(true)}
        >
          Delete
        </GlassButton>
      </div>
      {asking ? (
        <Modal
          inline
          className="ask"
          labelledBy={askId}
          onClose={() => !deleting && close()}
          first={cancelButton}
          fallback={deleteButton}
        >
          <p id={askId} className="ask__text">
            {ASK}
          </p>
          <div className="ask__actions">
            <GlassButton
              ref={cancelButton}
              tint="clear"
              size="sm"
              disabled={deleting}
              onClick={close}
            >
              Cancel
            </GlassButton>
            <GlassButton tint="orange" size="sm" disabled={deleting} onClick={() => void confirm()}>
              Delete
            </GlassButton>
          </div>
        </Modal>
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
 * This browser's papers (title or file name, state, counts, a busy one's progress, days to
 * deletion, Open, Delete with a confirm) and, below, its single-image jobs. `sample` is the
 * sample-paper button: in the heading row, or alone in the empty state.
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
