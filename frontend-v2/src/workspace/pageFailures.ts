// What the status bar reads from a paper's steps. Pages are 0-based here, as in the API.
import { reasonText } from "../api/reasons";
import { isStepActive } from "../api/status";
import type { StepOut } from "../api/types";

export type PageFailure = { page0: number; errorClass: string | null; retrying: boolean };

const PAGE_KINDS = new Set(["render_page", "segment_page"]);

const ms = (iso: string) => {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? 0 : t;
};

/**
 * Newest first, as the server's page_step_order: created_at, then kind (segment_page before
 * render_page), then the later one in the list (steps come oldest first, by created_at and
 * seq). Same-millisecond times fall back to the ISO strings, which carry microseconds. The
 * one order of steps in the UI: filter before calling it, it sorts what it is given.
 */
export function newestFirst(steps: StepOut[]): StepOut[] {
  return steps
    .map((s, i) => ({ s, i, t: ms(s.created_at) }))
    .sort(
      (a, b) =>
        b.t - a.t ||
        b.s.created_at.localeCompare(a.s.created_at) ||
        b.s.kind.localeCompare(a.s.kind) ||
        b.i - a.i,
    )
    .map(({ s }) => s);
}

/** Each page's render_page and segment_page steps, newest first. */
export function pageSteps(steps: StepOut[]): Map<number, StepOut[]> {
  const byPage = new Map<number, StepOut[]>();
  for (const s of newestFirst(steps.filter((s) => PAGE_KINDS.has(s.kind) && s.page !== null))) {
    const list = byPage.get(s.page!) ?? [];
    list.push(s);
    byPage.set(s.page!, list);
  }
  return byPage;
}

/**
 * The failed pages, by the server's failed_pages rule (F0-1, R-F10): per page, the newest
 * render_page or segment_page step decides. Failed → listed. Active after an older failure →
 * listed as retrying (with the old failure's class). Done, or never failed → not listed.
 */
export function pageFailures(steps: StepOut[]): PageFailure[] {
  const out: PageFailure[] = [];
  for (const [page0, list] of pageSteps(steps)) {
    const newest = list[0]!;
    if (newest.status === "failed") {
      out.push({ page0, errorClass: newest.error_class, retrying: false });
    } else if (isStepActive(newest.status)) {
      const failed = list.find((s) => s.status === "failed");
      if (failed) out.push({ page0, errorClass: failed.error_class, retrying: true });
    }
  }
  return out.sort((a, b) => a.page0 - b.page0);
}

const BAD_PDF = "it is encrypted, damaged or has more than 100 pages";

/** Why the PDF check failed (its newest check_pdf step), or null when it did not fail. */
export function checkFailure(steps: StepOut[]): string | null {
  const check = newestFirst(steps.filter((s) => s.kind === "check_pdf"))[0];
  if (!check || check.status !== "failed") return null;
  return check.error_class === "bad_input" ? BAD_PDF : reasonText(check.error_class);
}
