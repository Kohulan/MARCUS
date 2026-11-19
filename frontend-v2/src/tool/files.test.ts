// The landing-to-tool hand-off: one file in memory, taken once, by its token only.
import { describe, expect, it } from "vitest";
import { dropHandOff, handOff, takeHandOff } from "./files";

const pdf = (name: string) => new File(["%PDF"], name, { type: "application/pdf" });

describe("handOff / takeHandOff", () => {
  it("gives the file once, to its token only", () => {
    const file = pdf("a.pdf");
    const token = handOff(file);
    expect(takeHandOff("not-it")).toBeNull();
    expect(takeHandOff(token)).toBe(file);
    expect(takeHandOff(token)).toBeNull(); // consumed
  });

  it("a newer hand-off replaces an older one; the old token finds nothing", () => {
    const old = handOff(pdf("old.pdf"));
    const fresh = pdf("new.pdf");
    const token = handOff(fresh);
    expect(token).not.toBe(old);
    expect(takeHandOff(old)).toBeNull();
    expect(takeHandOff(token)).toBe(fresh);
  });

  it("anything that is not a live token is harmless", () => {
    for (const t of [undefined, null, 1, {}, ""]) expect(takeHandOff(t)).toBeNull();
  });

  it("dropHandOff forgets the file it names, and only that one", () => {
    const a = handOff(pdf("a.pdf"));
    dropHandOff("other");
    dropHandOff(a);
    expect(takeHandOff(a)).toBeNull();
  });
});
