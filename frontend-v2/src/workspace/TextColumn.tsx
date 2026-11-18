import { useId, useMemo } from "react";
import { ApiError } from "../api/client";
import { useSteps, useText } from "../api/queries";
import { reasonText } from "../api/reasons";
import type { StepOut } from "../api/types";
import { GlassButton } from "../ui/GlassButton";
import { doclingBlocks, type TextBlock } from "./doclingText";

const ACTIVE = new Set(["pending", "queued", "running"]);
const BUSY_PAPER = new Set(["checking", "processing"]);
const NO_BLOCKS: TextBlock[] = [];
const NO_STEPS: StepOut[] = [];

/** The paper's newest docling step (steps come oldest first; ties go to the later one). */
function newestDocling(steps: StepOut[]): StepOut | undefined {
  let newest: StepOut | undefined;
  for (const s of steps) {
    if (s.kind === "docling" && (!newest || s.created_at >= newest.created_at)) newest = s;
  }
  return newest;
}

/** Saves the blocks, joined by blank lines, as `<name>.txt` through a blob link. */
function download(blocks: TextBlock[], name: string) {
  const blob = new Blob([blocks.map((b) => b.text).join("\n\n")], {
    type: "text/plain;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${name}.txt`;
  document.body.append(a);
  a.click();
  a.remove();
  // Some browsers start reading the blob after click() returns.
  window.setTimeout(() => URL.revokeObjectURL(url), 10000);
}

/**
 * The middle column of the Paper view: the paper's text from Docling, its download, and the
 * place the annotations take later. The text file can be large: it is asked for only here
 * (the Paper view is open) and only once the docling step is done, or when the paper has
 * no docling step and is not being worked on (the server answers 404 if it has none).
 */
export default function TextColumn({
  paperId,
  displayName,
  paperStatus,
}: {
  paperId: string;
  displayName: string;
  paperStatus: string;
}) {
  const headId = useId();
  // The workspace's steps query (cached, no second request): until it has answered, a
  // failed or running docling step cannot be told from none.
  const stepsQuery = useSteps(paperId);
  const known = stepsQuery.data !== undefined || stepsQuery.isError;
  const docling = newestDocling(stepsQuery.data?.steps ?? NO_STEPS);
  const failed = docling?.status === "failed";
  const waiting =
    !known ||
    (docling === undefined ? BUSY_PAPER.has(paperStatus) : ACTIVE.has(docling.status));
  const text = useText(paperId, !failed && !waiting);
  const blocks = useMemo(() => (text.data ? doclingBlocks(text.data) : NO_BLOCKS), [text.data]);

  const notReady = waiting || (text.error instanceof ApiError && text.error.status === 404);
  let body;
  if (failed) {
    body = (
      <p className="pv-text__state">{`The text could not be read: ${reasonText(docling.error_class)}`}</p>
    );
  } else if (notReady) {
    body = <p className="pv-text__state">The text of this paper is not ready</p>;
  } else if (text.isError) {
    body = (
      <div className="pv-text__state">
        <p>The text could not be loaded.</p>
        <GlassButton tint="clear" size="sm" onClick={() => void text.refetch()}>
          Try again
        </GlassButton>
      </div>
    );
  } else if (!text.data) {
    body = (
      <p className="pv-text__state" role="status">
        Loading the text…
      </p>
    );
  } else if (blocks.length === 0) {
    body = <p className="pv-text__state">No text was found in this paper.</p>;
  } else {
    body = (
      <div className="pv-text__body">
        {blocks.map((b, i) =>
          b.kind === "heading" ? (
            <h3 key={i} className="pv-text__heading">
              {b.text}
            </h3>
          ) : (
            <p key={i} className="pv-text__para">
              {b.text}
            </p>
          ),
        )}
      </div>
    );
  }

  return (
    <section className="pv-col pv-col--text" aria-labelledby={headId}>
      <div className="pv-cap">
        <h2 id={headId} className="pv-cap__title">
          Text
        </h2>
        {blocks.length > 0 && (
          <GlassButton tint="clear" size="sm" onClick={() => download(blocks, displayName)}>
            Download text
          </GlassButton>
        )}
      </div>
      <div className="pv-text">
        <p className="pv-text__later">
          Annotations (compounds, organisms, methods) come in a later version.
        </p>
        {body}
      </div>
    </section>
  );
}
