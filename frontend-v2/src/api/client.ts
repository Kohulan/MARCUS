// The one HTTP client of the tool: every call is same-origin under /api/v2 (the owner
// cookie rides along), and every non-2xx becomes an ApiError with a text fit to show.
import type {
  AnnotationOut,
  AnnotationStarted,
  AnnotationValues,
  BuildOut,
  BulkCurationItem,
  BulkCurationOut,
  CompareReply,
  CurationIn,
  CurationOut,
  DepictReply,
  DifferencesReply,
  DoclingDoc,
  Engine,
  ExportFormat,
  ExportStatus,
  ImageJobList,
  ImageJobOut,
  MainFigureOut,
  McsReply,
  ModeOut,
  OcsrMode,
  PaperDetail,
  PaperList,
  QueueOut,
  ReadAccepted,
  RgroupList,
  RgroupStarted,
  SegmentAccepted,
  StepAccepted,
  StepList,
  UploadImageReply,
  UploadPaperReply,
} from "./types";

export const BASE = "/api/v2";

export const TOO_LARGE = "This file is larger than 20 MB.";
const BUSY = "The server is busy, try again in a moment.";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly retryAfter: number | undefined;

  constructor(status: number, detail: string, retryAfter?: number) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.retryAfter = retryAfter;
  }
}

/** The API's terse 429 detail for its per-owner request limits (backend api/security.py). */
const RATE_LIMITED = "rate limited";

/**
 * The text to show for a failed request: the API's detail, else a fixed sentence. A 429 of a
 * request limit (the API's, or nginx's with no detail) says how long to wait, naming `what`
 * was too many ("Too many starts, try again in 30 s"); other 429s keep their own detail.
 */
export function errorText(err: unknown, what = "requests"): string {
  if (!(err instanceof ApiError)) return "Something went wrong.";
  if (err.status === 429 && (err.detail === RATE_LIMITED || err.detail === fallbackDetail(429))) {
    const when = err.retryAfter !== undefined ? `in ${err.retryAfter} s` : "in a moment";
    return `Too many ${what}, try again ${when}`;
  }
  return err.detail;
}

/** Gone: 404 (missing, deleted, expired or another browser's; the API does not say which) or 422. */
export function isGone(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 404 || err.status === 422);
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Paper and image ids are UUIDs. Any other id (a mistyped or cut link) gets the gone page at
 * once, without a request the API would answer 422.
 */
export const isUuid = (id: string): boolean => UUID.test(id);

function fallbackDetail(status: number): string {
  if (status === 413) return TOO_LARGE;
  if (status === 502 || status === 503 || status === 504) return BUSY;
  return `Something went wrong (HTTP ${status}).`;
}

/** The JSON `detail` of FastAPI (a string, or the 422 list of {msg}); null for anything else. */
function jsonDetail(text: string): string | null {
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    return null; // nginx's own HTML error pages, or no body
  }
  if (typeof body !== "object" || body === null || !("detail" in body)) return null;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d: unknown) =>
        typeof d === "object" && d !== null && "msg" in d ? (d as { msg: unknown }).msg : null,
      )
      .filter((m): m is string => typeof m === "string" && m.trim() !== "");
    if (msgs.length) return msgs.join("; ");
  }
  return null;
}

/** Retry-After in whole seconds: delta-seconds or an HTTP date. */
function parseRetryAfter(value: string | null): number | undefined {
  if (value === null || value.trim() === "") return undefined;
  if (/^\d+$/.test(value.trim())) return Number(value.trim());
  const when = Date.parse(value);
  if (Number.isNaN(when)) return undefined;
  return Math.max(0, Math.ceil((when - Date.now()) / 1000));
}

/** Read a non-2xx response into an ApiError. */
export async function toApiError(res: Response): Promise<ApiError> {
  let text = "";
  try {
    text = await res.text();
  } catch {
    // a body that cannot be read gets the fixed text
  }
  const detail = jsonDetail(text) ?? fallbackDetail(res.status);
  return new ApiError(res.status, detail, parseRetryAfter(res.headers.get("Retry-After")));
}

// One owner per browser. The API makes an owner (and sets its cookie) for any request that
// comes without the cookie, so two cookie-less requests in flight at once make two owners,
// and the Set-Cookie that arrives last decides which one the browser keeps: an upload could
// land on the other one. So until one request has succeeded in this page (from then on the
// cookie is there), requests go out one at a time; a failed one (a 502 while the API
// restarts, a network error, a 429) lets the next waiting request try, and so does one that
// has not answered in 20 s.
//
// The gate covers every `api.*` call (they all go through send()). It does NOT cover what
// the browser requests by itself: an EventSource (useLiveEvents), an <img src> of an API URL
// (page, crop and image URLs), an export <a href>, or a raw fetch. Rule: mount those only
// after a gated request has answered 2xx (the paper workspace mounts its frame only after
// getPaper did; an image page must wait for getImageJob the same way), or await
// ownerReady() first (the depiction loader does).
let ownerSet = false;
let firstInFlight: Promise<unknown> | null = null;
let markReady: () => void = () => undefined;
let readyPromise = new Promise<void>((resolve) => (markReady = resolve));

/** Resolves once a request of this page has succeeded (the owner cookie is set). */
export function ownerReady(): Promise<void> {
  return readyPromise;
}

// A first request that never answers (a stalled connection) must not hold every other
// request for good: after this long the next waiting one goes (alone) in its place.
const GATE_WAIT_MS = 20_000;

/** True when `first` settled; false when GATE_WAIT_MS passed first. */
function settledInTime(first: Promise<unknown>): Promise<boolean> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const late = new Promise<boolean>((resolve) => {
    timer = setTimeout(() => resolve(false), GATE_WAIT_MS);
  });
  return Promise.race([first.then(() => true, () => true), late]).finally(() =>
    clearTimeout(timer),
  );
}

async function send(url: string, init: RequestInit): Promise<Response> {
  while (!ownerSet && firstInFlight) {
    const first = firstInFlight;
    if (!(await settledInTime(first)) && firstInFlight === first) {
      firstInFlight = null; // stalled: this request takes its place (the others still wait)
      break;
    }
  }
  if (ownerSet) return fetch(url, init);
  const attempt = fetch(url, init);
  firstInFlight = attempt;
  try {
    const res = await attempt;
    if (res.ok && !ownerSet) {
      ownerSet = true;
      markReady();
    }
    return res;
  } finally {
    if (firstInFlight === attempt) firstInFlight = null;
  }
}

/** Tests only: forget that a request has succeeded (a new page). */
export function resetOwnerGate(): void {
  ownerSet = false;
  firstInFlight = null;
  readyPromise = new Promise<void>((resolve) => (markReady = resolve));
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await send(`${BASE}${path}`, { ...init, credentials: "same-origin" });
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

/** Options of a read: TanStack Query's `signal`, so a cancelled query aborts its request. */
export type ReadOpts = { signal?: AbortSignal };

function get<T>(path: string, opts: ReadOpts = {}): Promise<T> {
  return request<T>(path, opts.signal ? { signal: opts.signal } : {});
}

function sendJson<T>(
  method: "POST" | "PUT",
  path: string,
  body: unknown,
  timeoutMs?: number,
): Promise<T> {
  const init: RequestInit = {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
  if (timeoutMs === undefined) return request<T>(path, init);
  const ctrl = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    ctrl.abort();
  }, timeoutMs);
  return request<T>(path, { ...init, signal: ctrl.signal })
    .catch((err: unknown) => {
      // no answer in time: like a gateway timeout, the outcome is unknown
      throw timedOut ? new ApiError(504, BUSY) : err;
    })
    .finally(() => clearTimeout(timer));
}

/**
 * A curation PUT not answered in this time is aborted (a 504 ApiError): the save fails and
 * rolls back, the paper's live refreshes, held while it is on the wire, go on, and the paper
 * is fetched again (the PUT may have been saved after all).
 */
export const SAVE_TIMEOUT_MS = 30_000;

const enc = encodeURIComponent;

export const api = {
  // papers
  listPapers: (opts?: ReadOpts) => get<PaperList>("/papers", opts),
  getPaper: (id: string, opts?: ReadOpts) => get<PaperDetail>(`/papers/${enc(id)}`, opts),
  getSteps: (id: string, opts?: ReadOpts) => get<StepList>(`/papers/${enc(id)}/steps`, opts),
  uploadPaper(file: File, opts: { engine: Engine; ocsr: OcsrMode }): Promise<UploadPaperReply> {
    const form = new FormData();
    form.append("file", file);
    form.append("engine", opts.engine);
    form.append("ocsr", opts.ocsr);
    // no Content-Type header: the browser writes multipart/form-data with its boundary
    return request<UploadPaperReply>("/papers", { method: "POST", body: form });
  },
  deletePaper: (id: string) => request<void>(`/papers/${enc(id)}`, { method: "DELETE" }),
  putBulkCuration: (paperId: string, items: BulkCurationItem[]) =>
    sendJson<BulkCurationOut>("PUT", `/papers/${enc(paperId)}/curation`, { items }),
  /** `page0` is the 0-based API page. */
  /** Marks a page (0-based) as the paper's main figure; null clears the mark. */
  putMainFigure: (paperId: string, page0: number | null) =>
    sendJson<MainFigureOut>("PUT", `/papers/${enc(paperId)}/main-figure`, { page: page0 }),
  retryPage: (paperId: string, page0: number) =>
    request<StepAccepted>(`/papers/${enc(paperId)}/pages/${page0}/retry`, { method: "POST" }),
  /** The paper page's answer: read all pages ("auto") or pick a structure ("pick"). */
  setMode: (paperId: string, mode: "auto" | "pick") =>
    sendJson<ModeOut>("PUT", `/papers/${enc(paperId)}/mode`, { mode }),
  /** Pick mode: find the boxes on one page (0-based). */
  segmentPage: (paperId: string, page0: number) =>
    request<SegmentAccepted>(`/papers/${enc(paperId)}/pages/${page0}/segment`, {
      method: "POST",
    }),
  /** Markush Phase 3: build each R-group row of the scaffold into its own structure. */
  buildStructures: (segmentId: string) =>
    request<BuildOut>(`/segments/${enc(segmentId)}/build`, { method: "POST" }),
  /** Pick mode: read one box with the three engines. */
  readSegment: (segmentId: string) =>
    request<ReadAccepted>(`/segments/${enc(segmentId)}/read`, { method: "POST" }),
  getQueue: (opts?: ReadOpts) => get<QueueOut>("/queue", opts),
  getText: (id: string, opts?: ReadOpts) => get<DoclingDoc>(`/papers/${enc(id)}/text`, opts),
  exportUrl(id: string, format: ExportFormat, status?: ExportStatus): string {
    const q = new URLSearchParams({ format });
    if (status) q.set("status", status);
    return `${BASE}/papers/${enc(id)}/export?${q}`;
  },
  /** `page0` is the 0-based API page. */
  pageImageUrl: (id: string, page0: number) => `${BASE}/papers/${enc(id)}/pages/${page0}/image`,

  // annotation (the local model's suggestion, and the curator's corrections)
  getAnnotation: (id: string, opts?: ReadOpts) =>
    get<AnnotationOut>(`/papers/${enc(id)}/annotation`, opts),
  /** 202 {step_id}: started or still running; 200 {step_id: null}: already annotated. */
  startAnnotation: (id: string, rerun = false) =>
    sendJson<AnnotationStarted>("POST", `/papers/${enc(id)}/annotation`, { rerun }),
  /** The curator's whole set: all 11 fields ([] = none). */
  saveAnnotation: (id: string, values: AnnotationValues) =>
    sendJson<AnnotationOut>("PUT", `/papers/${enc(id)}/annotation/curation`, { values }),
  /** Back to the model's values. */
  resetAnnotation: (id: string) =>
    request<AnnotationOut>(`/papers/${enc(id)}/annotation/curation`, { method: "DELETE" }),

  // R-group rows of a scaffold (the local R-group model)
  getPaperRgroups: (id: string, opts?: ReadOpts) =>
    get<RgroupList>(`/papers/${enc(id)}/rgroups`, opts),
  /** 202 {step_id}: started or still running; 200 {step_id: null}: it has rows already. */
  startRgroups: (predictionId: string, rerun = false) =>
    sendJson<RgroupStarted>("POST", `/predictions/${enc(predictionId)}/rgroups`, { rerun }),

  // segments
  /**
   * Only through useSaveCuration (curationBody builds the full record). `decision`: the status
   * is a decision made now, not kept by a note or structure edit (the server gives a
   * main-figure structure's decision to its repeats too). `shownPredictionId`: with a
   * decision, the prediction the card showed; the server keeps it as the decided structure.
   */
  putCuration: (
    segmentId: string,
    body: CurationIn,
    decision = false,
    shownPredictionId: string | null = null,
  ) => {
    const q = new URLSearchParams();
    if (decision) q.set("decision", "true");
    if (decision && shownPredictionId) q.set("shown_prediction_id", shownPredictionId);
    const query = q.toString() ? `?${q.toString()}` : "";
    return sendJson<CurationOut>(
      "PUT",
      `/segments/${enc(segmentId)}/curation${query}`,
      body,
      SAVE_TIMEOUT_MS,
    );
  },
  runPrediction: (segmentId: string, engine: Engine) =>
    sendJson<StepAccepted>("POST", `/segments/${enc(segmentId)}/predictions`, { engine }),
  segmentImageUrl: (id: string) => `${BASE}/segments/${enc(id)}/image`,
  /** `key` is depictionKey(segment): it only busts the browser cache. */
  depictionUrl(segmentId: string, key: string, engine?: Engine): string {
    const q = new URLSearchParams({ v: key });
    if (engine) q.set("engine", engine);
    return `${BASE}/segments/${enc(segmentId)}/depiction?${q}`;
  },

  // tools
  /**
   * A highlight is drawn only with the token its MCS reply carried (`highlight_token`).
   * `template`: an OCSR molfile with the image's atom positions (the paper's orientation).
   */
  depict(
    smiles: string,
    opts: {
      highlight?: string;
      highlightToken?: string;
      template?: string;
      /** Atoms drawn orange / light blue, by index (api.differences). */
      marks?: number[];
      common?: number[];
    } = {},
  ): Promise<DepictReply> {
    const body: Record<string, string | number[]> = { smiles, format: "svg" };
    if (opts.highlight) body.highlight = opts.highlight;
    if (opts.highlight && opts.highlightToken) body.highlight_token = opts.highlightToken;
    if (opts.template) body.template = opts.template;
    if (opts.marks?.length) body.marks = opts.marks;
    if (opts.common?.length) body.common = opts.common;
    return sendJson<DepictReply>("POST", "/tools/depict", body);
  },
  differences: (smiles: string[]) =>
    sendJson<DifferencesReply>("POST", "/tools/differences", { smiles }),
  compare: (smilesA: string, smilesB: string) =>
    sendJson<CompareReply>("POST", "/tools/compare", { smiles_a: smilesA, smiles_b: smilesB }),
  mcs: (molfiles: string[]) => sendJson<McsReply>("POST", "/tools/mcs", { molfiles }),
  /** The molfile text. */
  async smilesToMolfile(smiles: string): Promise<string> {
    const out = await sendJson<{ molfile: string }>("POST", "/tools/smiles-to-molfile", {
      smiles,
    });
    return out.molfile;
  },

  // single images
  uploadImage(file: File, engine: Engine): Promise<UploadImageReply> {
    const form = new FormData();
    form.append("file", file);
    form.append("engine", engine);
    return request<UploadImageReply>("/images", { method: "POST", body: form });
  },
  listImages: (opts?: ReadOpts) => get<ImageJobList>("/images", opts),
  getImageJob: (id: string, opts?: ReadOpts) => get<ImageJobOut>(`/images/${enc(id)}`, opts),
  runImagePrediction: (id: string, engine: Engine) =>
    sendJson<StepAccepted>("POST", `/images/${enc(id)}/predictions`, { engine }),
  imageUrl: (id: string) => `${BASE}/images/${enc(id)}/image`,
};

/** A /tools/depict reply as a file (api.depict always asks for SVG). */
export function depictBlob(reply: DepictReply): Blob {
  return new Blob([reply.data], { type: "image/svg+xml" });
}

/** An object URL for a /tools/depict reply, for `<img src>`. The caller revokes it. */
export function svgBlobUrl(reply: DepictReply): string {
  return URL.createObjectURL(depictBlob(reply));
}
