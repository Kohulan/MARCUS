// The Paper view's COCONUT side form (owner decision 2026-11-25): filled, login at the end
// without a token, one report sent, MARCUS JSON downloaded, the sent state.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PaperDetail, PredictionOut, SegmentOut } from "../api/types";
import * as coconutApi from "./coconutApi";
import CoconutSidePanel from "./CoconutSidePanel";

const pred: PredictionOut = {
  id: "p1", engine: "molparser", engine_version: "1", smiles: "COc1ccccc1", molfile: null,
  valid: true, ms: 1, cached: false, created_at: "2026-11-25T10:00:00Z",
};
const SEG: SegmentOut = {
  id: "s2", page: 3, idx: 10001, bbox: [0, 0, 1, 1], compound_id: "20a", built_from: "s1",
  curation: { status: "accepted", smiles: null, molfile: null, note: null }, predictions: [pred],
};
const PAPER = {
  id: "3f2a9c1e-7b4d-4e8a-9c2f-1a2b3c4d5e6f", doi: "10.1021/acs.jnatprod.6c00411",
  title: "Prenylated Isoflavones", display_name: "jnp.pdf", engine: "decimer",
  first_author: "Fang", year: 2026,
} as unknown as PaperDetail;
const START = { organisms: [{ name: "Millettia dura", parts: "", location: "", ecosystems: "" }], note: undefined };

function panel(segment: SegmentOut, onClose = vi.fn()) {
  return (
    <CoconutSidePanel
      paper={PAPER}
      segment={segment}
      n={2}
      start={START}
      built={{ segmentId: "s1", n: 1 }}
      row={{ compound: "20a", groups: { R1: "OMe" } }}
      onClose={onClose}
    />
  );
}

function show(onClose = vi.fn()) {
  render(panel(SEG, onClose));
  return onClose;
}

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear(); // the sent records
});
afterEach(() => vi.restoreAllMocks());

describe("COCONUT side form", () => {
  it("is filled, and asks for the login at its end without a token", () => {
    vi.spyOn(coconutApi, "getToken").mockReturnValue(null);
    show();
    expect(screen.getByLabelText("Name")).toHaveValue("Compound 20a");
    expect(screen.getByLabelText("Structural comments")).toHaveValue("Built from [01]: R1 = OMe (row 20a)");
    expect(screen.getByLabelText("DOI")).toHaveValue("10.1021/acs.jnatprod.6c00411");
    const login = screen.getByRole("heading", { name: "Log in to COCONUT" });
    const download = screen.getByRole("button", { name: "Download JSON" });
    // the login comes after every field
    expect(screen.getByLabelText("Name").compareDocumentPosition(login) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(download).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send to COCONUT" })).toBeNull();
  });

  it("opens at its top: the heading has focus, not the login at its end (live check 2026-11-26)", () => {
    vi.spyOn(coconutApi, "getToken").mockReturnValue(null);
    show();
    expect(screen.getByRole("heading", { name: "COCONUT [02]" })).toHaveFocus();
    expect(screen.getByLabelText("Email")).not.toHaveFocus();
  });

  it("sends one report with what the form shows", async () => {
    vi.spyOn(coconutApi, "getToken").mockReturnValue("tok");
    const send = vi
      .spyOn(coconutApi, "submitReports")
      .mockResolvedValue([{ segmentId: "s2", ok: true, reportId: "r1" }]);
    show();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Fangflavone" } });
    fireEvent.click(screen.getByRole("button", { name: "Send to COCONUT" }));
    await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    const [token, items] = send.mock.calls[0]!;
    expect(token).toBe("tok");
    expect(items).toHaveLength(1);
    expect(items[0]!.report.suggested_changes.new_molecule_data.name).toBe("Fangflavone");
    expect(items[0]!.report.suggested_changes.new_molecule_data.canonical_smiles).toBe("COc1ccccc1");
    expect(await screen.findByText("Sent to COCONUT")).toBeInTheDocument();
  });

  it("downloads the MARCUS JSON", () => {
    vi.spyOn(coconutApi, "getToken").mockReturnValue(null);
    const blobs: Blob[] = [];
    URL.createObjectURL = vi.fn((b: Blob) => { blobs.push(b); return "blob:x"; }) as never;
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    show();
    fireEvent.click(screen.getByRole("button", { name: "Download JSON" }));
    expect(click).toHaveBeenCalledTimes(1);
    expect(blobs).toHaveLength(1);
    expect(blobs[0]!.type).toBe("application/json");
  });

  it("Close and Esc close it", () => {
    vi.spyOn(coconutApi, "getToken").mockReturnValue(null);
    const onClose = show();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    fireEvent.keyDown(screen.getByLabelText("Name"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});

describe("final review (fable, 2026-11-25)", () => {
  const send = () =>
    vi.spyOn(coconutApi, "submitReports").mockResolvedValue([{ segmentId: "s2", ok: true, reportId: "r" }]);

  it("sends the structure the card shows now, not the one it showed when the form opened", async () => {
    vi.spyOn(coconutApi, "getToken").mockReturnValue("tok");
    const spy = send();
    const { rerender } = render(panel(SEG));
    const edited = { ...SEG, curation: { status: "accepted" as const, smiles: "CCO", molfile: null, note: null } };
    rerender(panel(edited));
    fireEvent.click(screen.getByRole("button", { name: "Send to COCONUT" }));
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(spy.mock.calls[0]![1][0]!.report.suggested_changes.new_molecule_data.canonical_smiles).toBe("CCO");
  });

  it("a structure that is not accepted cannot be sent", () => {
    vi.spyOn(coconutApi, "getToken").mockReturnValue("tok");
    render(panel({ ...SEG, curation: { status: "rejected", smiles: null, molfile: null, note: null } }));
    expect(screen.queryByRole("button", { name: "Send to COCONUT" })).toBeNull();
    expect(screen.getByText("Accept [02] to send it")).toBeInTheDocument();
  });

  it("sends only the organism the form shows, and says it is the model's suggestion", async () => {
    vi.spyOn(coconutApi, "getToken").mockReturnValue("tok");
    const spy = send();
    render(
      <CoconutSidePanel
        paper={PAPER}
        segment={SEG}
        n={2}
        start={{
          organisms: [
            { name: "Millettia dura", parts: "", location: "", ecosystems: "" },
            { name: "Hidden plant", parts: "", location: "", ecosystems: "" },
          ],
          note: "Organisms: model suggestion",
        }}
        built={null}
        row={null}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("Organisms: model suggestion")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Send to COCONUT" }));
    await waitFor(() => expect(spy).toHaveBeenCalled());
    const refs = spy.mock.calls[0]![1][0]!.report.suggested_changes.new_molecule_data.references;
    expect(refs[0]!.organisms.map((o) => o.name)).toEqual(["Millettia dura"]);
  });

  it("an unknown outcome is recorded, so the next send asks first", async () => {
    vi.spyOn(coconutApi, "getToken").mockReturnValue("tok");
    vi.spyOn(coconutApi, "submitReports").mockResolvedValue([
      { segmentId: "s2", ok: false, error: coconutApi.UNKNOWN_ERROR },
    ]);
    render(panel(SEG));
    fireEvent.click(screen.getByRole("button", { name: "Send to COCONUT" }));
    await waitFor(() => expect(coconutApi.unknownIds(PAPER.id).has("s2")).toBe(true));
  });

  it("an expired login brings the login back", async () => {
    sessionStorage.setItem(coconutApi.TOKEN_KEY, "tok");
    vi.spyOn(coconutApi, "submitReports").mockResolvedValue([
      { segmentId: "s2", ok: false, error: coconutApi.AUTH_ERROR },
    ]);
    render(panel(SEG));
    fireEvent.click(screen.getByRole("button", { name: "Send to COCONUT" }));
    expect(await screen.findByRole("heading", { name: "Log in to COCONUT" })).toBeInTheDocument();
    expect(sessionStorage.getItem(coconutApi.TOKEN_KEY)).toBeNull();
    expect(coconutApi.getToken()).toBeNull();
  });

  it("Send waits for a name, a title, the evidence and an organism", () => {
    vi.spyOn(coconutApi, "getToken").mockReturnValue("tok");
    render(panel({ ...SEG, compound_id: null }));
    expect(screen.getByRole("button", { name: "Send to COCONUT" })).toBeDisabled();
    expect(screen.getByText("Fill in name")).toBeInTheDocument();
  });

  it("Send waits for a DOI (COCONUT needs one on each reference)", () => {
    vi.spyOn(coconutApi, "getToken").mockReturnValue("tok");
    render(panel(SEG));
    const send = screen.getByRole("button", { name: "Send to COCONUT" });
    expect(send).toBeEnabled();
    fireEvent.change(screen.getByLabelText("DOI"), { target: { value: "  " } });
    expect(send).toBeDisabled();
    expect(screen.getByText("Fill in DOI")).toBeInTheDocument();
  });

  describe("the annotation ends after the form opened (owner 2026-11-27)", () => {
    const EMPTY = { organisms: [], note: undefined };
    const LATE = {
      organisms: [{ name: "Wikstroemia nutans", parts: "stems, roots", location: "China", ecosystems: "" }],
      note: "Organisms: model suggestion",
    };
    function late(start: typeof EMPTY | typeof LATE, annotating: boolean) {
      return (
        <CoconutSidePanel paper={PAPER} segment={SEG} n={2} start={start} built={null} row={null}
          annotating={annotating} onClose={vi.fn()} />
      );
    }

    it("says it waits, then fills the organism, its parts and place", () => {
      vi.spyOn(coconutApi, "getToken").mockReturnValue(null);
      const { rerender } = render(late(EMPTY, true));
      expect(screen.getByLabelText("Organism")).toHaveValue("");
      expect(screen.getByRole("status")).toHaveTextContent("Annotation running");
      rerender(late(LATE, false));
      expect(screen.getByLabelText("Organism")).toHaveValue("Wikstroemia nutans");
      expect(screen.getByLabelText("Parts")).toHaveValue("stems, roots");
      expect(screen.getByLabelText("Location")).toHaveValue("China");
      expect(screen.getByText("Organisms: model suggestion")).toBeInTheDocument();
      expect(screen.queryByText(/Annotation running/)).toBeNull();
    });

    it("keeps what the curator typed meanwhile", () => {
      vi.spyOn(coconutApi, "getToken").mockReturnValue(null);
      const { rerender } = render(late(EMPTY, true));
      fireEvent.change(screen.getByLabelText("Organism"), { target: { value: "Typed plant" } });
      rerender(late(LATE, false));
      expect(screen.getByLabelText("Organism")).toHaveValue("Typed plant");
      expect(screen.getByLabelText("Location")).toHaveValue("");
    });
  });
});
