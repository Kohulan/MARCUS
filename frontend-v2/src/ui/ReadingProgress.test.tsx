// The reading progress bar: the shared progress bar with its percentage and spoken value, the
// stages in words, one polite announcement per stage (never per count or percent), no style
// attribute (CSP), and an annotate run's time-based estimate.
import { act, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ANNOTATE_TYPICAL_MS, END_HOLD_MS, FILL_MS } from "./progressMotion";
import type { ReadingProgress as Model } from "../workspace/readingProgress";
import ReadingProgress, { useShownProgress } from "./ReadingProgress";

const stagesAt = (current: number, counts: (string | null)[] = []): Model["stages"] =>
  (["check", "pages", "structures", "end"] as const).map((key, i) => ({
    key,
    label: ["Checking PDF", "Reading pages", "Reading structures", "Finishing"][i]!,
    count: counts[i] ?? null,
    state: i < current ? "done" : i === current ? "current" : "next",
  }));

const pages = (done: number, fraction: number): Model => ({
  stage: "pages",
  fraction,
  pages: { done, total: 5 },
  structures: { done: 0, total: 0 },
  valueText: `Reading pages, ${done} of 5`,
  line: `Reading pages ${done}/5`,
  said: "Reading pages",
  estimated: false,
  stages: stagesAt(1, [null, `${done}/5`]),
});

const structures = (done: number, total: number, fraction: number): Model => ({
  stage: "structures",
  fraction,
  pages: { done: 5, total: 5 },
  structures: { done, total },
  valueText: `Reading structures, ${done} of ${total}`,
  line: `Reading structures ${done}/${total}`,
  said: "Reading structures",
  estimated: false,
  stages: stagesAt(2, [null, null, `${done}/${total}`]),
});

const waiting: Model = {
  stage: "waiting",
  fraction: null,
  pages: null,
  structures: { done: 0, total: 0 },
  valueText: "Waiting",
  line: "Waiting",
  said: "Waiting",
  estimated: false,
  stages: stagesAt(-1),
};

describe("ReadingProgress", () => {
  it("is a progress bar with its value, its name, its spoken value and its percentage", () => {
    render(<ReadingProgress progress={pages(3, 0.32)} label="Reading progress" />);
    const bar = screen.getByRole("progressbar", { name: "Reading progress" });
    expect(bar).toHaveAttribute("aria-valuemax", "100");
    expect(bar).toHaveAttribute("aria-valuenow", "32");
    expect(bar).toHaveAttribute("aria-valuetext", "Reading pages, 3 of 5, 32%");
    expect(screen.getByText("32%")).toBeInTheDocument();
  });

  it("names the stages, marks the current one and prints its count", () => {
    render(<ReadingProgress progress={structures(10, 15, 0.7)} label="Reading progress" />);
    const list = screen.getByRole("list", { name: "Stages" });
    const items = [...list.querySelectorAll("li")];
    expect(items.map((li) => li.textContent)).toEqual([
      "Checking PDF",
      "Reading pages",
      "Reading structures 10/15",
      "Finishing",
    ]);
    expect(items[2]).toHaveAttribute("aria-current", "step");
    expect(items[0]!.className).toContain("rp__stage--done");
    expect(items[3]!.className).toContain("rp__stage--next");
  });

  it("is indeterminate (no value) while nothing can be measured, and says it waits in the queue", () => {
    render(
      <ReadingProgress progress={waiting} label="Reading progress" queueNote="About 3 min in the queue" />,
    );
    const bar = screen.getByRole("progressbar");
    expect(bar).not.toHaveAttribute("aria-valuenow");
    expect(bar).toHaveAttribute("aria-valuetext", "Waiting");
    expect(screen.queryByText(/%$/)).toBeNull();
    expect(screen.getByText("About 3 min in the queue")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Stages" })).toBeNull();
  });

  it("shows the queue estimate beside the stages once the read has started", () => {
    render(<ReadingProgress progress={pages(1, 0.1)} label="p" queueNote="About 6 min in the queue" />);
    expect(screen.getByRole("list", { name: "Stages" })).toBeInTheDocument();
    expect(screen.getByText("About 6 min in the queue")).toBeInTheDocument();
  });

  it("never moves back while the paper is open", () => {
    const { rerender } = render(<ReadingProgress progress={pages(3, 0.4)} label="p" />);
    rerender(<ReadingProgress progress={structures(4, 10, 0.35)} label="p" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40");
    rerender(<ReadingProgress progress={structures(8, 10, 0.6)} label="p" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "60");
  });

  it("announces a new stage politely, not a new count", () => {
    const { rerender } = render(<ReadingProgress progress={pages(1, 0.1)} label="p" announce />);
    const live = screen.getByRole("status");
    expect(live).toHaveAttribute("aria-live", "polite");
    expect(live).toHaveTextContent("Reading pages");
    rerender(<ReadingProgress progress={pages(2, 0.2)} label="p" announce />);
    expect(live).toHaveTextContent(/^Reading pages$/);
    rerender(<ReadingProgress progress={structures(1, 4, 0.5)} label="p" announce />);
    expect(live).toHaveTextContent(/^Reading structures$/);
    rerender(<ReadingProgress progress={structures(2, 4, 0.6)} label="p" announce />);
    expect(live).toHaveTextContent(/^Reading structures$/); // no percent in the announcement
  });

  it("the compact form is a thin bar and one short line, with no announcement", () => {
    render(<ReadingProgress progress={structures(10, 15, 0.7)} label="Progress of a.pdf" compact />);
    expect(screen.getByRole("progressbar", { name: "Progress of a.pdf" })).toHaveAttribute("aria-valuenow", "70");
    expect(screen.getByText("70%")).toBeInTheDocument();
    expect(screen.getByText("Reading structures 10/15")).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("renders on the server with no style attribute", () => {
    const html = renderToString(<ReadingProgress progress={pages(3, 0.32)} label="p" announce />);
    expect(html).toContain('role="progressbar"');
    expect(html).not.toMatch(/style=/);
  });

  describe("an annotate run (no figure from the model): useShownProgress", () => {
    const FAKE = [
      "setInterval",
      "clearInterval",
      "setTimeout",
      "clearTimeout",
      "Date",
      "requestAnimationFrame",
      "cancelAnimationFrame",
      "performance",
    ] as const;
    afterEach(() => {
      vi.useRealTimers();
    });
    const annotating: Model = {
      ...waiting,
      stage: "annotating",
      valueText: "Annotating",
      line: "",
      said: "",
      estimated: true,
      stages: [],
    };
    const done: Model = { ...waiting, stage: "done", fraction: 1, valueText: "Done", line: "", said: "Done" };

    function Shown({ model, keepDone }: { model: Model | null; keepDone?: boolean }) {
      const shown = useShownProgress(model, { keepDone: keepDone ?? false });
      return shown ? <ReadingProgress progress={shown} label="Reading progress" announce /> : null;
    }

    it("shows the time-based estimate, labelled as one, and never 100% while it runs", () => {
      vi.useFakeTimers({ toFake: [...FAKE] });
      render(<Shown model={annotating} />);
      const bar = screen.getByRole("progressbar");
      expect(bar).toHaveAttribute("aria-valuenow", "0");
      expect(screen.queryByRole("list", { name: "Stages" })).toBeNull();
      expect(screen.getByRole("status")).toHaveTextContent(/^$/); // the badge says Annotating
      act(() => {
        vi.advanceTimersByTime(ANNOTATE_TYPICAL_MS);
      });
      act(() => {
        vi.advanceTimersByTime(FILL_MS); // the printed figure catches up with the fill
      });
      expect(bar).toHaveAttribute("aria-valuetext", "Annotating, about 90%");
      // the printed figure follows the moving estimate a step behind
      expect(document.querySelector(".pb__pct")!.textContent).toMatch(/^~(89|90)%$/);
      act(() => {
        vi.advanceTimersByTime(30 * 60_000);
      });
      expect(Number(bar.getAttribute("aria-valuenow"))).toBeLessThanOrEqual(95);
    });

    it("ends on its full bar for a moment, then no bar for the done paper", () => {
      vi.useFakeTimers({ toFake: [...FAKE] });
      const { rerender } = render(<Shown model={annotating} />);
      act(() => {
        vi.advanceTimersByTime(2000);
      });
      rerender(<Shown model={done} />);
      expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "Annotating, 100%");
      act(() => {
        vi.advanceTimersByTime(END_HOLD_MS + 50);
      });
      expect(screen.queryByRole("progressbar")).toBeNull();
    });

    it("a read seen here keeps its full bar when it is done, if asked to", () => {
      const { rerender } = render(<Shown model={pages(4, 0.8)} keepDone />);
      rerender(<Shown model={done} keepDone />);
      expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
      rerender(<Shown model={null} keepDone />);
      expect(screen.queryByRole("progressbar")).toBeNull();
    });

    it("a paper opened done has no bar", () => {
      render(<Shown model={done} keepDone />);
      expect(screen.queryByRole("progressbar")).toBeNull();
    });
  });
});
