import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  buildReport,
  clearToken,
  COCONUT_API,
  COCONUT_CHUNK,
  coconutLogin,
  getToken,
  markSent,
  markUnknown,
  mutateBody,
  NOT_SENT_ERROR,
  sentIds,
  splitList,
  submitReports,
  TOKEN_KEY,
  UNKNOWN_ERROR,
  unknownIds,
} from "./coconutApi";
import { api } from "../api/client";
import CoconutLogin from "./CoconutLogin";
import SubmitForm from "./SubmitForm";
import SubmitResults from "./SubmitResults";
import type { PaperFields, ReportCreate, SubmitItem, SubmitStructure } from "./types";

const TOKEN = "test-token";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type Call = { url: string; init: RequestInit };
let calls: Call[];
let fetchMock: ReturnType<typeof vi.fn>;

function stubFetch(impl: (url: string, init: RequestInit, n: number) => Promise<Response>) {
  calls = [];
  fetchMock = vi.fn((url: string, init: RequestInit = {}) => {
    calls.push({ url, init });
    return impl(url, init, calls.length);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function bodyOf(c: Call): { mutate: { attributes: ReportCreate }[] } {
  return JSON.parse(String(c.init.body)) as { mutate: { attributes: ReportCreate }[] };
}

/** A COCONUT that creates every report it is sent, ids counting up from 1. */
function okServer() {
  let next = 1;
  return async (_url: string, init: RequestInit) => {
    const n = (JSON.parse(String(init.body)) as { mutate: unknown[] }).mutate.length;
    return json({ created: Array.from({ length: n }, () => next++), updated: [] });
  };
}

const paper: PaperFields = {
  title: "MARCUS_Submission Rajan 2025",
  doi: "10.1039/d5dd00313j",
  evidence: "Isolated from the bark",
  comment: "Paper comment",
  organisms: [{ name: "Salix alba", parts: "bark, leaf", location: "Jena", ecosystems: "forest" }],
};

function items(count: number): SubmitItem[] {
  return Array.from({ length: count }, (_, i) => ({
    segmentId: `s${i + 1}`,
    report: buildReport(
      paper,
      { segmentId: `s${i + 1}`, n: i + 1, smiles: "CCO" },
      { name: `Name ${i + 1}`, structuralComments: "" },
    ),
  }));
}

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  clearToken();
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("coconutLogin", () => {
  it("posts to the relay's /auth/login and keeps access_token in sessionStorage", async () => {
    stubFetch(async () => json({ access_token: TOKEN, token_type: "Bearer" }));
    await expect(coconutLogin("a@b.c", "pw")).resolves.toBe(TOKEN);
    expect(calls).toHaveLength(1);
    expect(calls[0]!.url).toBe("/api/v2/coconut/auth/login");
    expect(calls[0]!.init.method).toBe("POST");
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({ email: "a@b.c", password: "pw" });
    expect(calls[0]!.init.credentials).toBe("omit");
    expect(sessionStorage.getItem(TOKEN_KEY)).toBe(TOKEN);
    expect(TOKEN_KEY).toBe("marcus-coconut-token");
    expect(localStorage.length).toBe(0);
    expect(getToken()).toBe(TOKEN);
  });

  it("keeps the token in memory when sessionStorage throws", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    stubFetch(async () => json({ access_token: TOKEN }));
    await coconutLogin("a@b.c", "pw");
    expect(getToken()).toBe(TOKEN);
    clearToken();
    expect(getToken()).toBeNull();
  });

  it("rejects wrong credentials with a plain message", async () => {
    stubFetch(async () => json({ message: "Invalid" }, 401));
    await expect(coconutLogin("a@b.c", "bad")).rejects.toThrow("Wrong email or password");
    expect(getToken()).toBeNull();
  });

  it("keeps COCONUT's own status through the relay: 403 and 422 wrong login, 429 busy", async () => {
    for (const status of [403, 422]) {
      stubFetch(async () => json({ message: "no" }, status));
      await expect(coconutLogin("a@b.c", "bad")).rejects.toThrow("Wrong email or password");
    }
    stubFetch(async () => json({ message: "Too Many Attempts." }, 429));
    await expect(coconutLogin("a@b.c", "pw")).rejects.toThrow("COCONUT is busy. Try again later");
  });

  it("reads the relay's own failure (502, 503, 504: nginx's HTML page) as unreachable", async () => {
    for (const status of [502, 503, 504]) {
      stubFetch(async () => new Response("<html>Bad Gateway</html>", { status }));
      await expect(coconutLogin("a@b.c", "pw")).rejects.toThrow("Could not reach COCONUT");
    }
    expect(getToken()).toBeNull();
  });
});

describe("submitReports", () => {
  it("sends one item in the v1 body shape exactly", async () => {
    stubFetch(okServer());
    const report = buildReport(
      paper,
      { segmentId: "s1", n: 1, smiles: "CCO", link: "https://pubchem.ncbi.nlm.nih.gov/compound/702" },
      { name: "Ethanol", structuralComments: "drawn as salt" },
    );
    const res = await submitReports(TOKEN, [{ segmentId: "s1", report }]);
    expect(res).toEqual([{ segmentId: "s1", ok: true, reportId: "1" }]);
    expect(calls[0]!.url).toBe("/api/v2/coconut/reports/mutate");
    expect(calls[0]!.init.method).toBe("POST");
    expect(new Headers(calls[0]!.init.headers).get("Authorization")).toBe(`Bearer ${TOKEN}`);
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({
      mutate: [
        {
          operation: "create",
          attributes: {
            title: "MARCUS_Submission Rajan 2025",
            evidence: "Isolated from the bark",
            comment: "Paper comment",
            suggested_changes: {
              new_molecule_data: {
                canonical_smiles: "CCO",
                reference_id: "10.1039/d5dd00313j",
                name: "Ethanol",
                link: "https://pubchem.ncbi.nlm.nih.gov/compound/702",
                structural_comments: "drawn as salt",
                references: [
                  {
                    doi: "10.1039/d5dd00313j",
                    organisms: [
                      {
                        name: "Salix alba",
                        parts: ["bark", "leaf"],
                        locations: [{ name: "Jena", ecosystems: ["forest"] }],
                      },
                    ],
                  },
                ],
              },
            },
          },
          relations: [],
        },
      ],
    });
    expect(mutateBody([report])).toEqual(JSON.parse(String(calls[0]!.init.body)));
  });

  it("sends 120 items as 50, 50 and 20 and reports progress", async () => {
    stubFetch(okServer());
    const progress: [number, number][] = [];
    const res = await submitReports(TOKEN, items(120), (done, total) => progress.push([done, total]));
    expect(COCONUT_CHUNK).toBe(50);
    expect(calls.map((c) => bodyOf(c).mutate.length)).toEqual([50, 50, 20]);
    expect(progress).toEqual([
      [50, 120],
      [100, 120],
      [120, 120],
    ]);
    expect(res).toHaveLength(120);
    expect(res.every((r) => r.ok)).toBe(true);
    expect(res[119]).toEqual({ segmentId: "s120", ok: true, reportId: "120" });
  });

  it("resends a chunk answered with 413 as two halves", async () => {
    const ok = okServer();
    stubFetch(async (url, init, n) => (n === 2 ? json({ message: "Too large" }, 413) : ok(url, init)));
    const res = await submitReports(TOKEN, items(120));
    expect(calls.map((c) => bodyOf(c).mutate.length)).toEqual([50, 50, 25, 25, 20]);
    expect(bodyOf(calls[2]!).mutate[0]!.attributes.suggested_changes.new_molecule_data.name).toBe(
      "Name 51",
    );
    expect(res.every((r) => r.ok)).toBe(true);
    expect(res.map((r) => r.segmentId)).toEqual(items(120).map((i) => i.segmentId));
  });

  it("halves on a 422 about the list size, but only once", async () => {
    stubFetch(async () =>
      json({ message: "The mutate field must not have more than 10 items.", errors: { mutate: ["x"] } }, 422),
    );
    const res = await submitReports(TOKEN, items(50));
    expect(calls.map((c) => bodyOf(c).mutate.length)).toEqual([50, 25, 25]);
    expect(res.every((r) => !r.ok)).toBe(true);
  });

  it("does not retry a network error: the chunk is Unknown and sending stops", async () => {
    const ok = okServer();
    stubFetch(async (url, init, n) => {
      if (n === 2) throw new TypeError("Failed to fetch");
      return ok(url, init);
    });
    const res = await submitReports(TOKEN, items(120));
    expect(calls).toHaveLength(2);
    expect(res.slice(0, 50).every((r) => r.ok)).toBe(true);
    expect(res.slice(50, 100)).toEqual(
      items(120)
        .slice(50, 100)
        .map((i) => ({ segmentId: i.segmentId, ok: false, error: "Unknown: check COCONUT before sending again" })),
    );
    expect(UNKNOWN_ERROR).toBe("Unknown: check COCONUT before sending again");
    expect(res.slice(100).every((r) => !r.ok && r.error === NOT_SENT_ERROR)).toBe(true);
  });

  it("treats a timeout like a network error", async () => {
    stubFetch(async () => {
      throw new DOMException("The operation timed out.", "TimeoutError");
    });
    const res = await submitReports(TOKEN, items(3));
    expect(calls).toHaveLength(1);
    expect(res.every((r) => !r.ok && r.error === UNKNOWN_ERROR)).toBe(true);
  });

  it("fails only the refused items of a 422 and resends the rest once", async () => {
    const ok = okServer();
    stubFetch(async (url, init, n) =>
      n === 1
        ? json(
            {
              message: "The given data was invalid.",
              errors: { "mutate.1.attributes.title": ["The title field is required."] },
            },
            422,
          )
        : ok(url, init),
    );
    const res = await submitReports(TOKEN, items(3));
    expect(calls.map((c) => bodyOf(c).mutate.length)).toEqual([3, 2]);
    expect(res).toEqual([
      { segmentId: "s1", ok: true, reportId: "1" },
      { segmentId: "s2", ok: false, error: "The title field is required." },
      { segmentId: "s3", ok: true, reportId: "2" },
    ]);
  });

  it("stops on 401 and asks for a new login", async () => {
    stubFetch(async () => json({ message: "Unauthenticated." }, 401));
    const res = await submitReports(TOKEN, items(60));
    expect(calls).toHaveLength(1);
    expect(res.slice(0, 50).every((r) => !r.ok && /log in/i.test(r.error))).toBe(true);
    expect(res.slice(50).every((r) => !r.ok && r.error === NOT_SENT_ERROR)).toBe(true);
  });

  it("sends only to the MARCUS relay for COCONUT (same origin)", async () => {
    stubFetch(okServer());
    await submitReports(TOKEN, items(2));
    expect(calls.every((c) => c.url.startsWith(`${COCONUT_API}/`))).toBe(true);
    expect(COCONUT_API).toBe("/api/v2/coconut");
  });
});

describe("buildReport", () => {
  it("lets a per-structure organism and comment win over the paper's", () => {
    const r = buildReport(
      paper,
      { segmentId: "s1", n: 1, smiles: "C" },
      {
        name: "Methane",
        structuralComments: "",
        comment: "Own comment",
        organism: { name: "Quercus robur", parts: "", location: "", ecosystems: "" },
      },
    );
    expect(r.comment).toBe("Own comment");
    expect(r.suggested_changes.new_molecule_data.references).toEqual([
      { doi: paper.doi, organisms: [{ name: "Quercus robur", parts: [], locations: [] }] },
    ]);
  });

  it("inherits the paper's organism when the override is blank", () => {
    const r = buildReport(
      paper,
      { segmentId: "s1", n: 1, smiles: "C" },
      { name: "M", structuralComments: "", comment: " ", organism: { name: "", parts: "x", location: "", ecosystems: "" } },
    );
    expect(r.comment).toBe("Paper comment");
    expect(r.suggested_changes.new_molecule_data.references[0]!.organisms[0]!.name).toBe("Salix alba");
  });
});

describe("comma-separated lists", () => {
  it("splits on commas, keeps a double-quoted item whole and reads a doubled quote", () => {
    expect(splitList(' bark, leaf ,, "roots, stems", "the ""inner"" bark" ')).toEqual([
      "bark",
      "leaf",
      "roots, stems",
      'the "inner" bark',
    ]);
  });

  it("reads a quote that does not open an item, or is never closed, as text", () => {
    expect(splitList('5" root, stem')).toEqual(['5" root', "stem"]);
    expect(splitList('"roots, stems')).toEqual(['"roots', "stems"]);
    expect(splitList('"a" b, c')).toEqual(["a b", "c"]);
  });

  it("carries a quoted part and ecosystem into the report as one item", () => {
    const r = buildReport(
      paper,
      { segmentId: "s1", n: 1, smiles: "C" },
      {
        name: "M",
        structuralComments: "",
        organism: {
          name: "Taxus brevifolia",
          parts: '"roots, stems", bark',
          location: "Oregon",
          ecosystems: '"forest, temperate"',
        },
      },
    );
    expect(r.suggested_changes.new_molecule_data.references[0]!.organisms).toEqual([
      {
        name: "Taxus brevifolia",
        parts: ["roots, stems", "bark"],
        locations: [{ name: "Oregon", ecosystems: ["forest, temperate"] }],
      },
    ]);
  });
});

describe("sent store", () => {
  it("keeps sent ids per paper in localStorage", () => {
    markSent("p1", ["a", "b"]);
    markSent("p1", ["c"]);
    expect([...sentIds("p1")].sort()).toEqual(["a", "b", "c"]);
    expect(localStorage.getItem("marcus-coconut-sent:p1")).not.toBeNull();
    expect(sentIds("p2").size).toBe(0);
  });

  it("keeps unknown ids until they are sent", () => {
    markUnknown("p1", ["a", "b"]);
    expect([...unknownIds("p1")].sort()).toEqual(["a", "b"]);
    markSent("p1", ["a"]);
    expect([...unknownIds("p1")]).toEqual(["b"]);
    expect(localStorage.getItem("marcus-coconut-unknown:p1")).toBe('["b"]');
  });

  it("survives a localStorage that throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => markSent("p1", ["a"])).not.toThrow();
    expect(sentIds("p1").size).toBe(0);
  });
});

// --- Components ----------------------------------------------------------------------------

const structures: SubmitStructure[] = [
  { segmentId: "s1", n: 1, smiles: "CCO", name: "Ethanol" },
  { segmentId: "s2", n: 2, smiles: "CCN", name: "Ethylamine" },
  { segmentId: "s3", n: 3, smiles: "CCC", name: "Propane" },
];

function renderForm(list = structures) {
  return render(
    <SubmitForm
      paper={{ id: "p1", title: "A paper on willow", doi: "10.1/x" }}
      structures={list}
      onClose={() => {}}
    />,
  );
}

function fillPaper() {
  const sheet = screen.getByRole("group", { name: "Paper" });
  fireEvent.change(within(sheet).getByLabelText("Title"), { target: { value: "T" } });
  fireEvent.change(within(sheet).getByLabelText("Organism"), { target: { value: "Salix alba" } });
}

function row(tag: string) {
  return screen.getByRole("listitem", { name: new RegExp(`\\[${tag}\\]`) });
}

describe("CoconutLogin", () => {
  it("logs in and hands the token back; the password is not logged", async () => {
    const log = vi.spyOn(console, "log");
    const err = vi.spyOn(console, "error");
    stubFetch(async () => json({ access_token: TOKEN }));
    const onLoggedIn = vi.fn();
    render(<CoconutLogin onLoggedIn={onLoggedIn} />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.c" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw" } });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() => expect(onLoggedIn).toHaveBeenCalledWith(TOKEN));
    expect(log).not.toHaveBeenCalled();
    expect(err).not.toHaveBeenCalled();
  });

  it("shows a failed login", async () => {
    stubFetch(async () => json({ message: "x" }, 401));
    render(<CoconutLogin onLoggedIn={() => {}} />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.c" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw" } });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong email or password");
  });
});

describe("SubmitForm", () => {
  it("asks for a COCONUT login first, then shows the form", async () => {
    stubFetch(async () => json({ access_token: TOKEN }));
    renderForm();
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.c" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw" } });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("group", { name: "Paper" })).toBeInTheDocument();
    expect(sessionStorage.getItem(TOKEN_KEY)).toBe(TOKEN);
  });

  it("fills the paper fields once and sends every structure with progress", async () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    stubFetch(okServer());
    renderForm();
    const sheet = screen.getByRole("group", { name: "Paper" });
    expect(within(sheet).getByLabelText("DOI")).toHaveValue("10.1/x");
    expect(within(sheet).getByLabelText("Evidence")).toHaveValue("A paper on willow");
    fillPaper();
    fireEvent.click(screen.getByRole("button", { name: "Send 3 to COCONUT" }));
    expect(await screen.findByText("Report 1")).toBeInTheDocument();
    const sent = calls.flatMap((c) => bodyOf(c).mutate.map((m) => m.attributes));
    expect(sent.map((a) => a.suggested_changes.new_molecule_data.name)).toEqual([
      "Ethanol",
      "Ethylamine",
      "Propane",
    ]);
    expect(sent.every((a) => a.title === "T")).toBe(true);
    expect([...sentIds("p1")].sort()).toEqual(["s1", "s2", "s3"]);
  });

  it("shows progress while chunks are sent", async () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    let release!: () => void;
    const ok = okServer();
    stubFetch(async (url, init, n) => {
      if (n === 2) await new Promise<void>((r) => (release = r));
      return ok(url, init);
    });
    const many = Array.from({ length: 60 }, (_, i) => ({
      segmentId: `s${i + 1}`,
      n: i + 1,
      smiles: "C",
      name: `N${i + 1}`,
    }));
    renderForm(many);
    fillPaper();
    fireEvent.click(screen.getByRole("button", { name: "Send 60 to COCONUT" }));
    expect(await screen.findByText("Sent 50 of 60")).toBeInTheDocument();
    await act(async () => release());
    expect(await screen.findByText("Report 60")).toBeInTheDocument();
  });

  it("sends once on a double click", async () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    stubFetch(okServer());
    renderForm();
    fillPaper();
    const button = screen.getByRole("button", { name: "Send 3 to COCONUT" });
    // Both clicks land before React re-renders the button as disabled: only the guard holds.
    act(() => {
      button.click();
      button.click();
    });
    await screen.findByText("Report 1");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("leaves already sent structures out until Send again is confirmed", async () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    markSent("p1", ["s2"]);
    stubFetch(okServer());
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderForm();
    fillPaper();
    expect(within(row("02")).getByText("Already sent")).toBeInTheDocument();
    const again = within(row("02")).getByRole("checkbox", { name: "Send again" });
    fireEvent.click(again);
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(again).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Send 2 to COCONUT" })).toBeInTheDocument();
    fireEvent.click(again);
    expect(again).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Send 3 to COCONUT" }));
    await screen.findByText("Report 1");
    expect(bodyOf(calls[0]!).mutate).toHaveLength(3);
  });

  it("sends only the structures not sent before", async () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    markSent("p1", ["s2"]);
    stubFetch(okServer());
    renderForm();
    fillPaper();
    fireEvent.click(screen.getByRole("button", { name: "Send 2 to COCONUT" }));
    await screen.findByText("Report 1");
    expect(
      bodyOf(calls[0]!).mutate.map((m) => m.attributes.suggested_changes.new_molecule_data.name),
    ).toEqual(["Ethanol", "Propane"]);
  });

  it("lets a structure's own organism win over the paper's", async () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    stubFetch(okServer());
    renderForm();
    fillPaper();
    const r2 = row("02");
    fireEvent.click(within(r2).getByRole("button", { name: "More" }));
    fireEvent.change(within(r2).getByLabelText("Organism"), { target: { value: "Quercus robur" } });
    fireEvent.change(within(r2).getByLabelText("Name for structure 2"), {
      target: { value: "Renamed" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send 3 to COCONUT" }));
    await screen.findByText("Report 1");
    const sent = bodyOf(calls[0]!).mutate.map((m) => m.attributes.suggested_changes.new_molecule_data);
    expect(sent[0]!.references[0]!.organisms[0]!.name).toBe("Salix alba");
    expect(sent[1]!.references[0]!.organisms[0]!.name).toBe("Quercus robur");
    expect(sent[1]!.name).toBe("Renamed");
  });

  it("keeps Send off until the required fields are filled", () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    renderForm([{ segmentId: "s1", n: 1, smiles: "C" }]);
    const send = screen.getByRole("button", { name: "Send 1 to COCONUT" });
    expect(send).toBeDisabled();
    fillPaper();
    expect(send).toBeDisabled(); // the structure has no name yet
    fireEvent.change(screen.getByLabelText("Name for structure 1"), { target: { value: "Methane" } });
    expect(send).toBeEnabled();
  });

  it("marks the required fields (3.3.2) and Send says why it is off", () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    renderForm();
    const sheet = screen.getByRole("group", { name: "Paper" });
    for (const name of ["Title", "Evidence", "Organism"]) {
      const field = within(sheet).getByLabelText(name);
      expect(field).toBeRequired();
      expect(field.closest(".coconut-field")).toHaveTextContent(/Required/);
    }
    for (const name of ["DOI", "Comment"]) {
      expect(within(sheet).getByLabelText(name)).not.toBeRequired();
    }
    expect(screen.getByLabelText("Name for structure 1")).toBeRequired();
    const send = screen.getByRole("button", { name: "Send 3 to COCONUT" });
    expect(send).toBeDisabled();
    expect(send).toHaveAccessibleDescription("Fill in title, organism");
  });

  it("sends the token only on the relay's mutate call, never to the MARCUS API", async () => {
    const ok = okServer();
    stubFetch(async (url, init) => {
      if (url.includes("/auth/login")) return json({ access_token: TOKEN });
      if (!url.startsWith(`${COCONUT_API}/`)) return json({ papers: [], updated: 0 });
      return ok(url, init);
    });
    renderForm();
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.c" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw" } });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    await screen.findByRole("group", { name: "Paper" });
    fillPaper();
    fireEvent.click(screen.getByRole("button", { name: "Send 3 to COCONUT" }));
    await screen.findByText("Report 1");
    // The app's own calls, made while the COCONUT token is stored in this tab.
    await api.listPapers();
    await api.putBulkCuration("p1", [{ segment_id: "s1", status: "accepted" }]);
    const v2 = calls.filter((c) => !c.url.startsWith(`${COCONUT_API}/`));
    expect(v2).toHaveLength(2);
    for (const c of v2) {
      expect(c.url).not.toContain(TOKEN);
      expect(String(c.init.body ?? "")).not.toContain(TOKEN);
      expect(JSON.stringify([...new Headers(c.init.headers).entries()])).not.toContain(TOKEN);
    }
    const toCoconut = calls.filter((c) => c.url.startsWith(`${COCONUT_API}/`));
    const withToken = toCoconut.filter((c) =>
      JSON.stringify([...new Headers(c.init.headers).entries()]).includes(TOKEN),
    );
    expect(withToken.map((c) => c.url)).toEqual([`${COCONUT_API}/reports/mutate`]);
  });

  it("keeps Unknown structures out of the next send until Send again is confirmed", async () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    stubFetch(async () => {
      throw new TypeError("Failed to fetch");
    });
    const { unmount } = renderForm();
    fillPaper();
    fireEvent.click(screen.getByRole("button", { name: "Send 3 to COCONUT" }));
    expect(await screen.findAllByText(UNKNOWN_ERROR)).toHaveLength(3);
    expect([...unknownIds("p1")].sort()).toEqual(["s1", "s2", "s3"]);
    fireEvent.click(screen.getByRole("button", { name: "Back to form" }));
    expect(within(row("02")).getByText("Unknown")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send 0 to COCONUT" })).toBeDisabled();
    unmount();

    // Still held after the form is opened again.
    const ok = okServer();
    stubFetch(ok);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderForm();
    fillPaper();
    expect(screen.getByRole("button", { name: "Send 0 to COCONUT" })).toBeDisabled();
    fireEvent.click(within(row("02")).getByRole("checkbox", { name: "Send again" }));
    expect(confirm).toHaveBeenCalledWith(expect.stringMatching(/may already have/));
    fireEvent.click(screen.getByRole("button", { name: "Send 1 to COCONUT" }));
    await screen.findByText("Report 1");
    expect(bodyOf(calls[0]!).mutate).toHaveLength(1);
    expect([...unknownIds("p1")].sort()).toEqual(["s1", "s3"]);
    expect(sentIds("p1").has("s2")).toBe(true);
  });

  it("moves the focus to the results heading", async () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    stubFetch(okServer());
    renderForm();
    fillPaper();
    fireEvent.click(screen.getByRole("button", { name: "Send 3 to COCONUT" }));
    await screen.findByText("Report 1");
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "3 sent" }));
  });

  it("starts in the first field", () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    renderForm();
    expect(document.activeElement).toBe(screen.getByLabelText("Title"));
  });

  it("gives each row its own names and controls only an open detail", () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    renderForm();
    expect(screen.getByLabelText("Name for structure 3")).toHaveValue("Propane");
    const more = within(row("02")).getByRole("button", { name: "More" });
    expect(more).not.toHaveAttribute("aria-controls");
    fireEvent.click(more);
    const id = more.getAttribute("aria-controls");
    expect(id && document.getElementById(id)).toBeTruthy();
  });

  it("shows each failed structure's error as text and the others' report ids", async () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    const ok = okServer();
    stubFetch(async (url, init, n) =>
      n === 1
        ? json(
            {
              message: "invalid",
              errors: { "mutate.1.attributes.title": ['<img src=x onerror="alert(1)">'] },
            },
            422,
          )
        : ok(url, init),
    );
    renderForm();
    fillPaper();
    fireEvent.click(screen.getByRole("button", { name: "Send 3 to COCONUT" }));
    expect(await screen.findByText("Report 1")).toBeInTheDocument();
    expect(within(row("01")).getByText("Report 1")).toBeInTheDocument();
    expect(within(row("02")).getByText('<img src=x onerror="alert(1)">')).toBeInTheDocument();
    expect(within(row("03")).getByText("Report 2")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    expect(sentIds("p1").has("s2")).toBe(false);
  });

  it("goes back to login when COCONUT says the login expired", async () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    stubFetch(async () => json({ message: "Unauthenticated." }, 401));
    renderForm();
    fillPaper();
    fireEvent.click(screen.getByRole("button", { name: "Send 3 to COCONUT" }));
    expect(await screen.findAllByText(/log in to COCONUT again/i)).not.toHaveLength(0);
    expect(getToken()).toBeNull();
  });
});

describe("SubmitForm closing", () => {
  function escape() {
    fireEvent.keyDown(screen.getByRole("dialog", { hidden: true }), { key: "Escape" });
  }

  it("closes on Escape without asking when nothing was typed", () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    const confirm = vi.spyOn(window, "confirm");
    const onClose = vi.fn();
    render(<SubmitForm paper={{ id: "p1", title: null, doi: null }} structures={structures} onClose={onClose} />);
    escape();
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(confirm).not.toHaveBeenCalled();
  });

  it("asks before Escape or Close throws typed values away", () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    const onClose = vi.fn();
    render(<SubmitForm paper={{ id: "p1", title: null, doi: null }} structures={structures} onClose={onClose} />);
    fireEvent.change(screen.getByLabelText("Name for structure 1"), { target: { value: "Typed" } });
    escape();
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not close while a send runs", async () => {
    sessionStorage.setItem(TOKEN_KEY, TOKEN);
    let release!: () => void;
    const ok = okServer();
    stubFetch(async (url, init) => {
      await new Promise<void>((r) => (release = r));
      return ok(url, init);
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const onClose = vi.fn();
    render(<SubmitForm paper={{ id: "p1", title: "T", doi: null }} structures={structures} onClose={onClose} />);
    fillPaper();
    fireEvent.click(screen.getByRole("button", { name: "Send 3 to COCONUT" }));
    await screen.findByText("Sent 0 of 3");
    escape();
    expect(onClose).not.toHaveBeenCalled();
    await act(async () => release());
    await screen.findByText("Report 1");
    escape();
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("SubmitResults", () => {
  it("counts sent and failed", () => {
    render(
      <SubmitResults
        structures={structures}
        results={[
          { segmentId: "s1", ok: true, reportId: "7" },
          { segmentId: "s2", ok: false, error: "Nope" },
          { segmentId: "s3", ok: true, reportId: null },
        ]}
        onBack={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText("2 sent, 1 failed")).toBeInTheDocument();
    expect(within(row("01")).getByText("Report 7")).toBeInTheDocument();
    expect(within(row("02")).getByText("Nope")).toBeInTheDocument();
    expect(within(row("03")).getByText("Sent")).toBeInTheDocument();
  });
});
