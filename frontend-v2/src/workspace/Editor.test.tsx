// The structure editor dialog: the Ketcher frame is talked to only through the bridge, a
// save from the drawing or the SMILES field goes through the caller's onSave, and a
// segment caller (useSaveCuration + editorChange) never loses the note.
import { QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { backendFixture } from "../test/backendFixture";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { createQueryClient, keys, useSaveCuration } from "../api/queries";
import type { CurationOut, PaperDetail } from "../api/types";
import { paperLayout } from "../test/paperLayout";
import { editorStart } from "./SegmentEditor";
import Editor, {
  editorChange,
  editorLoad,
  hasImagePositions,
  type EditorStructure,
} from "./Editor";

// Real engine molfiles (as engines.test.ts): MolScribe on p2_6 keeps the image's positions,
// MolNexTR on p2_0 lays the structure out itself.
const engines = backendFixture<Record<string, Record<string, { smiles: string; molfile: string | null }>>>(
  "orient_engines.json",
);
const IMAGE_MOL = engines["p2_6"]!["molscribe"]!.molfile!;
const COMPUTED_MOL = engines["p2_0"]!["molnextr"]!.molfile!;

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

  it("closing with the opener gone puts focus on the focus-mode region (keys stay live)", () => {
    function Host() {
      const [open, setOpen] = useState(false);
      return (
        <section data-focus-home="" tabIndex={-1} aria-label="Focus [01]">
          {!open && (
            <button type="button" onClick={() => setOpen(true)}>
              Edit
            </button>
          )}
          {open && (
            <Editor
              initial={{ smiles: "C", molfile: null }}
              onSave={() => Promise.resolve()}
              onClose={() => setOpen(false)}
            />
          )}
        </section>
      );
    }
    render(<Host />);
    const opener = screen.getByRole("button", { name: "Edit" });
    opener.focus();
    fireEvent.click(opener);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.getByRole("region", { name: "Focus [01]" })).toHaveFocus();
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

  it("takes the focus back when Ketcher grabs it, but not after the curator tabbed in", () => {
    renderEditor();
    const field = screen.getByLabelText("SMILES");
    field.focus();
    // Ketcher focused itself while starting: the focus goes back to the field.
    frame().focus();
    expect(frame()).toHaveFocus();
    fromKetcher({ type: "marcus:unfocus" });
    expect(field).toHaveFocus();
    // From another window: ignored.
    frame().focus();
    fromKetcher({ type: "marcus:unfocus" }, window);
    expect(frame()).toHaveFocus();
    // The curator tabbed into the frame: it stays there.
    field.focus();
    fireEvent.keyDown(field, { key: "Tab" });
    frame().focus();
    fromKetcher({ type: "marcus:unfocus" });
    expect(frame()).toHaveFocus();
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
    // the field is usable again for the next try, and has the focus
    expect(screen.getByRole("button", { name: "Save SMILES" })).toBeEnabled();
    expect(screen.getByLabelText("SMILES")).toHaveFocus();
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

  it("Escape is handled in the dialog: it reaches the review keys already handled", () => {
    const { onClose } = renderEditor();
    const prevented: boolean[] = [];
    const seen = (e: KeyboardEvent) => prevented.push(e.defaultPrevented);
    document.addEventListener("keydown", seen);
    try {
      fireEvent.keyDown(screen.getByLabelText("SMILES"), { key: "Escape" });
      expect(prevented).toEqual([true]);
      expect(onClose).toHaveBeenCalledTimes(1);
    } finally {
      document.removeEventListener("keydown", seen);
    }
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
    }, false);
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
    }, true);
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
    // the status is kept, not decided: no decision (a main card's repeats keep theirs)
    expect(put).toHaveBeenCalledWith("s1", {
      status: "rejected",
      smiles: "CCN",
      molfile: null,
      note: "why",
    }, false);
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
    // a kept status is not in the change: an edit is no decision
    expect(editorChange({ ...base, status: "rejected" }, s)).toEqual({ structure: s });
    // no note key: curationBody keeps the stored note
    expect("note" in editorChange({ ...base, status: "accepted" }, s)).toBe(false);
  });
});

describe("source panel", () => {
  const source = {
    image: "/api/segments/s1/image",
    page: { url: "/api/papers/p1/pages/0/image", bbox: [0, 0, 10, 10] as [number, number, number, number], page0: 0 },
  };

  it("shows the crop beside the editor; Escape still closes from the page view", () => {
    const onClose = vi.fn();
    render(
      <Editor initial={{ smiles: "C", molfile: null }} source={source} onSave={async () => {}} onClose={onClose} />,
    );
    expect(screen.getByRole("img", { name: "Crop the engines read" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Find on paper" }));
    const back = screen.getByRole("button", { name: "Back" });
    expect(back).toHaveFocus();
    fireEvent.keyDown(back, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("without a source the dialog is as before: no image", () => {
    renderEditor();
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByRole("dialog")).not.toHaveClass("editor--split");
  });
});

describe("hasImagePositions / editorLoad", () => {
  it("only a molfile with the image's positions counts", () => {
    expect(hasImagePositions({ smiles: "CC", molfile: null })).toBe(false);
    expect(hasImagePositions({ smiles: "CC", molfile: "" })).toBe(false);
    expect(hasImagePositions({ smiles: "CC", molfile: COMPUTED_MOL })).toBe(false);
    expect(hasImagePositions({ smiles: "CC", molfile: IMAGE_MOL })).toBe(true);
  });

  it("a prediction of an engine without image positions (MolParser) never counts", () => {
    expect(hasImagePositions({ smiles: "CC", molfile: IMAGE_MOL, engine: "molparser" })).toBe(false);
    expect(hasImagePositions({ smiles: "CC", molfile: IMAGE_MOL, engine: "molscribe" })).toBe(true);
    expect(hasImagePositions({ smiles: "CC", molfile: IMAGE_MOL, engine: null })).toBe(true);
  });

  it("needs a SMILES too: off would otherwise open Ketcher empty", () => {
    expect(hasImagePositions({ smiles: null, molfile: IMAGE_MOL })).toBe(false);
    expect(hasImagePositions({ smiles: "  ", molfile: IMAGE_MOL })).toBe(false);
    const noSmiles = { smiles: null, molfile: IMAGE_MOL };
    expect(editorLoad(noSmiles, false)).toEqual(noSmiles);
  });

  it("on: the start as it is; off: the SMILES only, when the molfile has image positions", () => {
    const image = { smiles: "CC", molfile: IMAGE_MOL };
    const computed = { smiles: "CC", molfile: COMPUTED_MOL };
    const bare = { smiles: "CC", molfile: null };
    expect(editorLoad(image, true)).toEqual(image);
    expect(editorLoad(image, false)).toEqual({ smiles: "CC", molfile: null });
    expect(editorLoad(computed, true)).toEqual(computed);
    expect(editorLoad(computed, false)).toEqual(computed);
    expect(editorLoad(bare, false)).toEqual(bare);
  });
});

describe("the editor never starts from the paper layout", () => {
  it("an invalid MolScribe answer with a layout opens as its own molfile: no Use coordinates", () => {
    // The layout is a reading aid for the drawings (binding review finding): the editor's
    // start is the prediction's own SMILES and molfile, here a computed layout.
    const p = {
      id: "p1",
      engine: "molscribe",
      engine_version: "1",
      smiles: "CC",
      molfile: COMPUTED_MOL,
      valid: false,
      ms: 1,
      cached: false,
      created_at: "2026-11-26T00:00:00Z",
      layout: paperLayout(),
    };
    const segment = { id: "s1", page: 0, idx: 0, bbox: [0, 0, 1, 1], curation: null, predictions: [p] };
    const start = editorStart(segment as never, "molscribe");
    expect(JSON.stringify(start)).not.toContain("MARCUS layout");
    expect(hasImagePositions(start)).toBe(false);
    // even handed a layout as a molfile, the editor does not take it for image positions
    expect(hasImagePositions({ smiles: "CC", molfile: paperLayout(), engine: "molscribe" })).toBe(false);
  });
});

describe("Use coordinates", () => {
  function coordsButton() {
    return screen.getByRole("switch", { name: "Use coordinates" });
  }
  function spyFrame() {
    const post = vi.spyOn(frame().contentWindow as Window, "postMessage");
    post.mockImplementation(() => {});
    return post;
  }

  it("is on at opening; switching it loads the start again with or without the molfile", () => {
    renderEditor({ initial: { smiles: "CC", molfile: IMAGE_MOL } });
    expect(coordsButton()).toHaveAttribute("aria-checked", "true");
    expect(coordsButton()).toBeEnabled();
    const post = spyFrame();
    fromKetcher({ type: "marcus:ready" });
    expect(post).toHaveBeenLastCalledWith(
      { type: "marcus:load", molfile: IMAGE_MOL, smiles: "CC" },
      ORIGIN,
    );
    fireEvent.click(coordsButton());
    expect(coordsButton()).toHaveAttribute("aria-checked", "false");
    expect(post).toHaveBeenCalledTimes(2);
    expect(post).toHaveBeenLastCalledWith({ type: "marcus:load", molfile: null, smiles: "CC" }, ORIGIN);
    fireEvent.click(coordsButton());
    expect(post).toHaveBeenCalledTimes(3);
    expect(post).toHaveBeenLastCalledWith(
      { type: "marcus:load", molfile: IMAGE_MOL, smiles: "CC" },
      ORIGIN,
    );
  });

  it("is off and disabled without image positions; Ketcher gets the start as today", () => {
    renderEditor({ initial: { smiles: "CC", molfile: COMPUTED_MOL } });
    expect(coordsButton()).toBeDisabled();
    expect(coordsButton()).toHaveAttribute("aria-checked", "false");
    const post = spyFrame();
    fromKetcher({ type: "marcus:ready" });
    expect(post).toHaveBeenCalledWith(
      { type: "marcus:load", molfile: COMPUTED_MOL, smiles: "CC" },
      ORIGIN,
    );
  });

  it("is disabled while a save runs: a failed save keeps the drawing", async () => {
    let finish!: () => void;
    renderEditor({
      initial: { smiles: "CC", molfile: IMAGE_MOL },
      onSave: () => new Promise<void>((resolve) => (finish = resolve)),
    });
    fromKetcher({ type: "marcus:save", molfile: "M", smiles: "CCO" });
    expect(coordsButton()).toBeDisabled();
    await act(async () => finish());
  });

  it("switched off before Ketcher is ready: nothing is posted until marcus:ready, then no molfile", () => {
    renderEditor({ initial: { smiles: "CC", molfile: IMAGE_MOL } });
    const post = spyFrame();
    fireEvent.click(coordsButton());
    expect(post).not.toHaveBeenCalled();
    fromKetcher({ type: "marcus:ready" });
    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith({ type: "marcus:load", molfile: null, smiles: "CC" }, ORIGIN);
  });
});
