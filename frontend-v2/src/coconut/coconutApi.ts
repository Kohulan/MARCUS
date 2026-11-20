// The COCONUT reports API with the curator's own login. COCONUT allows no cross-origin calls,
// so the browser calls the MARCUS server's relay (same origin, /api/v2/coconut/...: nginx
// passes exactly these calls on to https://coconut.naturalproducts.net and stores or logs
// neither the password nor the token; backend-v2/docker/nginx.conf). The token lives in
// sessionStorage (memory when storage is blocked), is sent only with the relay's mutate call,
// never to the MARCUS API, and is never logged. Every reply is third-party data: validated,
// and shown as text only.
import { isRecord } from "../lookup/fetchJson";
import type {
  OrganismDraft,
  Organism,
  PaperFields,
  ReportCreate,
  StructureFields,
  SubmitItem,
  SubmitResult,
  SubmitStructure,
} from "./types";

/** The relay's base path; its three calls map to COCONUT's /api/auth/login, /api/reports/mutate, /api/search. */
export const COCONUT_API = "/api/v2/coconut";
export const COCONUT_CHUNK = 50;
export const TOKEN_KEY = "marcus-coconut-token";
const SENT_KEY = "marcus-coconut-sent:";

/** A bulk create of 50 reports can be slow; v1 waited 30 s for one. */
const TIMEOUT_MS = 60_000;
const MAX_ERROR = 300;

export const UNKNOWN_ERROR = "Unknown: check COCONUT before sending again";
export const NOT_SENT_ERROR = "Not sent";
export const AUTH_ERROR = "Log in to COCONUT again";
const BUSY_ERROR = "COCONUT is busy. Try again later";
const TOO_LARGE_ERROR = "Too large for COCONUT";

// --- Token ---------------------------------------------------------------------------------

let memoryToken: string | null = null;

export function getToken(): string | null {
  try {
    const stored = sessionStorage.getItem(TOKEN_KEY);
    if (stored) return stored;
  } catch {
    // storage blocked: the memory copy below
  }
  return memoryToken;
}

function keepToken(token: string) {
  memoryToken = token;
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
  } catch {
    // storage blocked: memory only, gone on reload
  }
}

export function clearToken() {
  memoryToken = null;
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // nothing stored
  }
}

// --- Login ---------------------------------------------------------------------------------

export class CoconutLoginError extends Error {}

const JSON_HEADERS = { "Content-Type": "application/json", Accept: "application/json" };

async function readJson(res: Response): Promise<unknown> {
  try {
    return (await res.json()) as unknown;
  } catch {
    return undefined;
  }
}

/** Logs in to COCONUT, keeps the token for this tab and resolves to it. */
export async function coconutLogin(email: string, password: string): Promise<string> {
  let res: Response;
  try {
    res = await fetch(`${COCONUT_API}/auth/login`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ email, password }),
      credentials: "omit",
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    throw new CoconutLoginError("Could not reach COCONUT");
  }
  if (res.status === 401 || res.status === 403 || res.status === 422) {
    throw new CoconutLoginError("Wrong email or password");
  }
  // The relay limits logins per client (3 a minute) and COCONUT may too: "busy" would mislead.
  if (res.status === 429) throw new CoconutLoginError("Too many login attempts. Try again in a minute");
  // The relay's own failure (COCONUT unreachable, or too slow): nginx's 502 / 504; 503 alike.
  if (res.status === 502 || res.status === 503 || res.status === 504) {
    throw new CoconutLoginError("Could not reach COCONUT");
  }
  const body = res.ok ? await readJson(res) : undefined;
  const token = isRecord(body) ? body.access_token : undefined;
  if (typeof token !== "string" || token === "") {
    throw new CoconutLoginError("COCONUT did not log you in");
  }
  keepToken(token);
  return token;
}

// --- Report body ---------------------------------------------------------------------------

/**
 * A comma-separated list as typed: items trimmed, blanks out. An item that starts with a double
 * quote is read to its closing quote (a doubled quote is one quote inside), so it may hold
 * commas (the annotation's parts come so, backend-v2 core/annotation.py `_form_item`); an
 * opening quote that is never closed, or a quote later in an item, is plain text.
 */
export function splitList(text: string): string[] {
  const out: string[] = [];
  let at = 0;
  for (;;) {
    let from = at;
    while (from < text.length && /\s/.test(text[from]!)) from++;
    let item = "";
    if (text[from] === '"') {
      let value = "";
      let p = from + 1;
      while (p < text.length) {
        if (text[p] === '"' && text[p + 1] === '"') {
          value += '"';
          p += 2;
        } else if (text[p] === '"') {
          item = value;
          from = p + 1;
          break;
        } else {
          value += text[p++];
        }
      }
    }
    const comma = text.indexOf(",", from);
    item = (item + text.slice(from, comma === -1 ? text.length : comma)).trim();
    if (item) out.push(item);
    if (comma === -1) return out;
    at = comma + 1;
  }
}

/** v1 formatSubmissionData: unnamed organisms are dropped; a location only when named. */
function organism(d: OrganismDraft): Organism | null {
  const name = d.name.trim();
  if (!name) return null;
  const location = d.location.trim();
  return {
    name,
    parts: splitList(d.parts),
    locations: location ? [{ name: location, ecosystems: splitList(d.ecosystems) }] : [],
  };
}

/** The organisms a structure is sent with: its own when it has a named one, else the paper's. */
export function organismsFor(paper: PaperFields, fields: StructureFields): Organism[] {
  const own = fields.organism ? organism(fields.organism) : null;
  if (own) return [own];
  return paper.organisms.map(organism).filter((o): o is Organism => o !== null);
}

/** One report: the paper's fields, with the structure's own values where it has them. */
export function buildReport(
  paper: PaperFields,
  structure: SubmitStructure,
  fields: StructureFields,
): ReportCreate {
  const doi = paper.doi.trim();
  const organisms = organismsFor(paper, fields);
  const comment = fields.comment?.trim() ? fields.comment : paper.comment;
  return {
    title: paper.title,
    evidence: paper.evidence,
    comment,
    suggested_changes: {
      new_molecule_data: {
        canonical_smiles: structure.smiles,
        reference_id: doi,
        name: fields.name.trim(),
        link: structure.link ?? "",
        structural_comments: fields.structuralComments,
        references: organisms.length > 0 ? [{ doi, organisms }] : [],
      },
    },
  };
}

export function mutateBody(reports: ReportCreate[]) {
  return {
    mutate: reports.map((attributes) => ({
      operation: "create" as const,
      attributes,
      relations: [] as never[],
    })),
  };
}

// --- Submit --------------------------------------------------------------------------------

type Reply =
  | { kind: "ok"; ids: (string | null)[] }
  | { kind: "network" }
  | {
      kind: "http";
      status: number;
      message: string | null;
      /** Messages for single items, by index within the request. */
      itemErrors: Map<number, string>;
      /** A 422 about the number of items (the `mutate` list itself). */
      sizeComplaint: boolean;
    };

function clip(text: string): string {
  const t = text.trim();
  return t.length > MAX_ERROR ? `${t.slice(0, MAX_ERROR)}…` : t;
}

function firstText(v: unknown): string | null {
  if (typeof v === "string" && v.trim()) return clip(v);
  if (Array.isArray(v)) {
    for (const x of v) if (typeof x === "string" && x.trim()) return clip(x);
  }
  return null;
}

/** The ids COCONUT created, in request order (lomkit mutate reply: `{created: [...]}`). */
function createdIds(body: unknown, n: number): (string | null)[] {
  const created = isRecord(body) ? body.created : undefined;
  const ids = Array.isArray(created) && created.length === n ? created : [];
  return Array.from({ length: n }, (_, i) => {
    const id: unknown = ids[i];
    if (typeof id === "number" && Number.isFinite(id)) return String(id);
    if (typeof id === "string" && /^[\w-]{1,64}$/.test(id)) return id;
    return null;
  });
}

async function post(token: string, items: SubmitItem[]): Promise<Reply> {
  let res: Response;
  try {
    res = await fetch(`${COCONUT_API}/reports/mutate`, {
      method: "POST",
      headers: { ...JSON_HEADERS, Authorization: `Bearer ${token}` },
      body: JSON.stringify(mutateBody(items.map((i) => i.report))),
      credentials: "omit",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    return { kind: "network" };
  }
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    // A 2xx whose body is lost mid-read: the reports may exist. Treat it as unknown.
    if (res.ok) return { kind: "network" };
    body = undefined;
  }
  if (res.ok) return { kind: "ok", ids: createdIds(body, items.length) };

  const message = isRecord(body) ? firstText(body.message) : null;
  const itemErrors = new Map<number, string>();
  let sizeComplaint = false;
  const errors = isRecord(body) && isRecord(body.errors) ? body.errors : {};
  for (const [key, value] of Object.entries(errors)) {
    const m = /^mutate\.(\d+)(\.|$)/.exec(key);
    if (m) {
      const i = Number(m[1]);
      const text = firstText(value);
      if (i < items.length && text && !itemErrors.has(i)) itemErrors.set(i, text);
    } else if (key === "mutate") {
      sizeComplaint = true;
    }
  }
  if (!sizeComplaint && res.status === 422 && itemErrors.size === 0 && message) {
    sizeComplaint = /(more than|at most|too many|maximum).*items?|items?.*(more than|at most|too many)/i.test(
      message,
    );
  }
  return { kind: "http", status: res.status, message, itemErrors, sizeComplaint };
}

type Outcome = { results: SubmitResult[]; stop: boolean };

const failAll = (items: SubmitItem[], error: string): SubmitResult[] =>
  items.map((i) => ({ segmentId: i.segmentId, ok: false, error }));

/**
 * Sends one chunk. A 413 (or a 422 about the list size) splits it in two halves, and a 422
 * naming single items resends the others; both retries happen once (`retry` false below).
 * Nothing that may have reached COCONUT is ever resent: a network error, a timeout or a 5xx
 * makes the chunk "Unknown" and stops the whole submit.
 */
async function sendChunk(
  token: string,
  items: SubmitItem[],
  retry: boolean,
  onHalved: (size: number) => void,
): Promise<Outcome> {
  const reply = await post(token, items);
  if (reply.kind === "ok") {
    return {
      results: items.map((item, i) => ({
        segmentId: item.segmentId,
        ok: true,
        reportId: reply.ids[i] ?? null,
      })),
      stop: false,
    };
  }
  if (reply.kind === "network" || reply.status >= 500) {
    return { results: failAll(items, UNKNOWN_ERROR), stop: true };
  }
  if (reply.status === 401 || reply.status === 403) {
    return { results: failAll(items, AUTH_ERROR), stop: true };
  }
  if (reply.status === 429) return { results: failAll(items, BUSY_ERROR), stop: true };

  const tooLarge = reply.status === 413 || (reply.status === 422 && reply.sizeComplaint);
  if (tooLarge && retry && items.length > 1) {
    const half = Math.ceil(items.length / 2);
    onHalved(half);
    const first = await sendChunk(token, items.slice(0, half), false, onHalved);
    if (first.stop) {
      return { results: [...first.results, ...failAll(items.slice(half), NOT_SENT_ERROR)], stop: true };
    }
    const second = await sendChunk(token, items.slice(half), false, onHalved);
    return { results: [...first.results, ...second.results], stop: second.stop };
  }
  if (tooLarge) return { results: failAll(items, reply.message ?? TOO_LARGE_ERROR), stop: false };

  const general = reply.message ?? `COCONUT refused it (${reply.status})`;
  if (reply.status === 422 && retry && reply.itemErrors.size > 0) {
    const rest = items.filter((_, i) => !reply.itemErrors.has(i));
    const again = rest.length > 0 ? await sendChunk(token, rest, false, onHalved) : null;
    const byId = new Map(again?.results.map((r) => [r.segmentId, r]));
    return {
      results: items.map(
        (item, i): SubmitResult =>
          byId.get(item.segmentId) ?? {
            segmentId: item.segmentId,
            ok: false,
            error: reply.itemErrors.get(i) ?? general,
          },
      ),
      stop: again?.stop ?? false,
    };
  }
  return {
    results: items.map((item, i) => ({
      segmentId: item.segmentId,
      ok: false,
      error: reply.itemErrors.get(i) ?? general,
    })),
    stop: false,
  };
}

/**
 * Sends the reports in chunks of COCONUT_CHUNK (smaller after COCONUT asked for that) and
 * resolves to one result per item, in order. `onProgress(done, total, chunkResults)` runs
 * after each chunk. Never rejects.
 */
export async function submitReports(
  token: string,
  items: SubmitItem[],
  onProgress?: (done: number, total: number, chunk: SubmitResult[]) => void,
): Promise<SubmitResult[]> {
  const results: SubmitResult[] = [];
  let size = COCONUT_CHUNK;
  let at = 0;
  while (at < items.length) {
    const chunk = items.slice(at, at + size);
    const outcome = await sendChunk(token, chunk, true, (half) => {
      size = Math.min(size, half);
    });
    results.push(...outcome.results);
    at += chunk.length;
    onProgress?.(at, items.length, outcome.results);
    if (outcome.stop) {
      results.push(...failAll(items.slice(at), NOT_SENT_ERROR));
      break;
    }
  }
  return results;
}

// --- Duplicate guard -----------------------------------------------------------------------

const UNKNOWN_KEY = "marcus-coconut-unknown:";

function readIds(key: string): Set<string> {
  try {
    const raw = localStorage.getItem(key);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : []);
  } catch {
    return new Set();
  }
}

function writeIds(key: string, ids: Set<string>) {
  try {
    if (ids.size === 0) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify([...ids]));
  } catch {
    // storage blocked: the guard lasts only while the form is open
  }
}

/** Segment ids of this paper that COCONUT already accepted from this browser. */
export function sentIds(paperId: string): Set<string> {
  return readIds(SENT_KEY + paperId);
}

/** Segment ids whose send ended without an answer (UNKNOWN_ERROR): they may be in COCONUT. */
export function unknownIds(paperId: string): Set<string> {
  return readIds(UNKNOWN_KEY + paperId);
}

/** Records accepted ids; an accepted id is no longer unknown. */
export function markSent(paperId: string, ids: string[]) {
  if (ids.length === 0) return;
  const all = sentIds(paperId);
  for (const id of ids) all.add(id);
  writeIds(SENT_KEY + paperId, all);
  const unknown = unknownIds(paperId);
  if (ids.some((id) => unknown.delete(id))) writeIds(UNKNOWN_KEY + paperId, unknown);
}

export function markUnknown(paperId: string, ids: string[]) {
  if (ids.length === 0) return;
  const all = unknownIds(paperId);
  for (const id of ids) all.add(id);
  writeIds(UNKNOWN_KEY + paperId, all);
}
