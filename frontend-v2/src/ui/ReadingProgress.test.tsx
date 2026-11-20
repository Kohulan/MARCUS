// The reading progress bar: a native <progress> with its spoken value, the stages in words,
// one polite announcement per stage (never per count), no style attribute (CSP).
import { render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { ReadingProgress as Model } from "../workspace/readingProgress";
import ReadingProgress from "./ReadingProgress";

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
  started: true,
  valueText: `Reading pages, ${done} of 5`,
  stages: stagesAt(1, [null, `${done}/5`]),
});

const structures = (done: number, total: number, fraction: number): Model => ({
  stage: "structures",
  fraction,
  pages: { done: 5, total: 5 },
  structures: { done, total },
  started: true,
  valueText: `Reading structures, ${done} of ${total}`,
  stages: stagesAt(2, [null, null, `${done}/${total}`]),
});

const waiting: Model = {
  stage: "waiting",
  fraction: null,
  pages: null,
  structures: { done: 0, total: 0 },
  started: false,
  valueText: "Waiting",
  stages: stagesAt(-1),
};

describe("ReadingProgress", () => {
  it("is a native progress bar with its value, its name and its spoken value", () => {
    render(<ReadingProgress progress={pages(3, 0.32)} label="Reading progress" />);
    const bar = screen.getByRole("progressbar", { name: "Reading progress" });
    expect(bar.tagName).toBe("PROGRESS");
    expect(bar).toHaveAttribute("max", "100");
    expect(bar).toHaveAttribute("value", "32");
    expect(bar).toHaveAttribute("aria-valuetext", "Reading pages, 3 of 5");
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
    expect(bar).not.toHaveAttribute("value");
    expect(bar).toHaveAttribute("aria-valuetext", "Waiting");
    expect(screen.getByText("About 3 min in the queue")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Stages" })).toBeNull();
  });

  it("never moves back while the paper is open", () => {
    const { rerender } = render(<ReadingProgress progress={pages(3, 0.4)} label="p" />);
    rerender(<ReadingProgress progress={structures(4, 10, 0.35)} label="p" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("value", "40");
    rerender(<ReadingProgress progress={structures(8, 10, 0.6)} label="p" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("value", "60");
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
  });

  it("the compact form is a thin bar and one short line, with no announcement", () => {
    render(<ReadingProgress progress={structures(10, 15, 0.7)} label="Progress of a.pdf" compact />);
    expect(screen.getByRole("progressbar", { name: "Progress of a.pdf" })).toHaveAttribute("value", "70");
    expect(screen.getByText("Reading structures 10/15")).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("renders on the server with no style attribute", () => {
    const html = renderToString(<ReadingProgress progress={pages(3, 0.32)} label="p" announce />);
    expect(html).toContain("<progress");
    expect(html).not.toMatch(/style=/);
  });
});
