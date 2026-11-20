// How far a paper's read has come: its stages in plain words and one overall figure, for the
// status bar's progress bar and the tool home's rows. Pages are 0-based here, as in the API.
import { isPaperBusy, isStepActive } from "../api/status";
import type { StepOut } from "../api/types";
import { onlyAnnotating } from "./annotation";
import { checkFailure, pageSteps } from "./pageFailures";

export type Stage =
  | "waiting"
  | "checking"
  | "pages"
  | "structures"
  | "finishing"
  | "annotating"
  | "done";

export type StageMark = {
  key: "check" | "pages" | "structures" | "end";
  label: string;
  /** "3/5" while the stage is counted, null otherwise. */
  count: string | null;
  state: "done" | "current" | "next";
};

export type ReadingProgress = {
  stage: Stage;
  /** 0 to 1; null when there is nothing to measure yet (the bar is indeterminate). */
  fraction: number | null;
  /** Pages handled (read, or failed for good) of the paper's pages; null until counted. */
  pages: { done: number; total: number } | null;
  /** Structures handled of those found so far; null for a paper read without structures. */
  structures: { done: number; total: number } | null;
  /** Some reading step has run (the queue estimate is only shown before that). */
  started: boolean;
  /** The bar's spoken value: "Reading structures, 10 of 15". */
  valueText: string;
  stages: StageMark[];
};

type PaperLike = {
  status: string;
  pages: number | null;
  ocsr_mode: string;
  annotating?: boolean | undefined;
};

// The weights of the parts of a read. Pages and structures run side by side; the structures
// part is measured against the structures the unread pages can be expected to hold, so a
// page that brings new structures does not pull the figure back.
const CHECK = 0.05;
const PAGES = 0.45;
const STRUCTURES = 0.45;

const ENDED = new Set(["done", "failed", "cancelled"]);

/**
 * Pages whose newest page step has ended. A done render_page is the newest only when the
 * segmentation cache gave the page its segments: otherwise its segment_page step is created in
 * the same transaction that finishes the render (backend pipeline.py), so it is already newer.
 */
function pagesHandled(steps: StepOut[], total: number): number {
  let n = 0;
  for (const [page0, list] of pageSteps(steps)) {
    if (page0 < total && ENDED.has(list[0]!.status)) n += 1;
  }
  return n;
}

/** A structure is handled once read (another engine reading it again keeps it read), or failed with nothing running. */
function structuresHandled(steps: StepOut[]): { done: number; total: number } {
  const read = new Set<string>();
  const active = new Set<string>();
  const all = new Set<string>();
  for (const s of steps) {
    if (s.kind !== "ocsr" || s.segment_id === null) continue;
    all.add(s.segment_id);
    if (s.status === "done") read.add(s.segment_id);
    else if (isStepActive(s.status)) active.add(s.segment_id);
  }
  let done = 0;
  for (const id of all) if (read.has(id) || !active.has(id)) done += 1;
  return { done, total: all.size };
}

const LABEL: Record<StageMark["key"], string> = {
  check: "Checking PDF",
  pages: "Reading pages",
  structures: "Reading structures",
  end: "Finishing",
};

const ORDER: Record<Stage, number> = {
  waiting: -1,
  checking: 0,
  pages: 1,
  structures: 2,
  finishing: 3,
  annotating: 3,
  done: 4,
};

function marks(
  stage: Stage,
  pages: ReadingProgress["pages"],
  structures: ReadingProgress["structures"],
  withStructures: boolean,
): StageMark[] {
  const keys: StageMark["key"][] = withStructures
    ? ["check", "pages", "structures", "end"]
    : ["check", "pages", "end"];
  const at = ORDER[stage];
  return keys.map((key) => {
    const i = key === "check" ? 0 : key === "pages" ? 1 : key === "structures" ? 2 : 3;
    const state = i < at ? "done" : i === at ? "current" : "next";
    let count: string | null = null;
    if (state === "current" && key === "pages" && pages) count = `${pages.done}/${pages.total}`;
    if (state === "current" && key === "structures" && structures) {
      count = `${structures.done}/${structures.total}`;
    }
    const label = key === "end" && stage === "done" ? "Done" : LABEL[key];
    return { key, label, count, state };
  });
}

/**
 * The read's stage and overall figure, or null when there is no read to show (a failed paper,
 * a PDF that could not be read: the status bar says why as before).
 */
export function readingProgress(paper: PaperLike, steps: StepOut[]): ReadingProgress | null {
  if (paper.status === "failed" || checkFailure(steps) !== null) return null;
  const withStructures = paper.ocsr_mode !== "off";
  const started = steps.some(
    (s) => s.kind !== "annotate" && (s.status === "running" || ENDED.has(s.status)),
  );
  const total = paper.pages;
  const pages = total === null ? null : { done: pagesHandled(steps, total), total };
  const found = structuresHandled(steps);
  const structures = withStructures ? found : null;

  const make = (stage: Stage, fraction: number | null, valueText: string): ReadingProgress => ({
    stage,
    fraction,
    pages,
    structures,
    started,
    valueText,
    stages: marks(stage, pages, structures, withStructures),
  });

  if (paper.status === "done") return make("done", 1, "Done");
  if (!isPaperBusy(paper.status)) return null;
  if (paper.annotating || onlyAnnotating(steps)) return make("annotating", null, "Annotating");
  if (pages === null) {
    const check = steps.some(
      (s) => s.kind === "check_pdf" && (s.status === "running" || ENDED.has(s.status)),
    );
    return check ? make("checking", null, "Checking PDF") : make("waiting", null, "Waiting");
  }

  const pageFrac = pages.total > 0 ? pages.done / pages.total : 1;
  let fraction = CHECK;
  let structFrac = 0;
  if (structures === null) {
    fraction += (PAGES + STRUCTURES) * pageFrac;
  } else {
    if (structures.total > 0) structFrac = (structures.done / structures.total) * pageFrac;
    else if (pageFrac === 1) structFrac = 1;
    fraction += PAGES * pageFrac + STRUCTURES * structFrac;
  }

  if (pages.done < pages.total) {
    return make("pages", fraction, `Reading pages, ${pages.done} of ${pages.total}`);
  }
  if (structures !== null && structures.done < structures.total) {
    return make(
      "structures",
      fraction,
      `Reading structures, ${structures.done} of ${structures.total}`,
    );
  }
  return make("finishing", fraction, "Finishing");
}

/** The figure shown so far in this run, and whether the paper was busy at the last look. */
export type Climb = { max: number; busy: boolean };

/**
 * The bar never moves back while a paper is read: the shown figure is the highest so far in
 * this run (a retried page is busy again and starts a new run). The same state back when
 * nothing changed.
 */
export function climb(prev: Climb, fraction: number | null, busy: boolean): Climb {
  if (busy && !prev.busy) return { max: fraction ?? 0, busy };
  const max = fraction !== null && fraction > prev.max ? fraction : prev.max;
  if (max === prev.max && busy === prev.busy) return prev;
  return { max, busy };
}
