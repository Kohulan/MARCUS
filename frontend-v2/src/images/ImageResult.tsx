// /app/images/:id: one uploaded image and the structure read from it. The uploaded image,
// the structure (its drawing from /tools/depict, its SMILES, its specimen label) and the
// actions, side by side. Nothing on this page writes a curation: an edit or a pick is kept
// in this page only ("Edited here, not saved"). Raw error text (ImageJobOut.error) is never
// read; a failure shows reasonText(error_class).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ComponentType, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { ApiError, api, svgBlobUrl } from "../api/client";
import { keys, useImageJob } from "../api/queries";
import { reasonText } from "../api/reasons";
import type { Engine, ImageJobOut, ImagePrediction, PredictionOut } from "../api/types";
import { useLiveEvents } from "../api/useLiveEvents";
import { usePageTitle } from "../pages/meta";
import { GlassButton, GlassLink } from "../ui/GlassButton";
import Smiles from "../ui/Smiles";
import SpecimenLabel from "../ui/SpecimenLabel";
import StateBadge from "../ui/StateBadge";
import Structure from "../ui/Structure";
import { useToast } from "../ui/Toasts";
import Compare from "../workspace/Compare";
import Editor, { type EditorStructure } from "../workspace/Editor";
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
};

// F10's Compare, as a page section (no onClose): this page renders it below the sheet.
const COMPARE: ComponentType<ImageCompareProps> | undefined = Compare;

type ImageResultProps = {
  /** The Compare component; defaults to COMPARE above (tests pass a fake). */
  compare?: ComponentType<ImageCompareProps> | undefined;
};

const ENGINE_LABEL: Record<string, string> = {
  decimer: "DECIMER",
  "decimer-hand": "DECIMER hand-drawn",
  molnextr: "MolNexTR",
  molscribe: "MolScribe",
};

const engineName = (p: Pick<ImagePrediction, "engine" | "engine_version">) =>
  `${ENGINE_LABEL[p.engine] ?? p.engine} ${p.engine_version}`.trim();

const duration = (ms: number) => (ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`);

// Image job ids are UUIDs. Any other id (a mistyped or cut link) is not a job: it gets the
// gone page at once, without a request the API would answer 422.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const ACTIVE = new Set(["queued", "processing"]);

export default function ImageResult({ compare = COMPARE }: ImageResultProps) {
  const id = useParams().id ?? "";
  if (!UUID.test(id)) return <NoImage />;
  return <ImageJobPage key={id} id={id} compare={compare} />;
}

function NoImage() {
  usePageTitle("Image · MARCUS");
  return <GonePage />;
}

/**
 * The one page for an image job the API answers 404 for: deleted, expired, or owned by
 * another browser (the API does not say which, and neither does this page). Never a spinner.
 */
function GonePage() {
  return (
    <main className="ir-gone">
      <div className="ir-gone__sheet">
        <span className="corner ir-gone__corner" aria-hidden="true">
          +
        </span>
        <h1 className="ir-gone__title">This image is not here any more.</h1>
        <p className="ir-gone__why">
          It was deleted, it expired after 30 days, or it was opened in another browser.
        </p>
        <div className="ir-gone__bed glassbed">
          <GlassLink tint="clear" to="/app">
            Your papers
          </GlassLink>
        </div>
      </div>
    </main>
  );
}

/**
 * The job is read first; only a job that exists mounts the result (and with it the live
 * stream). A 404, at first or on a later refresh, shows the gone page and unmounts the
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
  const gone =
    query.error instanceof ApiError && (query.error.status === 404 || query.error.status === 422);
  usePageTitle(!gone && query.data ? `${query.data.display_name} · MARCUS` : "Image · MARCUS");

  if (gone) return <GonePage />;
  if (query.data) return <Result job={query.data} compare={compare} />;
  if (query.isError) {
    return (
      <main className="ir-gone">
        <div className="ir-gone__sheet">
          <h1 className="ir-gone__title">This image could not be opened.</h1>
          <p className="ir-gone__why">
            {query.error instanceof ApiError ? query.error.detail : "Something went wrong."}
          </p>
          <div className="ir-gone__bed glassbed">
            <GlassButton tint="clear" onClick={() => void query.refetch()}>
              Try again
            </GlassButton>
          </div>
        </div>
      </main>
    );
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

/** The drawing of `smiles` from /tools/depict as an object URL, revoked when it changes. */
function useDrawing(smiles: string | null): {
  src: string | null;
  failed: boolean;
} {
  const query = useQuery({
    // the same key Compare uses for a drawing without a highlight, so it is drawn once
    queryKey: ["depict", smiles, null],
    queryFn: () => api.depict(smiles!),
    enabled: smiles !== null,
    staleTime: Infinity,
  });
  const [src, setSrc] = useState<string | null>(null);
  const reply = query.data;
  useEffect(() => {
    if (!reply) {
      setSrc(null);
      return;
    }
    const url = svgBlobUrl(reply);
    setSrc(url);
    return () => URL.revokeObjectURL(url);
  }, [reply]);
  return { src: query.isError ? null : src, failed: query.isError };
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
  const live = useLiveEvents("image", job.id, () => {
    // cancelRefetch false: never cancel (and so never repeat) a fetch already on the wire
    void client.invalidateQueries({ queryKey: keys.image(job.id) }, { cancelRefetch: false });
  });

  // Kept in this page only: a prediction picked in Compare, and an edit on top of it.
  const [picked, setPicked] = useState<ImagePrediction | null>(null);
  const [edit, setEdit] = useState<EditorStructure | null>(null);
  const [editing, setEditing] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [retrying, setRetrying] = useState(false);
  // Compare opens below the sheet: focus goes to its Close, and back to what opened it.
  const opener = useRef<HTMLElement | null>(null);
  const closeCompare = useRef<HTMLButtonElement>(null);
  const openCompare = () => {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setComparing(true);
  };
  const endCompare = () => {
    setComparing(false);
    opener.current?.focus();
  };
  useEffect(() => {
    if (!comparing) return;
    closeCompare.current?.scrollIntoView?.({ block: "nearest" });
    closeCompare.current?.focus({ preventScroll: true });
  }, [comparing]);

  const prediction = picked ?? job.prediction;
  const smiles = edit?.smiles ?? prediction?.smiles ?? null;
  const molfile = edit ? edit.molfile : (prediction?.molfile ?? null);
  const drawing = useDrawing(smiles);
  const active = ACTIVE.has(job.status);

  async function retry() {
    setRetrying(true);
    try {
      await api.runImagePrediction(job.id, job.engine as Engine);
      live.reconnect();
      void client.invalidateQueries({ queryKey: keys.image(job.id) }, { cancelRefetch: false });
    } catch (err) {
      toast(err instanceof ApiError ? err.detail : "Something went wrong.", "error");
    } finally {
      setRetrying(false);
    }
  }

  const rows: [string, string][] = [];
  if (prediction) rows.push(["Engine", engineName(prediction)]);
  if (edit) rows.push(["Structure", "Edited"]);
  else if (prediction) {
    rows.push(["Valid", prediction.valid ? "Yes" : "No"], ["Time", duration(prediction.ms)]);
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

          {job.status === "queued" && (
            <p className="ir-status ir-status--wait">Waiting in the queue</p>
          )}
          {job.status === "processing" && (
            <p className="ir-status">
              <StateBadge state="reading" />
            </p>
          )}
          {job.status === "failed" && (
            <div className="ir-failed hatch">
              <StateBadge state="failed" />
              <p className="ir-failed__why">{`Could not read a structure: ${reasonText(job.error_class)}`}</p>
              <GlassButton tint="clear" size="sm" disabled={retrying} onClick={() => void retry()}>
                Retry
              </GlassButton>
            </div>
          )}
          {active && live.mode === "polling" && (
            <p className="ir-live mono-label">Live updates paused, checking every 2 s</p>
          )}

          {/* A failed job with nothing to draw has no empty box: the failure is the content. */}
          {(smiles || job.status !== "failed") && (
            <div className="ir-drawing">
              {smiles ? (
                <Structure
                  src={drawing.src}
                  failed={drawing.failed}
                  alt="Structure read from the image"
                />
              ) : job.status === "done" ? (
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
            depictionUrl={drawing.src}
            onEdit={() => setEditing(true)}
            copySmiles={false}
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
          initial={{ smiles, molfile }}
          onSave={async (structure) => {
            setEdit(structure);
          }}
          onClose={() => setEditing(false)}
        />
      )}
    </main>
  );
}
