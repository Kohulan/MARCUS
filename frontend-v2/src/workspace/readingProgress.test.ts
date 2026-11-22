// readingProgress: the stages and the overall figure of a paper being read.
import { describe, expect, it } from "vitest";
import type { StepOut } from "../api/types";
import { progressOf, readingProgress } from "./readingProgress";

let seq = 0;
function step(over: Partial<StepOut>): StepOut {
  seq += 1;
  return {
    id: `s${seq}`,
    kind: "segment_page",
    page: 0,
    segment_id: null,
    status: "done",
    attempts: 1,
    error_class: null,
    engine: null,
    created_at: `2026-11-18T10:${String(Math.floor(seq / 60)).padStart(2, "0")}:${String(seq % 60).padStart(2, "0")}.000000Z`,
    started_at: null,
    finished_at: null,
    ...over,
  };
}

const busy = (pages: number | null, over: Partial<{ ocsr_mode: string }> = {}) => ({
  status: "processing",
  pages,
  ocsr_mode: "auto",
  ...over,
});
const checkDone = () => step({ kind: "check_pdf", page: null });
/** Page p read (render and segment done). */
const pageRead = (p: number) => [step({ kind: "render_page", page: p }), step({ kind: "segment_page", page: p })];
const ocsr = (seg: string, status = "done") => step({ kind: "ocsr", page: 0, segment_id: seg, status });

describe("readingProgress", () => {
  it("waits with no figure before any work starts", () => {
    const r = readingProgress({ status: "checking", pages: null, ocsr_mode: "auto" }, [
      step({ kind: "check_pdf", page: null, status: "queued" }),
    ]);
    expect(r).toMatchObject({ stage: "waiting", fraction: null, valueText: "Waiting" });
  });

  it("checks the PDF with no figure while the pages are not known", () => {
    const r = readingProgress({ status: "checking", pages: null, ocsr_mode: "auto" }, [
      step({ kind: "check_pdf", page: null, status: "running" }),
    ]);
    expect(r).toMatchObject({ stage: "checking", fraction: null, valueText: "Checking PDF" });
    expect(r!.stages.map((s) => [s.label, s.state])).toEqual([
      ["Checking PDF", "current"],
      ["Reading pages", "next"],
      ["Reading structures", "next"],
      ["Reading the text", "next"],
      ["Finishing", "next"],
    ]);
  });

  it("a done check whose page count has not arrived is still checking, not a guess", () => {
    const r = readingProgress(busy(null), [checkDone()]);
    expect(r).toMatchObject({ stage: "checking", fraction: null });
  });

  it("reads pages: counts pages whose newest step ended, names the stage and its count", () => {
    const steps = [
      checkDone(),
      ...pageRead(0),
      ...pageRead(1),
      ...pageRead(2),
      step({ kind: "render_page", page: 3, status: "running" }),
    ];
    const r = readingProgress(busy(5), steps)!;
    expect(r.stage).toBe("pages");
    expect(r.pages).toEqual({ done: 3, total: 5 });
    expect(r.valueText).toBe("Reading pages, 3 of 5");
    expect(r.stages.map((s) => [s.label, s.count, s.state])).toEqual([
      ["Checking PDF", null, "done"],
      ["Reading pages", "3/5", "current"],
      ["Reading structures", null, "next"],
      ["Reading the text", null, "next"],
      ["Finishing", null, "next"],
    ]);
    expect(r.fraction).toBeGreaterThan(0);
    expect(r.fraction).toBeLessThan(0.5);
  });

  it("reads structures once every page is read", () => {
    const steps = [
      checkDone(),
      step({ kind: "docling", page: null, status: "running" }),
      ...[0, 1, 2, 3, 4].flatMap(pageRead),
    ];
    for (let i = 0; i < 15; i += 1) steps.push(ocsr(`g${i}`, i < 10 ? "done" : "running"));
    const r = readingProgress(busy(5), steps)!;
    expect(r.stage).toBe("structures");
    expect(r.structures).toEqual({ done: 10, total: 15 });
    expect(r.valueText).toBe("Reading structures, 10 of 15");
    expect(r.stages.map((s) => s.state)).toEqual(["done", "done", "current", "next", "next"]);
    expect(r.stages[2]!.count).toBe("10/15");
  });

  it("the overall figure never falls while structures are found as pages are read", () => {
    // Each page read finds two structures; a structure is read soon after its page; the text
    // ends last. A step's status changes in place, as on the server.
    const text = step({ kind: "docling", page: null, status: "running" });
    const steps: StepOut[] = [checkDone(), text];
    let last = 0;
    const look = () => {
      const f = readingProgress(busy(5), steps)!.fraction!;
      expect(f).toBeGreaterThanOrEqual(last);
      last = f;
    };
    look();
    for (let p = 0; p < 5; p += 1) {
      steps.push(...pageRead(p));
      const a = ocsr(`a${p}`, "queued");
      const b = ocsr(`b${p}`, "queued");
      steps.push(a, b);
      look();
      a.status = "done";
      look();
      b.status = "done";
      look();
    }
    text.status = "done";
    look();
    expect(last).toBeLessThan(1);
  });

  it("failed pages and failed structures count as handled, so the bar can end", () => {
    const steps = [
      checkDone(),
      ...pageRead(0),
      step({ kind: "render_page", page: 1, status: "failed", error_class: "timeout" }),
      ocsr("g1", "failed"),
      ocsr("g2"),
    ];
    const r = readingProgress(busy(2), steps)!;
    expect(r.pages).toEqual({ done: 2, total: 2 });
    expect(r.structures).toEqual({ done: 2, total: 2 });
    expect(r.stage).toBe("finishing");
    expect(r.valueText).toBe("Finishing");
  });

  it("a page served from the segmentation cache (render_page done, no segment_page) is read", () => {
    const steps = [checkDone(), step({ kind: "render_page", page: 0 }), step({ kind: "render_page", page: 1 })];
    expect(readingProgress(busy(3), steps)!.pages).toEqual({ done: 2, total: 3 });
  });

  it("a page whose segmentation follows its render is not read yet", () => {
    const steps = [checkDone(), step({ kind: "render_page", page: 0 }), step({ kind: "segment_page", page: 0, status: "queued" })];
    expect(readingProgress(busy(1), steps)!.pages).toEqual({ done: 0, total: 1 });
  });

  it("a page being retried is not handled", () => {
    const steps = [
      checkDone(),
      step({ kind: "render_page", page: 0, status: "failed" }),
      step({ kind: "render_page", page: 0, status: "running" }),
    ];
    expect(readingProgress(busy(1), steps)!.pages).toEqual({ done: 0, total: 1 });
  });

  it("a structure read once stays read while another engine reads it again", () => {
    const steps = [
      checkDone(),
      ...pageRead(0),
      step({ kind: "render_page", page: 1, status: "running" }),
      ocsr("g1"),
      ocsr("g1", "running"),
    ];
    expect(readingProgress(busy(2), steps)!.structures).toEqual({ done: 1, total: 1 });
  });

  it("reads the text once pages and structures are handled, with its own share of the bar", () => {
    const docling = (status: string) => step({ kind: "docling", page: null, status });
    const steps = [checkDone(), docling("running"), ...pageRead(0), ocsr("g1")];
    const r = readingProgress(busy(1), steps)!;
    expect(r).toMatchObject({ stage: "text", valueText: "Reading the text" });
    expect(r.fraction).toBeCloseTo(0.75, 5);
    expect(r.stages.map((s) => [s.label, s.state])).toEqual([
      ["Checking PDF", "done"],
      ["Reading pages", "done"],
      ["Reading structures", "done"],
      ["Reading the text", "current"],
      ["Finishing", "next"],
    ]);
    const done = readingProgress(busy(1), [checkDone(), docling("done"), ...pageRead(0), ocsr("g1")])!;
    expect(done.stage).toBe("finishing");
    expect(done.fraction).toBeCloseTo(0.95, 5);
  });

  it("the text read before the pages is ticked at once and counted", () => {
    const steps = [
      checkDone(),
      step({ kind: "docling", page: null, status: "done" }),
      ...pageRead(0),
      step({ kind: "render_page", page: 1, status: "running" }),
    ];
    const r = readingProgress(busy(2), steps)!;
    expect(r.stage).toBe("pages");
    expect(r.stages.find((s) => s.key === "text")!.state).toBe("done");
    expect(r.fraction).toBeCloseTo(0.05 + 0.2 + 0.35 * 0.5, 5);
  });

  it("a paper read without structures (ocsr off) has no structures stage", () => {
    const steps = [checkDone(), step({ kind: "docling", page: null, status: "running" }), ...pageRead(0)];
    const r = readingProgress(busy(2, { ocsr_mode: "off" }), steps)!;
    expect(r.structures).toBeNull();
    expect(r.stages.map((s) => s.label)).toEqual([
      "Checking PDF",
      "Reading pages",
      "Reading the text",
      "Finishing",
    ]);
    expect(r.fraction).toBeCloseTo(0.05 + 0.7 * 0.5, 5);
  });

  it("pages read with no structure found yet: the structures part waits for the pages", () => {
    const steps = [checkDone(), step({ kind: "docling", page: null, status: "queued" }), ...pageRead(0), ...pageRead(1)];
    const r = readingProgress(busy(4), steps)!;
    expect(r.stage).toBe("pages");
    expect(r.fraction).toBeCloseTo(0.05 + 0.35 * 0.5, 5);
  });

  it("no bar while the only work is reading read structures again (another engine on a done paper)", () => {
    const steps = [checkDone(), ...pageRead(0), ocsr("g1"), ocsr("g1", "running")];
    expect(readingProgress(busy(1), steps)).toBeNull();
    // a structure read for the first time is a read
    expect(readingProgress(busy(1), [checkDone(), ...pageRead(0), ocsr("g1", "running")])!.stage).toBe(
      "structures",
    );
  });

  it("is done and full for a done paper", () => {
    const r = readingProgress({ status: "done", pages: 2, ocsr_mode: "auto" }, [checkDone(), ...pageRead(0), ...pageRead(1)])!;
    expect(r).toMatchObject({ stage: "done", fraction: 1, valueText: "Done" });
    expect(r.stages.map((s) => [s.label, s.state])).toEqual([
      ["Checking PDF", "done"],
      ["Reading pages", "done"],
      ["Reading structures", "done"],
      ["Reading the text", "done"],
      ["Done", "done"],
    ]);
  });

  it("shows nothing for a failed paper or a PDF that could not be read", () => {
    expect(readingProgress({ status: "failed", pages: null, ocsr_mode: "auto" }, [])).toBeNull();
    const bad = [step({ kind: "check_pdf", page: null, status: "failed", error_class: "bad_input" })];
    expect(readingProgress({ status: "checking", pages: null, ocsr_mode: "auto" }, bad)).toBeNull();
  });

  it("reads the papers list's counts as the steps (the tool home's rows poll no steps)", () => {
    const counts = {
      pages_read: 2,
      structures_total: 3,
      structures_read: 1,
      text_read: false,
      check_started: true,
      rereading: false,
    };
    const row = progressOf({ status: "processing", pages: 4, ocsr_mode: "auto", ...counts })!;
    expect(row).toMatchObject({
      stage: "pages",
      valueText: "Reading pages, 2 of 4",
      line: "Reading pages 2/4",
      said: "Reading pages",
    });
    const steps = [checkDone(), ...pageRead(0), ...pageRead(1), ocsr("g1"), ocsr("g2", "running"), ocsr("g3", "queued")];
    expect(readingProgress(busy(4), steps)).toEqual(row);
    expect(progressOf({ status: "processing", pages: 4, ocsr_mode: "auto", ...counts, rereading: true })).toBeNull();
  });
});
