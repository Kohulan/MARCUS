// /app/images/:id: one uploaded image and the structure read from it. The uploaded image,
// the structure (its drawing from /tools/depict, its SMILES, its specimen label) and the
// actions, side by side. Nothing on this page writes a curation: an edit or a pick is kept
// in this page only ("Edited here, not saved"). Raw error text (ImageJobOut.error) is never
// read; a failure shows reasonText(error_class).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ComponentType, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { api, depictBlob, errorText, isGone, isUuid } from "../api/client";
import { depictQuery, useReplyUrl } from "../api/depictions";
import { engineName, firstRunNote, isLegacyEngine, orientationTemplate } from "../api/engines";
import { keys, useImageJob } from "../api/queries";
import { reasonText } from "../api/reasons";
import { isImageActive } from "../api/status";
import type { DepictReply, Engine, ImageJobOut, PredictionOut } from "../api/types";
import { useLiveEvents } from "../api/useLiveEvents";
import { usePageTitle } from "../pages/meta";
import { returnFocus } from "../ui/focus";
import { GlassButton } from "../ui/GlassButton";
import ProgressBar from "../ui/ProgressBar";
import GonePage, { OpenFailed } from "../ui/GonePage";
import Smiles from "../ui/Smiles";
import SpecimenLabel from "../ui/SpecimenLabel";
import StateBadge from "../ui/StateBadge";
import Structure from "../ui/Structure";
import { useToast } from "../ui/Toasts";
import Compare from "../workspace/Compare";
import Editor, { type EditorStructure } from "../workspace/Editor";
import { labelList, rgroupsOf } from "../workspace/rgroups";
import StructureActions from "../workspace/StructureActions";
import "./imageResult.css";

/**
 * What the Compare slot is given (F10's `<Compare>` with `target.kind` "image"). Compare
 * opens no stream of its own: `onStarted` is this page's `live.reconnect`.
 */
export type ImageCompareProps = {
  target: { kind: "image"; id: string };
  predictions: PredictionOut[];
  steps: {
    engine: string | null;
    status: string;
    error_class: string | null;
  }[];
  onPick: (p: PredictionOut) => void;
  onStarted: () => void;
  /** The section's Close, at the end of Compare's head. */
  headAction?: ReactNode;
  /** The image was read with DECIMER hand-drawn: Hand-drawn starts on. */
  handDrawn?: boolean;
};

// F10's Compare, as a page section (no onClose): this page renders it below the sheet.
const COMPARE: ComponentType<ImageCompareProps> | undefined = Compare;

type ImageResultProps = {
  /** The Compare component; defaults to COMPARE above (tests pass a fake). */
  compare?: ComponentType<ImageCompareProps> | undefined;
};

const duration = (ms: number) => (ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`);

/**
 * The main result: the job engine's newest valid prediction, else its newest one. Never
 * another engine's: an engine run from Compare shows there, and here only once picked
 * (the API's `prediction` is the newest of any engine, so it is not read).
 */
export function mainPrediction(job: ImageJobOut): PredictionOut | null {
  const own = job.predictions.filter((p) => p.engine === job.engine);
  return own.find((p) => p.valid) ?? own[0] ?? null;
}

/**
 * What the job engine is doing, from its newest step (newest first). The job's own status
 * also counts Compare's engines (it is "queued" while any of them runs) and is never
 * "processing", so it is only the fallback for a job without a step of its engine.
 */
function mainStatus(job: ImageJobOut): "waiting" | "reading" | "failed" | "done" {
  const step = job.steps.find((s) => s.engine === job.engine);
  const status = step?.status ?? job.status;
  if (status === "running" || status === "processing") return "reading";
  if (status === "pending" || status === "queued") return "waiting";
  if (status === "failed") return "failed";
  return "done";
}

export default function ImageResult({ compare = COMPARE }: ImageResultProps) {
  const id = useParams().id ?? "";
  if (!isUuid(id)) return <NoImage />;
  return <ImageJobPage key={id} id={id} compare={compare} />;
}

function NoImage() {
  usePageTitle("Image · MARCUS");
  return <GonePage noun="image" />;
}

/**
 * The job is read first; only a job that exists mounts the result (and with it the live
 * stream). A 404 or 422, at first or on a later refresh, shows the gone page and unmounts the
 * result, so no stream or poll is left behind.
 */
function ImageJobPage({
  id,
  compare,
}: {
  id: string;
  compare: ComponentType<ImageCompareProps> | undefined;
}) {
  const query = useImageJob(id);
  const gone = isGone(query.error);
  usePageTitle(!gone && query.data ? `${query.data.display_name} · MARCUS` : "Image · MARCUS");

  if (gone) return <GonePage noun="image" />;
  if (query.data) return <Result job={query.data} compare={compare} />;
  if (query.isError) {
    return <OpenFailed noun="image" error={query.error} onRetry={() => void query.refetch()} />;
  }
  return (
    <main className="ir" aria-busy="true">
      <span className="ir-skeleton" aria-hidden="true" />
      <p className="visually-hidden" role="status">
        Loading the image…
      </p>
    </main>
  );
}

/**
 * The drawing of `smiles` from /tools/depict (Compare's query for a plain drawing, so it is
 * drawn once), in the image's orientation when `template` gives its atom positions, as an
 * object URL, and the reply itself (Download saves it as is).
 */
function useDrawing(
  smiles: string | null,
  template: PredictionOut | null,
): {
  src: string | null;
  failed: boolean;
  reply: DepictReply | null;
} {
  const query = useQuery({
    ...depictQuery(smiles ?? "", null, undefined, template),
    enabled: smiles !== null,
  });
  const reply = smiles !== null && !query.isError ? query.data : undefined;
  return { src: useReplyUrl(reply), failed: query.isError, reply: reply ?? null };
}

function Result({
  job,
  compare: Compare,
}: {
  job: ImageJobOut;
  compare: ComponentType<ImageCompareProps> | undefined;
}) {
  const client = useQueryClient();
  const toast = useToast();
  // The stream's first snapshot ({status}) comes right after the job was read: when it says
  // what the job says, the refetch is skipped (a later one, a reconnect, never is).
  const firstSnapshot = useRef(true);
  const live = useLiveEvents("image", job.id, (snapshot) => {
    const first = snapshot !== undefined && firstSnapshot.current;
    if (snapshot !== undefined) firstSnapshot.current = false;
    const status = (snapshot as { status?: unknown } | null | undefined)?.status;
    const cached = client.getQueryData<ImageJobOut>(keys.image(job.id))?.status;
    if (first && status !== undefined && status === cached) return;
    // cancelRefetch false: never cancel (and so never repeat) a fetch already on the wire
    void client.invalidateQueries({ queryKey: keys.image(job.id) }, { cancelRefetch: false });
  });

  // Kept in this page only: a prediction picked in Compare, and an edit on top of it.
  const [picked, setPicked] = useState<PredictionOut | null>(null);
  const [edit, setEdit] = useState<EditorStructure | null>(null);
  const [editing, setEditing] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [retrying, setRetrying] = useState(false);
  // Compare opens below the sheet: focus goes to its Close, and back to what opened it.
  const opener = useRef<Element | null>(null);
  const closeCompare = useRef<HTMLButtonElement>(null);
  const openCompare = () => {
    opener.current = document.activeElement;
    setComparing(true);
  };
  const endCompare = () => {
    setComparing(false);
    returnFocus(opener.current, null);
  };
  useEffect(() => {
    if (!comparing) return;
    closeCompare.current?.scrollIntoView?.({ block: "nearest" });
    closeCompare.current?.focus({ preventScroll: true });
  }, [comparing]);

  const prediction = picked ?? mainPrediction(job);
  const status = mainStatus(job);
  const slowNote = firstRunNote(job.engine);
  // The job engine failed and left nothing to show: the failure is the result (Retry).
  const failed = status === "failed" && mainPrediction(job) === null;
  const failedClass =
    job.steps.find((st) => st.engine === job.engine)?.error_class ?? job.error_class;
  const smiles = edit?.smiles ?? prediction?.smiles ?? null;
  const molfile = edit ? edit.molfile : (prediction?.molfile ?? null);
  const drawing = useDrawing(smiles, orientationTemplate(job.predictions));
  const active = isImageActive(job.status);

  async function retry() {
    setRetrying(true);
    try {
      // as sent: the job may run an engine the UI does not offer (the fake stack's "fake")
      await api.runImagePrediction(job.id, job.engine as Engine);
      live.reconnect();
      void client.invalidateQueries({ queryKey: keys.image(job.id) }, { cancelRefetch: false });
    } catch (err) {
      toast(errorText(err), "error");
    } finally {
      setRetrying(false);
    }
  }

  const rows: [string, string][] = [];
  if (prediction) {
    rows.push(["Engine", `${engineName(prediction.engine)} ${prediction.engine_version}`.trim()]);
  }
  if (edit) rows.push(["Structure", "Edited"]);
  else if (prediction) {
    rows.push(["Valid", prediction.valid ? "Yes" : "No"]);
    const labels = rgroupsOf(prediction);
    if (labels.length > 0) rows.push(["R-groups", labelList(labels)]);
    rows.push(["Time", duration(prediction.ms)]);
  }
  const localNote = edit ? "Edited here, not saved" : picked ? "Picked here, not saved" : null;

  return (
    <main className="ir">
      <header className="ir-head">
        <h1 className="ir-title">{job.display_name}</h1>
      </header>

      <div className="ir-sheet">
        <figure className="ir-cell ir-cell--image">
          <figcaption className="ir-cap mono-label">Image</figcaption>
          <div className="ir-image">
            <img
              className="ir-image__img"
              src={api.imageUrl(job.id)}
              alt="The uploaded image"
              decoding="async"
            />
          </div>
        </figure>

        <section className="ir-cell ir-cell--structure" aria-label="Structure">
          <p className="ir-cap mono-label" aria-hidden="true">
            Structure
          </p>

          {status === "waiting" && (
            <div className="ir-progress">
              <p className="ir-status ir-status--wait">Waiting in the queue</p>
              <ProgressBar value={null} label="Image progress" valueText="Waiting in the queue" size="sm" />
            </div>
          )}
          {status === "reading" && (
            <div className="ir-progress">
              <p className="ir-status">
                <StateBadge state="reading" />
              </p>
              <ProgressBar value={null} label="Image progress" valueText="Reading" size="sm" />
              {slowNote && <p className="ir-note">{slowNote}</p>}
            </div>
          )}
          {failed && (
            <div className="ir-failed hatch">
              <StateBadge state="failed" />
              <p className="ir-failed__why">{`Could not read a structure: ${reasonText(failedClass)}`}</p>
              {/* a legacy engine (old jobs' MolNexTR) is never run again: no Retry */}
              {!isLegacyEngine(job.engine) && (
                <GlassButton tint="clear" size="sm" disabled={retrying} onClick={() => void retry()}>
                  Retry
                </GlassButton>
              )}
            </div>
          )}
          {active && live.mode === "polling" && (
            <p className="ir-live mono-label">Live updates paused, checking every 2 s</p>
          )}

          {/* A failed job with nothing to draw has no empty box: the failure is the content. */}
          {(smiles || !failed) && (
            <div className="ir-drawing">
              {smiles ? (
                <Structure
                  src={drawing.src}
                  failed={drawing.failed}
                  alt="Structure read from the image"
                />
              ) : status === "done" ? (
                <p className="ir-drawing__none mono-label">No structure found</p>
              ) : (
                <span className="corner ir-drawing__empty" aria-hidden="true">
                  +
                </span>
              )}
            </div>
          )}

          {smiles && (
            <div className="ir-smiles">
              <Smiles value={smiles} />
            </div>
          )}
          {(prediction || edit) && <SpecimenLabel title="Result" rows={rows} />}
        </section>

        <section className="ir-cell ir-cell--actions glassbed" aria-label="Actions">
          <StructureActions
            name={job.display_name}
            n={1}
            smiles={smiles}
            curatedMolfile={edit ? edit.molfile : null}
            predictionMolfile={edit ? null : (prediction?.molfile ?? null)}
            depictionUrl={null}
            image={drawing.reply ? () => depictBlob(drawing.reply!) : undefined}
            onEdit={() => setEditing(true)}
            {...(Compare ? { onCompare: openCompare } : {})}
          />
          {localNote && (
            <div className="ir-local">
              <p className="ir-local__note">{localNote}</p>
              <GlassButton
                tint="clear"
                size="sm"
                onClick={() => (edit ? setEdit(null) : setPicked(null))}
              >
                {edit ? "Undo edit" : "Undo pick"}
              </GlassButton>
            </div>
          )}
        </section>
      </div>

      {Compare && comparing && (
        <div className="ir-compare">
          <Compare
            target={{ kind: "image", id: job.id }}
            predictions={job.predictions}
            steps={job.steps}
            onPick={(p) => {
              setPicked(p);
              setEdit(null);
            }}
            onStarted={live.reconnect}
            handDrawn={job.engine === "decimer-hand"}
            headAction={
              <GlassButton ref={closeCompare} tint="clear" size="sm" onClick={endCompare}>
                Close
              </GlassButton>
            }
          />
        </div>
      )}

      {editing && (
        <Editor
          initial={{ smiles, molfile, engine: edit ? null : (prediction?.engine ?? null) }}
          source={{ image: api.imageUrl(job.id), page: null }}
          onSave={async (structure) => {
            setEdit(structure);
          }}
          onClose={() => setEditing(false)}
        />
      )}
    </main>
  );
}
