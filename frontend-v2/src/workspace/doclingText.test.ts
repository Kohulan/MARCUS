import { describe, expect, it } from "vitest";
import type { DoclingDoc } from "../api/types";
import { doclingBlocks } from "./doclingText";

const text = (i: number, label: string, value: string) => ({
  self_ref: `#/texts/${i}`,
  label,
  text: value,
});

describe("doclingBlocks", () => {
  it("keeps body order through a group and maps section_header to a heading", () => {
    const doc: DoclingDoc = {
      body: {
        children: [
          { $ref: "#/texts/3" },
          { $ref: "#/groups/0" },
          { $ref: "#/tables/0" },
          { $ref: "#/texts/0" },
          { $ref: "#/pictures/0" },
        ],
      },
      texts: [
        text(0, "text", "Last paragraph."),
        text(1, "list_item", "First item."),
        text(2, "list_item", "Second item."),
        text(3, "section_header", "Results"),
      ],
      groups: [{ self_ref: "#/groups/0", children: [{ $ref: "#/texts/1" }, { $ref: "#/texts/2" }] }],
    };
    expect(doclingBlocks(doc)).toEqual([
      { kind: "heading", text: "Results" },
      { kind: "paragraph", text: "First item." },
      { kind: "paragraph", text: "Second item." },
      { kind: "paragraph", text: "Last paragraph." },
    ]);
  });

  it("maps title to a heading and every other text label to a paragraph", () => {
    const doc: DoclingDoc = {
      body: { children: [{ $ref: "#/texts/0" }, { $ref: "#/texts/1" }, { $ref: "#/texts/2" }] },
      texts: [text(0, "title", "Alkaloids"), text(1, "caption", "Figure 1."), text(2, "footnote", "a")],
    };
    expect(doclingBlocks(doc).map((b) => b.kind)).toEqual(["heading", "paragraph", "paragraph"]);
  });

  it("uses texts in array order without a body", () => {
    const doc: DoclingDoc = {
      texts: [text(0, "section_header", "Intro"), text(1, "text", "Body.")],
    };
    expect(doclingBlocks(doc)).toEqual([
      { kind: "heading", text: "Intro" },
      { kind: "paragraph", text: "Body." },
    ]);
  });

  it("skips refs that point nowhere, blank text and a group that contains itself", () => {
    const doc: DoclingDoc = {
      body: {
        children: [
          { $ref: "#/texts/9" },
          { $ref: "#/groups/0" },
          { $ref: "#/texts/1" },
          { $ref: "nonsense" },
        ],
      },
      texts: [text(0, "text", "Kept."), text(1, "text", "   ")],
      groups: [{ self_ref: "#/groups/0", children: [{ $ref: "#/groups/0" }, { $ref: "#/texts/0" }] }],
    };
    expect(doclingBlocks(doc)).toEqual([{ kind: "paragraph", text: "Kept." }]);
  });

  it("returns plain strings: markup in the text stays text", () => {
    const hostile = "<img src=x onerror=window.__xss=1>";
    const doc: DoclingDoc = { texts: [text(0, "text", hostile)] };
    expect(doclingBlocks(doc)).toEqual([{ kind: "paragraph", text: hostile }]);
  });
});
