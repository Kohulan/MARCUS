// The one HTTP client of the tool: every call is same-origin under /api/v2 (the owner
// cookie rides along), and every non-2xx becomes an ApiError with a text fit to show.
import type {
  BulkCurationItem,
  BulkCurationOut,
  CompareReply,
  CurationIn,
  CurationOut,
  DepictReply,
  DoclingDoc,
  Engine,
  ExportFormat,
  ExportStatus,
  ImageJobList,
  ImageJobOut,
  McsReply,
  OcsrMode,
  PaperDetail,
  PaperList,
  QueueOut,
  StepAccepted,
  StepList,
  UploadImageReply,
  UploadPaperReply,
} from "./types";

export const BASE = "/api/v2";

const TOO_LARGE = "This file is larger than 20 MB.";
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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { ...init, credentials: "same-origin" });
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

function sendJson<T>(method: "POST" | "PUT", path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

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
  retryPage: (paperId: string, page0: number) =>
    request<StepAccepted>(`/papers/${enc(paperId)}/pages/${page0}/retry`, { method: "POST" }),
  getQueue: (opts?: ReadOpts) => get<QueueOut>("/queue", opts),
  getText: (id: string, opts?: ReadOpts) => get<DoclingDoc>(`/papers/${enc(id)}/text`, opts),
  exportUrl(id: string, format: ExportFormat, status?: ExportStatus): string {
    const q = new URLSearchParams({ format });
    if (status) q.set("status", status);
    return `${BASE}/papers/${enc(id)}/export?${q}`;
  },
  /** `page0` is the 0-based API page. */
  pageImageUrl: (id: string, page0: number) => `${BASE}/papers/${enc(id)}/pages/${page0}/image`,

  // segments
  /** Only through useSaveCuration (curationBody builds the full record). */
  putCuration: (segmentId: string, body: CurationIn) =>
    sendJson<CurationOut>("PUT", `/segments/${enc(segmentId)}/curation`, body),
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
  depict(smiles: string, opts: { highlight?: string } = {}): Promise<DepictReply> {
    const body: Record<string, string> = { smiles, format: "svg" };
    if (opts.highlight) body.highlight = opts.highlight;
    return sendJson<DepictReply>("POST", "/tools/depict", body);
  },
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

/** An object URL for a /tools/depict reply, for `<img src>`. The caller revokes it. */
export function svgBlobUrl(reply: DepictReply): string {
  const blob =
    reply.format === "png"
      ? new Blob([Uint8Array.from(atob(reply.data), (c) => c.charCodeAt(0))], {
          type: "image/png",
        })
      : new Blob([reply.data], { type: "image/svg+xml" });
  return URL.createObjectURL(blob);
}
