// pageFailures: the client copy of the server's failed_pages rule (F0-1, R-F10): per page,
// the newest render_page or segment_page step decides.
import { describe, expect, it } from "vitest";
import type { StepOut } from "../api/types";
import { checkFailure, pageFailures, progress } from "./pageFailures";

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
    created_at: `2026-11-18T10:00:${String(seq).padStart(2, "0")}.000000Z`,
    started_at: null,
    finished_at: null,
    ...over,
  };
}

describe("pageFailures", () => {
  it("lists a page whose newest step failed, with its error class (page stays 0-based)", () => {
    const steps = [
      step({ kind: "render_page", page: 4 }),
      step({ kind: "segment_page", page: 4, status: "failed", error_class: "timeout" }),
      step({ kind: "render_page", page: 1 }),
      step({ kind: "segment_page", page: 1 }),
    ];
    expect(pageFailures(steps)).toEqual([{ page0: 4, errorClass: "timeout", retrying: false }]);
  });

  it("a page failed, then retried and done, is not listed", () => {
    const steps = [
      step({ kind: "segment_page", page: 2, status: "failed", error_class: "worker_lost" }),
      step({ kind: "render_page", page: 2, status: "done" }),
    ];
    expect(pageFailures(steps)).toEqual([]);
  });

  it("a page failed with a newer step still running is retrying", () => {
    const steps = [
      step({ kind: "render_page", page: 3, status: "failed", error_class: "bad_input" }),
      step({ kind: "render_page", page: 3, status: "running" }),
    ];
    expect(pageFailures(steps)).toEqual([{ page0: 3, errorClass: "bad_input", retrying: true }]);
  });

  it("a page still being read for the first time is not listed", () => {
    const steps = [
      step({ kind: "render_page", page: 0, status: "done" }),
      step({ kind: "segment_page", page: 0, status: "running" }),
    ];
    expect(pageFailures(steps)).toEqual([]);
  });

  it("orders by created_at, not by list order, and sorts pages", () => {
    const failed = step({
      kind: "segment_page",
      page: 6,
      status: "failed",
      error_class: "engine_error",
      created_at: "2026-11-18T11:00:00.000000Z",
    });
    const older = step({ kind: "render_page", page: 6, created_at: "2026-11-18T09:00:00.000000Z" });
    const other = step({ kind: "render_page", page: 2, status: "failed", error_class: null });
    expect(pageFailures([failed, older, other])).toEqual([
      { page0: 2, errorClass: null, retrying: false },
      { page0: 6, errorClass: "engine_error", retrying: false },
    ]);
  });

  it("at the same created_at, segment_page counts as newer than render_page (server order)", () => {
    const at = "2026-11-18T12:00:00.000000Z";
    const steps = [
      step({ kind: "segment_page", page: 1, status: "failed", error_class: "timeout", created_at: at }),
      step({ kind: "render_page", page: 1, status: "done", created_at: at }),
    ];
    expect(pageFailures(steps)).toEqual([{ page0: 1, errorClass: "timeout", retrying: false }]);
  });

  it("ignores ocsr and check_pdf steps", () => {
    const steps = [
      step({ kind: "check_pdf", page: null, status: "failed", error_class: "bad_input" }),
      step({ kind: "ocsr", page: 0, status: "failed", error_class: "timeout", segment_id: "g1" }),
    ];
    expect(pageFailures(steps)).toEqual([]);
  });
});

describe("checkFailure", () => {
  it("is null without a failed check_pdf step", () => {
    expect(checkFailure([step({ kind: "check_pdf", page: null, status: "done" })])).toBeNull();
  });

  it("bad_input names what is wrong with the PDF", () => {
    const steps = [step({ kind: "check_pdf", page: null, status: "failed", error_class: "bad_input" })];
    expect(checkFailure(steps)).toBe("it is encrypted, damaged or has more than 100 pages");
  });

  it("other classes use the common reasons", () => {
    const steps = [step({ kind: "check_pdf", page: null, status: "failed", error_class: "timeout" })];
    expect(checkFailure(steps)).toBe("it took too long");
    const unknown = [step({ kind: "check_pdf", page: null, status: "failed", error_class: "x" })];
    expect(checkFailure(unknown)).toBe("an unknown error");
  });
});

describe("progress", () => {
  it("counts pages whose newest page step is done, and read structures", () => {
    const steps = [
      step({ kind: "render_page", page: 0 }),
      step({ kind: "segment_page", page: 0 }),
      step({ kind: "render_page", page: 1 }),
      step({ kind: "segment_page", page: 1, status: "running" }),
      step({ kind: "render_page", page: 2, status: "running" }),
      step({ kind: "ocsr", page: 0, segment_id: "g1", status: "done" }),
      step({ kind: "ocsr", page: 0, segment_id: "g2", status: "running" }),
      step({ kind: "ocsr", page: 0, segment_id: "g1", status: "running" }), // another engine
    ];
    expect(progress(steps, 3)).toEqual({ pagesRead: 1, pages: 3, structuresRead: 1, structures: 2 });
  });

  it("a page served from the segmentation cache (render_page done, no segment_page) is read", () => {
    const steps = [step({ kind: "render_page", page: 0 }), step({ kind: "render_page", page: 1 })];
    expect(progress(steps, 2).pagesRead).toBe(2);
  });

  it("has no structure part without ocsr steps", () => {
    expect(progress([step({ kind: "segment_page", page: 0 })], 1)).toEqual({
      pagesRead: 1,
      pages: 1,
      structuresRead: 0,
      structures: 0,
    });
  });
});
