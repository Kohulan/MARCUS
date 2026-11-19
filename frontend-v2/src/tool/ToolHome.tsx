import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { keys, useImages, usePapers } from "../api/queries";
import type { Engine } from "../api/types";
import { usePageTitle } from "../pages/meta";
import { GlassButton } from "../ui/GlassButton";
import DropZone from "./DropZone";
import type { FileKind } from "./files";
import PapersList from "./PapersList";
import "./tool.css";

/** The synthetic sample paper (public/sample) and the display name it is uploaded under. */
const SAMPLE_URL = "/sample/synth_015.pdf";
export const SAMPLE_NAME = "Sample paper (synthetic).pdf";
const SAMPLE_MISSING = "The sample paper could not be loaded.";

type Problem = { text: string; retryAt?: number; waitS?: number };

function problemOf(error: unknown): Problem {
  if (error instanceof ApiError) {
    return error.status === 429 && error.retryAfter !== undefined
      ? {
          text: error.detail,
          retryAt: Date.now() + error.retryAfter * 1000,
          waitS: error.retryAfter,
        }
      : { text: error.detail };
  }
  return { text: "The upload did not reach the server. Check your connection." };
}

const waitText = (seconds: number) => `Try again in ${seconds} s`;

/**
 * "Try again in N s", counting down; gone at zero, and its timer with it. Shown outside the
 * alert and hidden from screen readers: the alert says the first value once (a ticking line
 * inside role="alert" would be read out again every second).
 */
function RetryIn({ at }: { at: number }) {
  const [now, setNow] = useState(() => Date.now());
  const seconds = Math.ceil((at - now) / 1000);
  const done = seconds <= 0;
  useEffect(() => {
    if (done) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [done]);
  if (done) return null;
  return (
    <p className="drop__wait" aria-hidden="true">
      {waitText(seconds)}
    </p>
  );
}

/**
 * /app: upload a PDF or one image (engine, find structures on/off), try the sample paper,
 * and this browser's papers and image jobs. A PDF opens /app/papers/<id> after upload, an
 * image /app/images/<id>. `?sample=1` (the landing's "Try a sample paper") runs the sample
 * button once; router state `{upload: File}` (a PDF dropped on the landing, already checked
 * there) is uploaded once, the same way as a file dropped here.
 */
export default function ToolHome() {
  usePageTitle("Papers · MARCUS");
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const client = useQueryClient();
  // The first answer of a new browser sets its owner cookie. Every other request waits for
  // it: two requests without the cookie would make two owners, and the Set-Cookie that comes
  // last decides which one the browser keeps (an upload could end up with the other one).
  const papers = usePapers();
  const listed = papers.isSuccess || papers.isError;
  const images = useImages(listed);

  const [engine, setEngine] = useState<Engine>("decimer");
  const [auto, setAuto] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);

  const sample = papers.data?.papers.find((p) => p.display_name === SAMPLE_NAME) ?? null;

  /** Resolves once the papers list has answered (the owner cookie is set), ok or not. */
  const listAnswered = useCallback(async () => {
    if (client.getQueryState(keys.papers())?.status !== "pending") return;
    await client
      .fetchQuery({ queryKey: keys.papers(), queryFn: ({ signal }) => api.listPapers({ signal }) })
      .catch(() => undefined);
  }, [client]);

  const upload = useCallback(
    async (file: File, kind: FileKind, label: string) => {
      setBusy(label);
      setProblem(null);
      try {
        await listAnswered();
        if (kind === "pdf") {
          const out = await api.uploadPaper(file, { engine, ocsr: auto ? "auto" : "off" });
          void client.invalidateQueries({ queryKey: keys.papers() });
          navigate(`/app/papers/${encodeURIComponent(out.paper_id)}`);
        } else {
          const out = await api.uploadImage(file, engine);
          void client.invalidateQueries({ queryKey: keys.images() });
          navigate(`/app/images/${encodeURIComponent(out.image_job_id)}`);
        }
      } catch (error) {
        setProblem(problemOf(error));
        setBusy(null);
      }
    },
    [auto, client, engine, listAnswered, navigate],
  );

  // Each upload takes one of the three active-paper slots: a listed sample is opened.
  const runSample = useCallback(async () => {
    if (sample) {
      navigate(`/app/papers/${encodeURIComponent(sample.id)}`);
      return;
    }
    setBusy("Uploading the sample paper…");
    setProblem(null);
    let file: File;
    try {
      const res = await fetch(SAMPLE_URL, { credentials: "same-origin" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      file = new File([await res.blob()], SAMPLE_NAME, { type: "application/pdf" });
    } catch {
      setProblem({ text: SAMPLE_MISSING });
      setBusy(null);
      return;
    }
    await upload(file, "pdf", "Uploading the sample paper…");
  }, [navigate, sample, upload]);

  // ?sample=1: once the list says whether the sample is there. The flag is dropped from
  // the URL first, so a reload or Back does not upload it again.
  const wantsSample = params.get("sample") === "1";
  const sampleRan = useRef(false);
  useEffect(() => {
    if (!wantsSample || sampleRan.current || !papers.isSuccess) return;
    sampleRan.current = true;
    navigate({ pathname: location.pathname }, { replace: true, state: null });
    void runSample();
  }, [wantsSample, papers.isSuccess, navigate, location.pathname, runSample]);

  // {upload: File}: the landing's drop zone hands over a PDF it has checked. The file leaves
  // the history entry first, so a reload or Back from the paper does not upload it again.
  const handed = (location.state as { upload?: unknown } | null)?.upload;
  const handedFile = handed instanceof File ? handed : null;
  const handOffRan = useRef(false);
  useEffect(() => {
    if (!handedFile || handOffRan.current) return;
    handOffRan.current = true; // StrictMode runs this effect twice; the file is sent once
    navigate(
      { pathname: location.pathname, search: location.search },
      { replace: true, state: null },
    );
    void upload(handedFile, "pdf", `Uploading ${handedFile.name}…`);
  }, [handedFile, navigate, location.pathname, location.search, upload]);

  const sampleButton = (
    <GlassButton tint="clear" disabled={busy !== null} onClick={() => void runSample()}>
      {sample ? "Open the sample paper" : "Try a sample paper"}
      <span aria-hidden="true">→</span>
    </GlassButton>
  );

  return (
    <main className="tool-home">
      <section className="upload" aria-label="Upload">
        <div className="upload__caption" aria-hidden="true">
          <span className="corner">+</span>
          <span className="mono-label">New sheet · PDF or one image · max 20 MB</span>
          <span className="corner">+</span>
        </div>
        <div className="ticks upload__ticks" aria-hidden="true" />
        <DropZone
          engine={engine}
          onEngine={setEngine}
          auto={auto}
          onAuto={setAuto}
          onFile={(file, kind) => void upload(file, kind, `Uploading ${file.name}…`)}
          onRefuse={(text) => setProblem({ text })}
          busy={busy}
          message={
            problem ? (
              <p className="drop__problem">
                {problem.text}
                {problem.retryAt !== undefined ? (
                  <span className="visually-hidden">{` ${waitText(problem.waitS ?? 0)}.`}</span>
                ) : null}
              </p>
            ) : null
          }
          wait={
            problem?.retryAt !== undefined ? (
              <RetryIn key={problem.retryAt} at={problem.retryAt} />
            ) : null
          }
        />
      </section>

      <PapersList
        papers={{
          items: papers.data?.papers,
          error: papers.error,
          loading: papers.isPending,
          retry: () => void papers.refetch(),
        }}
        images={{
          items: images.data?.jobs,
          error: images.error,
          loading: images.isPending,
          retry: () => void images.refetch(),
        }}
        sample={sampleButton}
      />
    </main>
  );
}
