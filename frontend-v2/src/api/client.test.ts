import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  api,
  ApiError,
  errorText,
  ownerReady,
  resetOwnerGate,
  SAVE_TIMEOUT_MS,
  svgBlobUrl,
} from "./client";

type Call = { url: string; init: RequestInit };

let calls: Call[];
let reply: () => Response;

function json(status: number, body: unknown, headers: Record<string, string> = {}) {
  return () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json", ...headers },
    });
}

beforeEach(() => {
  calls = [];
  reply = json(200, {});
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      return reply();
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function caught(p: Promise<unknown>): Promise<ApiError> {
  try {
    await p;
  } catch (err) {
    expect(err).toBeInstanceOf(ApiError);
    return err as ApiError;
  }
  throw new Error("expected an ApiError");
}

describe("ApiError", () => {
  it("404 → ApiError(404) with the JSON detail", async () => {
    reply = json(404, { detail: "Not found" });
    const err = await caught(api.getPaper("p1"));
    expect(err.status).toBe(404);
    expect(err.detail).toBe("Not found");
    expect(err.retryAfter).toBeUndefined();
  });

  it("429 with Retry-After: 7 → retryAfter 7", async () => {
    reply = json(429, { detail: "Too many requests" }, { "Retry-After": "7" });
    const err = await caught(api.listPapers());
    expect(err.status).toBe(429);
    expect(err.retryAfter).toBe(7);
    expect(err.detail).toBe("Too many requests");
  });

  it("422 with a list detail → the msg texts joined", async () => {
    reply = json(422, {
      detail: [
        { type: "value_error", loc: ["body", "smiles"], msg: "cannot parse SMILES" },
        { type: "missing", loc: ["body", "status"], msg: "Field required" },
      ],
    });
    const err = await caught(
      api.putCuration("s1", { status: "accepted", smiles: "C1", molfile: null, note: null }),
    );
    expect(err.status).toBe(422);
    expect(err.detail).toBe("cannot parse SMILES; Field required");
  });

  it("nginx 413 HTML → the size text", async () => {
    reply = () =>
      new Response("<html><body><h1>413 Request Entity Too Large</h1></body></html>", {
        status: 413,
        headers: { "Content-Type": "text/html" },
      });
    const file = new File(["%PDF-1.4"], "a.pdf", { type: "application/pdf" });
    const err = await caught(api.uploadPaper(file, { engine: "decimer", ocsr: "auto" }));
    expect(err.status).toBe(413);
    expect(err.detail).toBe("This file is larger than 20 MB.");
  });

  it("502, 503 and 504 without JSON → the busy text; others → HTTP code", async () => {
    for (const status of [502, 503, 504]) {
      reply = () => new Response("<html>bad gateway</html>", { status });
      expect((await caught(api.getQueue())).detail).toBe(
        "The server is busy, try again in a moment.",
      );
    }
    reply = () => new Response(null, { status: 500 });
    expect((await caught(api.getQueue())).detail).toBe("Something went wrong (HTTP 500).");
  });
});

describe("errorText", () => {
  it("shows the API's detail, a fixed sentence for anything else", () => {
    expect(errorText(new ApiError(503, "The annotation model is not running"))).toBe(
      "The annotation model is not running",
    );
    expect(errorText(new ApiError(422, "Value error, too many values"))).toBe("Value error, too many values");
    expect(errorText(new Error("x"))).toBe("Something went wrong.");
  });

  it("a request limit's 429 says what was too many and how long to wait", () => {
    expect(errorText(new ApiError(429, "rate limited", 20))).toBe("Too many requests, try again in 20 s");
    expect(errorText(new ApiError(429, "rate limited", 20), "starts")).toBe("Too many starts, try again in 20 s");
    expect(errorText(new ApiError(429, "rate limited"), "changes")).toBe("Too many changes, try again in a moment");
    // nginx's own limit, with no JSON detail
    expect(errorText(new ApiError(429, "Something went wrong (HTTP 429)."))).toBe(
      "Too many requests, try again in a moment",
    );
    // a 429 with its own words keeps them
    expect(errorText(new ApiError(429, "Too many active papers", 7))).toBe("Too many active papers");
  });
});

describe("api", () => {
  it("every call is same-origin under /api/v2", async () => {
    reply = json(200, { papers: [] });
    await api.listPapers();
    expect(calls[0]?.url).toBe("/api/v2/papers");
    expect(calls[0]?.init.credentials).toBe("same-origin");
  });

  it("reads pass the query signal to fetch, so a cancelled query aborts its request", async () => {
    reply = json(200, {});
    const ctrl = new AbortController();
    await api.getPaper("p1", { signal: ctrl.signal });
    await api.getSteps("p1", { signal: ctrl.signal });
    expect(calls[0]?.init.signal).toBe(ctrl.signal);
    expect(calls[1]?.init.signal).toBe(ctrl.signal);
  });

  it("uploadPaper sends multipart/form-data with engine and ocsr", async () => {
    reply = json(202, { paper_id: "p9", status: "checking" });
    const file = new File(["%PDF-1.4"], "a.pdf", { type: "application/pdf" });
    const out = await api.uploadPaper(file, { engine: "molparser", ocsr: "off" });
    expect(out.paper_id).toBe("p9");
    const { url, init } = calls[0]!;
    expect(url).toBe("/api/v2/papers");
    expect(init.method).toBe("POST");
    const body = init.body as FormData;
    expect(body).toBeInstanceOf(FormData);
    expect(body.get("engine")).toBe("molparser");
    expect(body.get("ocsr")).toBe("off");
    expect((body.get("file") as File).name).toBe("a.pdf");
    // the browser sets the multipart boundary itself
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
  });

  it("depict sends a highlight with its token, and neither without one", async () => {
    reply = json(200, { format: "svg", data: "<svg/>" });
    await api.depict("CCO", { highlight: "[#6]-[#6]", highlightToken: "tok" });
    await api.depict("CCN");
    expect(JSON.parse(calls[0]?.init.body as string)).toEqual({
      smiles: "CCO",
      format: "svg",
      highlight: "[#6]-[#6]",
      highlight_token: "tok",
    });
    expect(JSON.parse(calls[1]?.init.body as string)).toEqual({ smiles: "CCN", format: "svg" });
  });

  it("compare posts exactly smiles_a and smiles_b", async () => {
    reply = json(200, { tanimoto: 0.5, identical: false, same_structure: false, agree: false });
    await api.compare("CCO", "CCN");
    expect(calls[0]?.url).toBe("/api/v2/tools/compare");
    expect(JSON.parse(calls[0]?.init.body as string)).toEqual({ smiles_a: "CCO", smiles_b: "CCN" });
  });

  it("putCuration names the prediction shown with a decision only", async () => {
    const body = { status: "accepted", smiles: null, molfile: null, note: null } as const;
    reply = json(200, body);
    await api.putCuration("s1", body, true, "pr7");
    expect(calls[0]?.url).toBe("/api/v2/segments/s1/curation?decision=true&shown_prediction_id=pr7");
    reply = json(200, body);
    await api.putCuration("s1", body, false, "pr7");
    expect(calls[1]?.url).toBe("/api/v2/segments/s1/curation");
  });

  it("putCuration sends the full record as JSON", async () => {
    const body = { status: "accepted", smiles: "CCO", molfile: null, note: "n" } as const;
    reply = json(200, body);
    expect(await api.putCuration("s1", body)).toEqual(body);
    expect(calls[0]?.url).toBe("/api/v2/segments/s1/curation");
    expect(calls[0]?.init.method).toBe("PUT");
    expect(JSON.parse(calls[0]?.init.body as string)).toEqual(body);
  });

  it("putCuration gives up after 30 s: the request is aborted and the save rejects", async () => {
    vi.useFakeTimers();
    try {
      vi.stubGlobal(
        "fetch",
        vi.fn(
          (url: string, init: RequestInit) =>
            new Promise<Response>((_, reject) => {
              calls.push({ url, init });
              init.signal?.addEventListener("abort", () =>
                reject(new DOMException("aborted", "AbortError")),
              );
            }),
        ),
      );
      const body = { status: "accepted", smiles: null, molfile: null, note: null } as const;
      const settled = api.putCuration("s1", body).then(
        () => "saved",
        (err: unknown) => err,
      );
      await vi.advanceTimersByTimeAsync(SAVE_TIMEOUT_MS - 1);
      expect(SAVE_TIMEOUT_MS).toBe(30_000);
      expect(calls[0]?.init.signal?.aborted).toBe(false);
      await vi.advanceTimersByTimeAsync(1);
      expect(calls[0]?.init.signal?.aborted).toBe(true);
      // a timeout is a 504 ApiError: the outcome is unknown, as for a gateway timeout
      const err = await settled;
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(504);
    } finally {
      vi.useRealTimers();
    }
  });

  it("putCuration that answers in time leaves no timer behind", async () => {
    vi.useFakeTimers();
    try {
      const body = { status: "rejected", smiles: null, molfile: null, note: null } as const;
      reply = json(200, body);
      expect(await api.putCuration("s1", body)).toEqual(body);
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("putBulkCuration keeps an absent note key absent", async () => {
    reply = json(200, { updated: 1 });
    await api.putBulkCuration("p1", [{ segment_id: "s1", status: "accepted" }]);
    expect(calls[0]?.url).toBe("/api/v2/papers/p1/curation");
    expect(JSON.parse(calls[0]?.init.body as string)).toEqual({
      items: [{ segment_id: "s1", status: "accepted" }],
    });
  });

  it("retryPage and runPrediction post to their routes", async () => {
    reply = json(202, { step_id: "x" });
    await api.retryPage("p1", 4);
    await api.runPrediction("s1", "molscribe");
    await api.runImagePrediction("i1", "decimer-hand");
    expect(calls.map((c) => c.url)).toEqual([
      "/api/v2/papers/p1/pages/4/retry",
      "/api/v2/segments/s1/predictions",
      "/api/v2/images/i1/predictions",
    ]);
    expect(JSON.parse(calls[1]?.init.body as string)).toEqual({ engine: "molscribe" });
  });

  it("pick a structure: choose the mode, open a page, read a box", async () => {
    reply = json(202, { step_id: null });
    await api.setMode("p1", "pick");
    await api.segmentPage("p1", 3);
    await api.readSegment("s1");
    expect(calls.map((c) => [c.init.method ?? "GET", c.url])).toEqual([
      ["PUT", "/api/v2/papers/p1/mode"],
      ["POST", "/api/v2/papers/p1/pages/3/segment"],
      ["POST", "/api/v2/segments/s1/read"],
    ]);
    expect(JSON.parse(calls[0]?.init.body as string)).toEqual({ mode: "pick" });
  });

  it("annotation calls: read, start, save the curator's values, reset", async () => {
    reply = json(200, {});
    await api.getAnnotation("p1");
    await api.startAnnotation("p1");
    await api.saveAnnotation("p1", { organism_or_species: ["Taxus brevifolia"] });
    await api.resetAnnotation("p1");
    expect(calls.map((c) => [c.init.method ?? "GET", c.url])).toEqual([
      ["GET", "/api/v2/papers/p1/annotation"],
      ["POST", "/api/v2/papers/p1/annotation"],
      ["PUT", "/api/v2/papers/p1/annotation/curation"],
      ["DELETE", "/api/v2/papers/p1/annotation/curation"],
    ]);
    expect(JSON.parse(calls[1]?.init.body as string)).toEqual({ rerun: false });
    expect(JSON.parse(calls[2]?.init.body as string)).toEqual({
      values: { organism_or_species: ["Taxus brevifolia"] },
    });
  });

  it("deletePaper accepts an empty 204", async () => {
    reply = () => new Response(null, { status: 204 });
    await expect(api.deletePaper("p1")).resolves.toBeUndefined();
    expect(calls[0]?.init.method).toBe("DELETE");
  });

  it("builds URLs", () => {
    expect(api.depictionUrl("s1", "abc", "molparser")).toBe(
      "/api/v2/segments/s1/depiction?v=abc&engine=molparser",
    );
    expect(api.depictionUrl("s1", "abc")).toBe("/api/v2/segments/s1/depiction?v=abc");
    expect(api.exportUrl("p1", "sdf", "accepted")).toBe(
      "/api/v2/papers/p1/export?format=sdf&status=accepted",
    );
    expect(api.pageImageUrl("p1", 4)).toBe("/api/v2/papers/p1/pages/4/image");
    expect(api.segmentImageUrl("s1")).toBe("/api/v2/segments/s1/image");
    expect(api.imageUrl("i1")).toBe("/api/v2/images/i1/image");
  });

  it("svgBlobUrl makes an image/svg+xml object URL", () => {
    const made: Blob[] = [];
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: (b: Blob) => {
        made.push(b);
        return "blob:x";
      },
    });
    expect(svgBlobUrl({ format: "svg", data: "<svg/>" })).toBe("blob:x");
    expect(made[0]?.type).toBe("image/svg+xml");
  });
});

describe("one owner: no parallel requests before the first success", () => {
  type Pending = { url: string; resolve: (r: Response) => void; reject: (e: unknown) => void };
  let pending: Pending[];

  beforeEach(() => {
    resetOwnerGate();
    pending = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (url: string) =>
          new Promise<Response>((resolve, reject) => pending.push({ url, resolve, reject })),
      ),
    );
  });

  afterEach(() => resetOwnerGate());

  const ok = () => new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
  const tick = () => new Promise((r) => setTimeout(r, 0));

  it("ownerReady() resolves after the first success, not after a failure", async () => {
    let ready = false;
    void ownerReady().then(() => (ready = true));
    const first = api.listPapers();
    await tick();
    pending[0]!.resolve(new Response("", { status: 502 }));
    await expect(first).rejects.toBeInstanceOf(ApiError);
    await tick();
    expect(ready).toBe(false);
    const second = api.listPapers();
    await tick();
    pending[1]!.resolve(ok());
    await second;
    await tick();
    expect(ready).toBe(true);
  });

  it("holds every request until the first one succeeded, then lets them all go", async () => {
    const list = api.listPapers();
    const images = api.listImages();
    const upload = api.uploadPaper(new File(["%PDF"], "a.pdf"), { engine: "decimer", ocsr: "auto" });
    await tick();
    expect(pending.map((p) => p.url)).toEqual(["/api/v2/papers"]);
    pending[0]!.resolve(ok());
    await list;
    await tick();
    expect(pending).toHaveLength(3); // both waiting requests went out together
    pending[1]!.resolve(ok());
    pending[2]!.resolve(ok());
    await Promise.all([images, upload]);
  });

  it("after a failed first request (error status or network), the next one goes alone", async () => {
    const list = api.listPapers();
    const images = api.listImages();
    images.catch(() => undefined); // it rejects (network) before allSettled below sees it
    const upload = api.uploadPaper(new File(["%PDF"], "a.pdf"), { engine: "decimer", ocsr: "auto" });
    await tick();
    expect(pending).toHaveLength(1);
    pending[0]!.resolve(new Response("", { status: 502 }));
    await expect(list).rejects.toBeInstanceOf(ApiError);
    await tick();
    expect(pending).toHaveLength(2); // only one of the two waiting requests
    pending[1]!.reject(new TypeError("network"));
    await tick();
    await tick();
    expect(pending).toHaveLength(3); // the last one, still alone
    pending[2]!.resolve(ok());
    await Promise.allSettled([images, upload]);
    const next = api.listPapers();
    await tick();
    expect(pending).toHaveLength(4); // ready: no more waiting
    pending[3]!.resolve(ok());
    await next;
  });

  it("a first request that never answers holds the others 20 s at most, then the next goes alone", async () => {
    vi.useFakeTimers();
    try {
      void api.listPapers(); // a stalled connection: never settles
      const images = api.listImages();
      const upload = api.uploadPaper(new File(["%PDF"], "a.pdf"), { engine: "decimer", ocsr: "auto" });
      await vi.advanceTimersByTimeAsync(0);
      expect(pending).toHaveLength(1);
      await vi.advanceTimersByTimeAsync(19_999);
      expect(pending).toHaveLength(1);
      await vi.advanceTimersByTimeAsync(1);
      expect(pending).toHaveLength(2); // one of the two waiting requests, alone
      expect(pending[1]!.url).toBe("/api/v2/images");
      pending[1]!.resolve(ok());
      await images;
      await vi.advanceTimersByTimeAsync(0);
      expect(pending).toHaveLength(3); // the owner is set: the upload goes
      pending[2]!.resolve(ok());
      await upload;
    } finally {
      vi.useRealTimers();
    }
  });
});
