import { describe, expect, it } from "vitest";
import { curationBody } from "./curation";
import type { CurationOut } from "./types";

const edited: CurationOut = {
  status: "unchecked",
  smiles: "CCO",
  molfile: "M  END",
  note: "from figure 2",
};

describe("curationBody", () => {
  it("a status change keeps smiles, molfile and note", () => {
    expect(curationBody(edited, { status: "accepted" })).toEqual({
      status: "accepted",
      smiles: "CCO",
      molfile: "M  END",
      note: "from figure 2",
    });
  });

  it("a structure change keeps note and status and sets smiles and molfile together", () => {
    const current: CurationOut = { ...edited, status: "accepted" };
    expect(curationBody(current, { structure: { smiles: "CCN", molfile: null } })).toEqual({
      status: "accepted",
      smiles: "CCN",
      molfile: null,
      note: "from figure 2",
    });
  });

  it("a note change keeps the rest; a null note clears it", () => {
    expect(curationBody(edited, { note: "x" })).toEqual({ ...edited, note: "x" });
    expect(curationBody(edited, { note: null })).toEqual({ ...edited, note: null });
  });

  it("current null → unchecked with nulls", () => {
    expect(curationBody(null, {})).toEqual({
      status: "unchecked",
      smiles: null,
      molfile: null,
      note: null,
    });
    expect(curationBody(null, { status: "rejected" })).toEqual({
      status: "rejected",
      smiles: null,
      molfile: null,
      note: null,
    });
  });

  it("always sends exactly the four keys", () => {
    const body = curationBody({ ...edited, extra: 1 } as CurationOut, { status: "accepted" });
    expect(Object.keys(body).sort()).toEqual(["molfile", "note", "smiles", "status"]);
  });
});
