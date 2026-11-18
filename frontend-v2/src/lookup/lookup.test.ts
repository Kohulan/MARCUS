import { afterEach, describe, expect, it, vi } from "vitest";
import { coconutCountForDoi } from "./coconutDoi";
import { pubchemBySmiles } from "./pubchem";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

afterEach(() => vi.unstubAllGlobals());

describe("pubchemBySmiles", () => {
  it("encodes # and + in the SMILES", async () => {
    const f = vi.fn().mockResolvedValue(json({}, 404));
    vi.stubGlobal("fetch", f);
    await pubchemBySmiles("C#C[N+]=O");
    expect(f.mock.calls[0]![0]).toBe(
      "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/cids/JSON?smiles=C%23C%5BN%2B%5D%3DO",
    );
  });

  it("returns null on 404", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({}, 404)));
    expect(await pubchemBySmiles("CCO")).toBeNull();
  });

  it("returns the CID, title and url", async () => {
    const f = vi
      .fn()
      .mockResolvedValueOnce(json({ IdentifierList: { CID: [2519] } }))
      .mockResolvedValueOnce(
        json({
          PropertyTable: { Properties: [{ CID: 2519, Title: "Caffeine" }] },
        }),
      );
    vi.stubGlobal("fetch", f);
    expect(await pubchemBySmiles("CN1C=NC2=C1C(=O)N(C(=O)N2C)C")).toEqual({
      cid: 2519,
      name: "Caffeine",
      url: "https://pubchem.ncbi.nlm.nih.gov/compound/2519",
    });
    expect(f.mock.calls[1]![0]).toBe(
      "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2519/property/Title/JSON",
    );
  });

  it("keeps the CID when the title fails or is malformed", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(json({ IdentifierList: { CID: [7] } }))
        .mockRejectedValueOnce(new Error("x")),
    );
    expect((await pubchemBySmiles("C"))?.name).toBeNull();
  });

  it("rejects bad shapes and the 0 placeholder", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ IdentifierList: { CID: [0] } })),
    );
    expect(await pubchemBySmiles("C")).toBeNull();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ IdentifierList: { CID: ["<img>"] } })),
    );
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

  it("flags a full page as more and encodes the url", async () => {
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
