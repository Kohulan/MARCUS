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

function show(onClose = vi.fn()) {
  render(
    <CoconutSidePanel
      paper={PAPER}
      segment={SEG}
      n={2}
      start={START}
      built={{ segmentId: "s1", n: 1 }}
      row={{ compound: "20a", groups: { R1: "OMe" } }}
      onClose={onClose}
    />,
  );
  return onClose;
}

beforeEach(() => sessionStorage.clear());
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
