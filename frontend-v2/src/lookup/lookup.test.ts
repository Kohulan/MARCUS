import { afterEach, describe, expect, it, vi } from "vitest";
import { coconutCountForDoi, coconutLabel } from "./coconutDoi";
import { TIMEOUT_MS } from "./fetchJson";
import { pubchemBySmiles } from "./pubchem";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

afterEach(() => vi.unstubAllGlobals());

describe("pubchemBySmiles", () => {
  const found = (props: unknown[]) => json({ PropertyTable: { Properties: props } });

  it("asks once, with # and + in the SMILES encoded", async () => {
    const f = vi.fn().mockResolvedValue(json({}, 404));
    vi.stubGlobal("fetch", f);
    await pubchemBySmiles("C#C[N+]=O");
    expect(f).toHaveBeenCalledTimes(1);
    expect(f.mock.calls[0]![0]).toBe(
      "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/property/Title/JSON?smiles=C%23C%5BN%2B%5D%3DO",
    );
  });

  it("returns null on 404", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({}, 404)));
    expect(await pubchemBySmiles("CCO")).toBeNull();
  });

  it("returns the CID, title and url from the one reply", async () => {
    const f = vi.fn().mockResolvedValue(found([{ CID: 2519, Title: "Caffeine" }]));
    vi.stubGlobal("fetch", f);
    expect(await pubchemBySmiles("CN1C=NC2=C1C(=O)N(C(=O)N2C)C")).toEqual({
      cid: 2519,
      name: "Caffeine",
      url: "https://pubchem.ncbi.nlm.nih.gov/compound/2519",
    });
    expect(f).toHaveBeenCalledTimes(1);
  });

  it("keeps the CID when the title is missing or malformed", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(found([{ CID: 7, Title: 42 }])));
    expect(await pubchemBySmiles("C")).toEqual({
      cid: 7,
      name: null,
      url: "https://pubchem.ncbi.nlm.nih.gov/compound/7",
    });
  });

  it("rejects bad shapes and the 0 placeholder", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(found([{ CID: 0 }])));
    expect(await pubchemBySmiles("C")).toBeNull();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(found([{ CID: "<img>" }])));
    expect(await pubchemBySmiles("C")).toBeNull();
  });

  it("returns null on a network error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    expect(await pubchemBySmiles("CCO")).toBeNull();
  });
});

describe("coconutCountForDoi", () => {
  const rowsOf = (n: number) =>
    Array.from({ length: n }, (_, i) => ({ id: i + 1 }));

  it("sends exactly v1's request", async () => {
    const f = vi.fn().mockResolvedValue(json({ data: { data: [] } }));
    vi.stubGlobal("fetch", f);
    await coconutCountForDoi("https://doi.org/10.1/abc");
    const [url, init] = f.mock.calls[0]!;
    expect(url).toBe("https://coconut.naturalproducts.net/api/search");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      type: "tags",
      tagType: "citations",
      query: "10.1/abc",
      limit: 20,
      sort: "desc",
      page: 1,
      offset: 0,
    });
  });

  it("counts unique ids from data.data.data, data.data, data.results and a bare array", async () => {
    for (const body of [
      { data: { data: rowsOf(3) } },
      { data: rowsOf(3) },
      { results: rowsOf(3) },
      rowsOf(3),
    ]) {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(body)));
      expect(await coconutCountForDoi("10.1/x")).toMatchObject({
        count: 3,
        more: false,
      });
    }
  });

  it("falls back to coconut_id then identifier and dedupes", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          json([
            { coconut_id: "A" },
            { coconut_id: "A" },
            { identifier: "B" },
            { name: "none" },
          ]),
        ),
    );
    expect((await coconutCountForDoi("10.1/x"))?.count).toBe(2);
  });

  it("flags a full page of unique ids as more and encodes the url", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ data: { data: rowsOf(20) } })),
    );
    expect(await coconutCountForDoi("10.1/a b#c")).toEqual({
      count: 20,
      more: true,
      url: "https://coconut.naturalproducts.net/search?q=10.1%2Fa%20b%23c&tagType=citations&type=tags&activeTab=citations",
    });
  });

  it("returns null on error, bad status and unusable shapes without crashing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    expect(await coconutCountForDoi("10.1/x")).toBeNull();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({}, 500)));
    expect(await coconutCountForDoi("10.1/x")).toBeNull();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json("junk")));
    expect(await coconutCountForDoi("10.1/x")).toMatchObject({ count: 0 });
    expect(await coconutCountForDoi("  ")).toBeNull();
  });
});

describe("coconutLabel", () => {
  it("shows the count, with + on a full page, and 0", () => {
    expect(coconutLabel({ count: 0, more: false })).toBe(
      "0 already in COCONUT",
    );
    expect(coconutLabel({ count: 3, more: false })).toBe(
      "3 already in COCONUT",
    );
    expect(coconutLabel({ count: 20, more: true })).toBe(
      "20+ already in COCONUT",
    );
  });

  it("counts more on unique ids, not rows", async () => {
    const dupes = Array.from({ length: 20 }, () => ({ id: 1 }));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(dupes)));
    expect(await coconutCountForDoi("10.1/x")).toMatchObject({
      count: 1,
      more: false,
    });
  });
});

describe("timeout and abort", () => {
  it("returns null when the request hangs past the timeout", async () => {
    vi.useFakeTimers();
    try {
      vi.stubGlobal(
        "fetch",
        vi.fn(
          (_u: string, init: RequestInit) =>
            new Promise<Response>((_res, rej) =>
              init.signal?.addEventListener("abort", () =>
                rej(new DOMException("t", "AbortError")),
              ),
            ),
        ),
      );
      const p = pubchemBySmiles("CCO");
      await vi.advanceTimersByTimeAsync(TIMEOUT_MS + 1);
      expect(await p).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("aborts the request when the caller aborts, and stays null", async () => {
    let seen: AbortSignal | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_u: string, init: RequestInit) =>
          new Promise<Response>((_res, rej) => {
            seen = init.signal as AbortSignal;
            seen.addEventListener("abort", () =>
              rej(new DOMException("a", "AbortError")),
            );
          }),
      ),
    );
    const ctl = new AbortController();
    const p = coconutCountForDoi("10.1/x", ctl.signal);
    ctl.abort();
    expect(await p).toBeNull();
    expect(seen?.aborted).toBe(true);
  });

  it("does not start when already aborted", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_u: string, init: RequestInit) => {
        if (init.signal?.aborted) throw new DOMException("a", "AbortError");
        return json({});
      }),
    );
    const ctl = new AbortController();
    ctl.abort();
    expect(await pubchemBySmiles("C", ctl.signal)).toBeNull();
  });
});
