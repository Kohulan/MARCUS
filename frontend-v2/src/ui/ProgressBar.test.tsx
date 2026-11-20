// The one progress bar: a progressbar with its percentage (value, spoken value and printed),
// the fill set through the CSSOM (no style attribute), a count-up that eases and never goes
// down, the sheen only while work goes on, an indeterminate bar with no number, and a jump
// with no count-up under reduced motion.
import { act, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ProgressBar, { useAnnotateEstimate } from "./ProgressBar";
import { reduceMotion } from "../test/reduceMotion";
import { ANNOTATE_TYPICAL_MS, END_HOLD_MS, FILL_MS } from "./progressMotion";

const FAKE = [
  "setTimeout",
  "clearTimeout",
  "setInterval",
  "clearInterval",
  "requestAnimationFrame",
  "cancelAnimationFrame",
  "performance",
  "Date",
] as const;

const pct = () => document.querySelector(".pb__pct")!.textContent;
const advance = (ms: number) =>
  act(() => {
    vi.advanceTimersByTime(ms);
  });

describe("ProgressBar", () => {
  it("is a progressbar with its value, its name and its spoken value with the percentage", () => {
    render(<ProgressBar value={0.625} label="Reading progress" valueText="Reading structures, 10 of 15" />);
    const bar = screen.getByRole("progressbar", { name: "Reading progress" });
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
    expect(bar).toHaveAttribute("aria-valuenow", "62");
    expect(bar).toHaveAttribute("aria-valuetext", "Reading structures, 10 of 15, 62%");
  });

  it("prints the percentage beside the bar, hidden from screen readers (the bar says it)", () => {
    render(<ProgressBar value={0.4} label="p" />);
    const figure = document.querySelector(".pb__pct")!;
    expect(figure).toHaveTextContent("40%");
    expect(figure).toHaveAttribute("aria-hidden", "true");
  });

  it("sets the fill through the CSSOM, never a style attribute in the markup", () => {
    render(<ProgressBar value={0.4} label="p" />);
    expect(screen.getByRole("progressbar").style.getPropertyValue("--pb")).toBe("0.4");
    const html = renderToString(<ProgressBar value={0.4} label="p" valueText="x" />);
    expect(html).toContain('role="progressbar"');
    expect(html).not.toMatch(/style=/);
  });

  it("has a sheen while work goes on, none once it is done or stopped", () => {
    const { container, rerender } = render(<ProgressBar value={0.4} label="p" />);
    expect(container.firstElementChild).toHaveClass("pb--active");
    rerender(<ProgressBar value={1} label="p" active={false} />);
    expect(container.firstElementChild).not.toHaveClass("pb--active");
  });

  it("is indeterminate with no value and no number while nothing is measured", () => {
    const { container } = render(<ProgressBar value={null} label="p" valueText="Waiting" />);
    const bar = screen.getByRole("progressbar");
    expect(bar).not.toHaveAttribute("aria-valuenow");
    expect(bar).toHaveAttribute("aria-valuetext", "Waiting");
    expect(container.firstElementChild).toHaveClass("pb--indeterminate");
    expect(container.firstElementChild).not.toHaveClass("pb--active");
    expect(pct()).toBe("");
  });

  it("an estimate is printed with a tilde and said with about, until it is full", () => {
    const { rerender } = render(<ProgressBar value={0.6} label="p" valueText="Annotating" estimated />);
    expect(pct()).toBe("~60%");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "Annotating, about 60%");
    rerender(<ProgressBar value={1} label="p" valueText="Annotating" estimated active={false} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "Annotating, 100%");
  });

  it("the small size is a class", () => {
    const { container } = render(<ProgressBar value={0.2} label="p" size="sm" />);
    expect(container.firstElementChild).toHaveClass("pb--sm");
  });

  describe("count-up", () => {
    beforeEach(() => {
      vi.useFakeTimers({ toFake: [...FAKE] });
    });
    afterEach(() => {
      vi.useRealTimers();
    });

    it("starts on its first value (no count from zero when it appears)", () => {
      render(<ProgressBar value={0.6} label="p" />);
      expect(pct()).toBe("60%");
    });

    it("counts up smoothly to a new value over the fill's transition time", () => {
      const { rerender } = render(<ProgressBar value={0.2} label="p" />);
      rerender(<ProgressBar value={0.6} label="p" />);
      // the bar's value is the new one at once; the printed figure follows the fill
      expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "60");
      expect(pct()).toBe("20%");
      advance(FILL_MS / 4);
      const quarter = parseInt(pct()!, 10);
      expect(quarter).toBeGreaterThan(20);
      expect(quarter).toBeLessThan(60);
      advance(FILL_MS);
      expect(pct()).toBe("60%");
    });

    it("never counts down: a lower value during the run keeps the higher figure", () => {
      const { rerender } = render(<ProgressBar value={0.5} label="p" />);
      const seen: number[] = [];
      rerender(<ProgressBar value={0.8} label="p" />);
      for (let i = 0; i < 6; i += 1) {
        advance(50);
        seen.push(parseInt(pct()!, 10));
      }
      rerender(<ProgressBar value={0.3} label="p" />);
      for (let i = 0; i < 12; i += 1) {
        advance(50);
        seen.push(parseInt(pct()!, 10));
      }
      for (let i = 1; i < seen.length; i += 1) expect(seen[i]).toBeGreaterThanOrEqual(seen[i - 1]!);
      expect(pct()).toBe("80%");
      expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "80");
    });

    it("work that starts again starts a new run from its own figure", () => {
      const { rerender } = render(<ProgressBar value={1} label="p" active={false} />);
      rerender(<ProgressBar value={0.1} label="p" />);
      advance(FILL_MS);
      expect(pct()).toBe("10%");
    });

    it("jumps with no count-up under reduced motion, the percentage still shown", () => {
      const restore = reduceMotion(true);
      try {
        const { rerender } = render(<ProgressBar value={0.2} label="p" />);
        rerender(<ProgressBar value={0.6} label="p" />);
        expect(pct()).toBe("60%");
      } finally {
        restore();
      }
    });
  });
});

describe("useAnnotateEstimate", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: [...FAKE] });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function Probe({ running }: { running: boolean }) {
    const v = useAnnotateEstimate(running);
    return <p data-testid="v">{v === null ? "none" : v.toFixed(3)}</p>;
  }
  const value = () => {
    const t = screen.getByTestId("v").textContent!;
    return t === "none" ? null : Number(t);
  };

  it("is nothing before a run", () => {
    render(<Probe running={false} />);
    expect(value()).toBeNull();
  });

  it("eases toward 90% over the typical run time, then creeps, at most 95%, never 100% while it runs", () => {
    render(<Probe running />);
    expect(value()).toBe(0);
    advance(ANNOTATE_TYPICAL_MS / 2);
    expect(value()).toBeGreaterThan(0.6);
    expect(value()).toBeLessThan(0.9);
    advance(ANNOTATE_TYPICAL_MS / 2);
    expect(value()).toBeCloseTo(0.9, 1);
    advance(10 * 60_000);
    expect(value()).toBeLessThanOrEqual(0.95);
  });

  it("is full when the run ends, then nothing once the end hold has passed", () => {
    const { rerender } = render(<Probe running />);
    advance(2000);
    rerender(<Probe running={false} />);
    expect(value()).toBe(1);
    advance(END_HOLD_MS + 50);
    expect(value()).toBeNull();
  });

  it("a run started inside the last one's hold starts from zero too", () => {
    const { rerender } = render(<Probe running />);
    advance(5000);
    rerender(<Probe running={false} />);
    advance(END_HOLD_MS / 2);
    rerender(<Probe running />);
    expect(value()).toBe(0);
    advance(500);
    expect(value()).toBeLessThan(0.3);
  });

  it("every bar of one run counts from one clock (the panel and the status bar say the same)", () => {
    function Two({ second }: { second: boolean }) {
      const a = useAnnotateEstimate(true, "step-1");
      const b = useAnnotateEstimate(second, second ? "step-1" : null);
      return <p data-testid="v">{`${a?.toFixed(2)} ${b === null ? "none" : b.toFixed(2)}`}</p>;
    }
    const { rerender } = render(<Two second={false} />);
    advance(3000);
    rerender(<Two second />); // the second bar sees the run 3 s in
    advance(500);
    const [a, b] = screen.getByTestId("v").textContent!.split(" ");
    expect(b).toBe(a);
    expect(Number(a)).toBeGreaterThan(0.6);
  });

  it("a new run starts again from zero", () => {
    const { rerender } = render(<Probe running />);
    advance(5000);
    rerender(<Probe running={false} />);
    advance(END_HOLD_MS + 50);
    rerender(<Probe running />);
    expect(value()).toBe(0);
  });
});
