// How far a paper's read has come: its stages in plain words and one overall figure, for the
// status bar's progress bar and the tool home's rows. Pages are 0-based here, as in the API.
// The workspace reads the counts from the paper's steps (readCounts); the tool home gets the
// same counts with the papers list (PaperSummary), so its rows poll no steps.
import { isPaperBusy, isStepActive } from "../api/status";
import type { PaperSummary, StepOut } from "../api/types";
import { checkFailure, pageSteps } from "./pageFailures";

export type Stage =
  | "waiting"
  | "checking"
  | "pages"
  | "structures"
  | "text"
  | "finishing"
  | "done";

export type StageMark = {
  key: "check" | "pages" | "structures" | "text" | "end";
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
  /** The bar's spoken value: "Reading structures, 10 of 15". */
  valueText: string;
  /** The tool home row's line: "Reading pages 2/4", "Waiting"; "" when there is none. */
  line: string;
  /** Said once when the stage changes. */
  said: string;
  /** The stages, done ones ticked, the current one counted. */
  stages: StageMark[];
};

/** What a read is measured by: the papers list's fields, or readCounts from the steps. */
export type ReadCounts = Pick<
  PaperSummary,
  | "pages_read"
  | "structures_total"
  | "structures_read"
  | "text_read"
  | "check_started"
  | "rereading"
>;

type PaperLike = {
  status: string;
  pages: number | null;
  ocsr_mode: string;
};

// The weights of the parts of a read; the last 5% fills when the paper is done. Pages,
// structures and the text (docling, on the CPU at about 11 s a page) run side by side; the
// structures part is measured against the structures the unread pages can be expected to
// hold, so a page that brings new structures does not pull the figure back.
const CHECK = 0.05;
const PAGES = 0.35;
const STRUCTURES = 0.35;
const TEXT = 0.2;

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

/**
 * The text step (docling) has ended. A paper without one (read before the text step existed)
 * counts its text as read once its pages are.
 */
function textHandled(steps: StepOut[], pagesRead: boolean): boolean {
  const docling = steps.filter((s) => s.kind === "docling");
  if (docling.length === 0) return pagesRead;
  return docling.every((s) => ENDED.has(s.status));
}

/**
 * Busy only because structures already read are read again (another engine on a done paper):
 * no read to show. Like an annotate-only run, but without a bar at all.
 */
function onlyRereading(steps: StepOut[]): boolean {
  const read = new Set(
    steps.filter((s) => s.kind === "ocsr" && s.status === "done").map((s) => s.segment_id),
  );
  const active = steps.filter((s) => isStepActive(s.status));
  return (
    active.length > 0 &&
    active.every((s) => s.kind === "ocsr" && s.segment_id !== null && read.has(s.segment_id))
  );
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

/** The counts the papers list sends (backend api/read.py paper_counts), from the steps. */
export function readCounts(paper: PaperLike, steps: StepOut[]): ReadCounts {
  const pagesRead = paper.pages === null ? 0 : pagesHandled(steps, paper.pages);
  const structures = structuresHandled(steps);
  return {
    pages_read: pagesRead,
    structures_total: structures.total,
    structures_read: structures.done,
    text_read: textHandled(steps, paper.pages !== null && pagesRead >= paper.pages),
    check_started: steps.some(
      (s) => s.kind === "check_pdf" && (s.status === "running" || ENDED.has(s.status)),
    ),
    rereading: onlyRereading(steps),
  };
}

/** Each stage's words and place (a mark's state comes from it: before, at or after). */
const STAGES: Record<Stage, { label: string; order: number }> = {
  waiting: { label: "Waiting", order: -1 },
  checking: { label: "Checking PDF", order: 0 },
  pages: { label: "Reading pages", order: 1 },
  structures: { label: "Reading structures", order: 2 },
  text: { label: "Reading the text", order: 3 },
  finishing: { label: "Finishing", order: 4 },
  done: { label: "Done", order: 5 },
};

/** The marks of a read, each the stage it stands for. */
const MARKS: [StageMark["key"], Stage][] = [
  ["check", "checking"],
  ["pages", "pages"],
  ["structures", "structures"],
  ["text", "text"],
  ["end", "finishing"],
];

type Read = {
  pages: ReadingProgress["pages"];
  structures: ReadingProgress["structures"];
  textDone: boolean;
};

/** The model of one stage: its words (bar, row line, announcement) and its marks. */
function make(stage: Stage, fraction: number | null, read: Read): ReadingProgress {
  const { pages, structures, textDone } = read;
  const counted = stage === "pages" ? pages : stage === "structures" ? structures : null;
  const { label, order } = STAGES[stage];
  const count = counted ? `${counted.done}/${counted.total}` : null;
  const stages = MARKS.filter(([key]) => key !== "structures" || structures !== null).map(
    ([key, at]): StageMark => {
      const i = STAGES[at].order;
      let state: StageMark["state"] = i < order ? "done" : i === order ? "current" : "next";
      // The text is read beside the pages: ticked as soon as it is, whatever the stage.
      if (key === "text" && textDone && state === "next") state = "done";
      const mark = key === "end" && stage === "done" ? "done" : at;
      return { key, label: STAGES[mark].label, count: at === stage ? count : null, state };
    },
  );
  return {
    stage,
    fraction,
    pages,
    structures,
    valueText: counted ? `${label}, ${counted.done} of ${counted.total}` : label,
    line: stage === "done" ? "" : count ? `${label} ${count}` : label,
    said: label,
    stages,
  };
}

/**
 * The read's stage and overall figure from its counts (the papers list's fields, or
 * readCounts), or null when there is no read to show (a failed paper; busy only reading read
 * structures again).
 */
export function progressOf(paper: PaperLike & ReadCounts): ReadingProgress | null {
  if (paper.status === "failed") return null;
  const total = paper.pages;
  const pages = total === null ? null : { done: paper.pages_read, total };
  const structures =
    paper.ocsr_mode !== "off" ? { done: paper.structures_read, total: paper.structures_total } : null;
  const read: Read = { pages, structures, textDone: paper.text_read };

  if (paper.status === "done") return make("done", 1, read);
  if (!isPaperBusy(paper.status)) return null;
  if (paper.rereading) return null;
  if (pages === null) return make(paper.check_started ? "checking" : "waiting", null, read);

  const pageFrac = pages.total > 0 ? pages.done / pages.total : 1;
  let fraction = CHECK + (read.textDone ? TEXT : 0);
  let structFrac = 0;
  if (structures === null) {
    fraction += (PAGES + STRUCTURES) * pageFrac;
  } else {
    if (structures.total > 0) structFrac = (structures.done / structures.total) * pageFrac;
    else if (pageFrac === 1) structFrac = 1;
    fraction += PAGES * pageFrac + STRUCTURES * structFrac;
  }

  if (pages.done < pages.total) return make("pages", fraction, read);
  if (structures !== null && structures.done < structures.total) {
    return make("structures", fraction, read);
  }
  return make(read.textDone ? "finishing" : "text", fraction, read);
}

/**
 * The read's stage and overall figure from the paper's steps, or null when there is no read
 * to show (progressOf; also a PDF that could not be read: the status bar says why as before).
 */
export function readingProgress(paper: PaperLike, steps: StepOut[]): ReadingProgress | null {
  if (checkFailure(steps) !== null) return null;
  return progressOf({ ...paper, ...readCounts(paper, steps) });
}
