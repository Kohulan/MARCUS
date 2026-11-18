// The structure editor dialog: the Ketcher frame is talked to only through the bridge, a
// save from the drawing or the SMILES field goes through the caller's onSave, and a
// segment caller (useSaveCuration + editorChange) never loses the note.
import { QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { createQueryClient, keys, useSaveCuration } from "../api/queries";
import type { CurationOut, PaperDetail } from "../api/types";
import Editor, { editorChange, type EditorStructure } from "./Editor";

const ORIGIN = window.location.origin;

function frame(): HTMLIFrameElement {
  return screen.getByTitle("Structure editor") as HTMLIFrameElement;
}

/** A message as the Ketcher frame would post it. */
function fromKetcher(data: unknown, source: Window | null = frame().contentWindow) {
  act(() => {
    window.dispatchEvent(new MessageEvent("message", { data, origin: ORIGIN, source }));
  });
}

function paper(curation: CurationOut | null): PaperDetail {
  return {
    id: "p1",
    segments: [
      {
        id: "s1",
        page: 0,
        idx: 0,
        bbox: [0, 0, 10, 10],
        curation,
        predictions: [],
      },
    ],
  } as unknown as PaperDetail;
}

/** What the hook-up does for a segment: save through useSaveCuration with editorChange. */
function SegmentEditor({ current, onClose }: { current: CurationOut; onClose: () => void }) {
  const { save } = useSaveCuration("p1");
  return (
    <Editor
      initial={{ smiles: current.smiles, molfile: current.molfile }}
      onSave={async (s) => {
        await save("s1", editorChange(current, s));
      }}
      onClose={onClose}
    />
  );
}

function renderSegment(current: CurationOut) {
  const client = createQueryClient();
  client.setQueryData(keys.paper("p1"), paper(current));
  const put = vi
    .spyOn(api, "putCuration")
    .mockImplementation(async (_id, body) => ({ ...body }) as CurationOut);
  const onClose = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <SegmentEditor current={current} onClose={onClose} />
    </QueryClientProvider>,
  );
  return { put, onClose, client };
}

function renderEditor(
  opts: {
    initial?: { smiles: string | null; molfile: string | null };
    onSave?: (s: EditorStructure) => Promise<void>;
  } = {},
) {
  const onSave = vi.fn(opts.onSave ?? (async () => {}));
  const onClose = vi.fn();
  const { unmount } = render(
    <Editor
      initial={opts.initial ?? { smiles: "c1ccccc1", molfile: "BENZENE" }}
      onSave={onSave}
      onClose={onClose}
    />,
  );
  return { onSave, onClose, unmount };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Editor", () => {
  it("opens a dialog with the SMILES field above the Ketcher frame", () => {
    renderEditor();
    expect(screen.getByRole("dialog", { name: "Edit structure" })).toBeInTheDocument();
    expect(screen.getByLabelText("SMILES")).toHaveValue("c1ccccc1");
    const iframe = frame();
    expect(iframe.getAttribute("src")).toBe("/ketcher/");
    expect(iframe.getAttribute("sandbox")).toBe("allow-scripts allow-same-origin");
    expect(
      screen.getByLabelText("SMILES").compareDocumentPosition(iframe) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.getByText("Loading editor…")).toBeInTheDocument();
  });

  it("answers marcus:ready with marcus:load to its own origin, and only then", () => {
    renderEditor();
    const post = vi.spyOn(frame().contentWindow as Window, "postMessage");
    post.mockImplementation(() => {});
    fromKetcher({ type: "marcus:ready" }, window); // not the frame
    fromKetcher({ type: "marcus:ready", molfile: "x" }); // wrong shape
    expect(post).not.toHaveBeenCalled();
    fromKetcher({ type: "marcus:ready" });
    expect(post).toHaveBeenCalledWith(
      { type: "marcus:load", molfile: "BENZENE", smiles: "c1ccccc1" },
      ORIGIN,
    );
    expect(screen.queryByText("Loading editor…")).toBeNull();
  });

  it("a drawing saved in the frame goes to onSave with its SMILES and molfile, then closes", async () => {
    const { onSave, onClose } = renderEditor();
    fromKetcher({ type: "marcus:save", molfile: "M2", smiles: "CCO" });
    expect(onSave).toHaveBeenCalledWith({ smiles: "CCO", molfile: "M2" });
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it("ignores a save from another origin or another window", () => {
    const { onSave } = renderEditor();
    act(() => {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: { type: "marcus:save", molfile: "M", smiles: "C" },
          origin: "https://evil.example",
          source: frame().contentWindow,
        }),
      );
    });
    fromKetcher({ type: "marcus:save", molfile: "M", smiles: "C" }, window);
    expect(onSave).not.toHaveBeenCalled();
  });

  it("the SMILES field sends molfile: null", async () => {
    const { onSave, onClose } = renderEditor();
    fireEvent.change(screen.getByLabelText("SMILES"), {
      target: { value: " CCN " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save SMILES" }));
    expect(onSave).toHaveBeenCalledWith({ smiles: "CCN", molfile: null });
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it("an unchanged SMILES cannot be saved: the button is off and Enter does nothing", () => {
    const { onSave } = renderEditor(); // starts with c1ccccc1 and a stored molfile
    const field = screen.getByLabelText("SMILES");
    const button = screen.getByRole("button", { name: "Save SMILES" });
    expect(field).toHaveFocus();
    expect(button).toBeDisabled();
    fireEvent.submit(field.closest("form") as HTMLFormElement); // Enter in the field
    expect(onSave).not.toHaveBeenCalled();

    fireEvent.change(field, { target: { value: "  c1ccccc1 " } }); // only spaces differ
    expect(button).toBeDisabled();
    fireEvent.submit(field.closest("form") as HTMLFormElement);
    expect(onSave).not.toHaveBeenCalled();

    fireEvent.change(field, { target: { value: "c1ccccc1C" } });
    expect(button).toBeEnabled();
    fireEvent.change(field, { target: { value: "c1ccccc1" } }); // back to the start
    expect(button).toBeDisabled();
  });

  it("an empty SMILES field cannot be saved", () => {
    renderEditor({ initial: { smiles: null, molfile: null } });
    expect(screen.getByLabelText("SMILES")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Save SMILES" })).toBeDisabled();
  });

  it("an empty drawing is not saved", () => {
    const { onSave, onClose } = renderEditor();
    fromKetcher({ type: "marcus:save", molfile: "", smiles: "  " });
    expect(onSave).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Draw a structure first.");
  });

  it("a rejected onSave keeps the dialog open and shows the API detail", async () => {
    const { onClose } = renderEditor({
      onSave: async () => {
        throw new ApiError(422, "SMILES could not be parsed");
      },
    });
    fireEvent.change(screen.getByLabelText("SMILES"), { target: { value: "C1CC" } });
    fireEvent.click(screen.getByRole("button", { name: "Save SMILES" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Save failed: SMILES could not be parsed",
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    // the field is usable again for the next try
    expect(screen.getByRole("button", { name: "Save SMILES" })).toBeEnabled();
  });

  it("a failure that is not an ApiError shows a fixed text", async () => {
    renderEditor({
      onSave: async () => {
        throw new TypeError("Failed to fetch");
      },
    });
    fromKetcher({ type: "marcus:save", molfile: "M", smiles: "C" });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Save failed: Something went wrong.",
    );
  });

  it("does not start a second save while one is running", async () => {
    let finish: () => void = () => {};
    const { onSave } = renderEditor({
      onSave: () => new Promise<void>((resolve) => (finish = resolve)),
    });
    fireEvent.change(screen.getByLabelText("SMILES"), { target: { value: "CC" } });
    expect(screen.getByRole("button", { name: "Save SMILES" })).toBeEnabled();
    fromKetcher({ type: "marcus:save", molfile: "M", smiles: "C" });
    fromKetcher({ type: "marcus:save", molfile: "M", smiles: "C" });
    expect(screen.getByRole("button", { name: "Save SMILES" })).toBeDisabled();
    expect(onSave).toHaveBeenCalledTimes(1);
    await act(async () => finish());
  });

  it("closes on marcus:cancel from the frame, on Close, and on Escape", () => {
    const a = renderEditor();
    fromKetcher({ type: "marcus:cancel" });
    expect(a.onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(a.onClose).toHaveBeenCalledTimes(2);

    fireEvent.keyDown(screen.getByLabelText("SMILES"), { key: "Escape" });
    expect(a.onClose).toHaveBeenCalledTimes(3);
  });

  it("stops listening once unmounted", () => {
    const { onSave, unmount } = renderEditor();
    const source = frame().contentWindow;
    unmount();
    fromKetcher({ type: "marcus:save", molfile: "M", smiles: "C" }, source);
    expect(onSave).not.toHaveBeenCalled();
  });
});

describe("segment caller (useSaveCuration + editorChange)", () => {
  it("save in the editor keeps the note", async () => {
    const { put } = renderSegment({
      status: "accepted",
      smiles: "C",
      molfile: null,
      note: "n",
    });
    fromKetcher({ type: "marcus:save", molfile: "M", smiles: "CCO" });
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put).toHaveBeenCalledWith("s1", {
      status: "accepted",
      smiles: "CCO",
      molfile: "M",
      note: "n",
    });
  });

  it("an unchecked structure becomes accepted on save", async () => {
    const { put } = renderSegment({
      status: "unchecked",
      smiles: "C",
      molfile: null,
      note: null,
    });
    fromKetcher({ type: "marcus:save", molfile: "M", smiles: "CCO" });
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put).toHaveBeenCalledWith("s1", {
      status: "accepted",
      smiles: "CCO",
      molfile: "M",
      note: null,
    });
  });

  it("a rejected structure stays rejected; the SMILES field clears the stored molfile", async () => {
    const { put, client } = renderSegment({
      status: "rejected",
      smiles: "C",
      molfile: "OLD",
      note: "why",
    });
    fireEvent.change(screen.getByLabelText("SMILES"), {
      target: { value: "CCN" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save SMILES" }));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put).toHaveBeenCalledWith("s1", {
      status: "rejected",
      smiles: "CCN",
      molfile: null,
      note: "why",
    });
    await waitFor(() =>
      expect(client.getQueryData<PaperDetail>(keys.paper("p1"))?.segments[0]?.curation).toEqual({
        status: "rejected",
        smiles: "CCN",
        molfile: null,
        note: "why",
      }),
    );
  });

  it("a 422 from the API keeps the dialog open with its detail", async () => {
    const { put, onClose } = renderSegment({
      status: "accepted",
      smiles: "C",
      molfile: null,
      note: "n",
    });
    put.mockRejectedValue(new ApiError(422, "molfile could not be parsed"));
    fromKetcher({ type: "marcus:save", molfile: "BAD", smiles: "C" });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Save failed: molfile could not be parsed",
    );
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("editorChange", () => {
  it("accepts an unchecked or missing curation, keeps any other status, sets the structure", () => {
    const s = { smiles: "CCO", molfile: "M" };
    expect(editorChange(null, s)).toEqual({ status: "accepted", structure: s });
    const base = { smiles: null, molfile: null, note: "n" };
    expect(editorChange({ ...base, status: "unchecked" }, s)).toEqual({
      status: "accepted",
      structure: s,
    });
    expect(editorChange({ ...base, status: "rejected" }, s)).toEqual({
      status: "rejected",
      structure: s,
    });
    // no note key: curationBody keeps the stored note
    expect("note" in editorChange({ ...base, status: "accepted" }, s)).toBe(false);
  });
});
