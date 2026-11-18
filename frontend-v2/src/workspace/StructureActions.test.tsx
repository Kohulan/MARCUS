import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StructureActions, { fileStem } from "./StructureActions";

function readBlob(b: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsText(b);
  });
}

let saved: { name: string; text: Promise<string> }[];

beforeEach(() => {
  saved = [];
  URL.createObjectURL = vi.fn((b: Blob) => {
    saved.push({ name: "", text: readBlob(b) });
    return "blob:x";
  });
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    saved[saved.length - 1]!.name = this.download;
  });
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const base = {
  name: "paper one.pdf",
  n: 3,
  smiles: "CCO",
  depictionUrl: "/api/v2/segments/s/depiction?v=k",
};

describe("StructureActions", () => {
  it("builds a safe file stem", () => {
    expect(fileStem("../a b.pdf", 2)).toBe("a_b-2");
    expect(fileStem("", 1)).toBe("structure-1");
  });

  it("downloads the curated molfile in preference", async () => {
    const convert = vi.fn();
    render(
      <StructureActions
        {...base}
        curatedMolfile="CURATED"
        predictionMolfile="PRED"
        convert={convert}
      />,
    );
    fireEvent.click(screen.getByText("Download molfile"));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0]!.name).toBe("paper_one-3.mol");
    expect(await saved[0]!.text).toBe("CURATED");
    expect(convert).not.toHaveBeenCalled();
  });

  it("uses the prediction molfile, else converts the SMILES", async () => {
    const convert = vi.fn().mockResolvedValue("CONVERTED");
    const { unmount } = render(
      <StructureActions {...base} predictionMolfile="PRED" convert={convert} />,
    );
    fireEvent.click(screen.getByText("Copy molfile"));
    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith("PRED"),
    );
    unmount();
    render(<StructureActions {...base} convert={convert} />);
    fireEvent.click(screen.getByText("Copy molfile"));
    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith("CONVERTED"),
    );
    expect(convert).toHaveBeenCalledWith("CCO");
  });

  it("copies the SMILES", async () => {
    render(<StructureActions {...base} />);
    fireEvent.click(screen.getByText("Copy SMILES"));
    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith("CCO"),
    );
    expect(await screen.findByText("SMILES copied")).toBeTruthy();
  });

  it("leaves Copy SMILES out where the SMILES has its own Copy", () => {
    render(<StructureActions {...base} copySmiles={false} />);
    expect(screen.queryByText("Copy SMILES")).toBeNull();
    expect(screen.getByText("Copy molfile")).toBeInTheDocument();
  });

  it("saves the depiction svg", async () => {
    const f = vi.fn().mockResolvedValue(new Response("<svg/>"));
    vi.stubGlobal("fetch", f);
    render(<StructureActions {...base} />);
    fireEvent.click(screen.getByText("Download image"));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(f.mock.calls[0]![0]).toBe(base.depictionUrl);
    expect(saved[0]!.name).toBe("paper_one-3.svg");
    expect(await saved[0]!.text).toBe("<svg/>");
  });

  it("shows the PubChem hit as text with a safe link", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ IdentifierList: { CID: [702] } })),
        )
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              PropertyTable: { Properties: [{ Title: "<b>Ethanol</b>" }] },
            }),
          ),
        ),
    );
    const { container } = render(<StructureActions {...base} />);
    fireEvent.click(screen.getByText("Look up in PubChem"));
    expect(await screen.findByText("CID 702")).toBeTruthy();
    expect(container.querySelector("b")).toBeNull();
    const a = screen.getByRole("link", { name: "Open in PubChem" });
    expect(a.getAttribute("href")).toBe(
      "https://pubchem.ncbi.nlm.nih.gov/compound/702",
    );
    expect(a.getAttribute("rel")).toContain("noopener");
  });

  it("says so when PubChem has nothing, and calls Edit and Compare", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    const onEdit = vi.fn();
    const onCompare = vi.fn();
    render(
      <StructureActions {...base} onEdit={onEdit} onCompare={onCompare} />,
    );
    fireEvent.click(screen.getByText("Look up in PubChem"));
    expect(await screen.findByText("Not found in PubChem")).toBeTruthy();
    fireEvent.click(screen.getByText("Edit"));
    fireEvent.click(screen.getByText("Compare"));
    expect(onEdit).toHaveBeenCalled();
    expect(onCompare).toHaveBeenCalled();
  });

  it("drops the lookup and aborts it when the structure changes", async () => {
    let signal: AbortSignal | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_u: string, init: RequestInit) => {
        signal = init.signal as AbortSignal;
        return new Promise<Response>(() => {});
      }),
    );
    const { rerender } = render(<StructureActions {...base} />);
    fireEvent.click(screen.getByText("Look up in PubChem"));
    expect(await screen.findByText("Looking up…")).toBeTruthy();
    rerender(<StructureActions {...base} smiles="CCN" />);
    expect(screen.queryByText("Looking up…")).toBeNull();
    expect(signal?.aborted).toBe(true);
  });

  it("clears a shown hit when the structure changes", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ IdentifierList: { CID: [702] } })),
        )
        .mockResolvedValueOnce(new Response("{}")),
    );
    const { rerender } = render(<StructureActions {...base} />);
    fireEvent.click(screen.getByText("Look up in PubChem"));
    expect(await screen.findByText("CID 702")).toBeTruthy();
    rerender(<StructureActions {...base} smiles="CCN" />);
    expect(screen.queryByText("CID 702")).toBeNull();
  });

  it("aborts an in-flight lookup on unmount", async () => {
    let signal: AbortSignal | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_u: string, init: RequestInit) => {
        signal = init.signal as AbortSignal;
        return new Promise<Response>(() => {});
      }),
    );
    const { unmount } = render(<StructureActions {...base} />);
    fireEvent.click(screen.getByText("Look up in PubChem"));
    await screen.findByText("Looking up…");
    unmount();
    expect(signal?.aborted).toBe(true);
  });
});
