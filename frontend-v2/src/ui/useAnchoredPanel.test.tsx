import { render } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAnchoredPanel } from "./anchor";

// jsdom has no Popover API: the hook is driven here with a stand-in that records the calls.
const shown = new Set<Element>();
const ownRect = HTMLButtonElement.prototype.getBoundingClientRect;

function Menu({ open, onAway }: { open: boolean; onAway?: () => void }) {
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  useAnchoredPanel(open, button, panel, { prefer: "above", align: "end" }, onAway);
  return (
    <section className="col">
      <button ref={button} type="button">
        More
      </button>
      {open && (
        <div ref={panel} data-testid="panel">
          menu
        </div>
      )}
    </section>
  );
}

const rect = (x: number, y: number, width: number, height: number) => () =>
  DOMRect.fromRect({ x, y, width, height });

beforeEach(() => {
  const root = document.documentElement;
  Object.defineProperty(root, "clientWidth", { configurable: true, value: 1024 });
  Object.defineProperty(root, "clientHeight", { configurable: true, value: 768 });
  Object.defineProperty(HTMLElement.prototype, "showPopover", {
    configurable: true,
    value(this: HTMLElement) {
      shown.add(this);
    },
  });
  Object.defineProperty(HTMLElement.prototype, "hidePopover", {
    configurable: true,
    value(this: HTMLElement) {
      shown.delete(this);
    },
  });
  vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(200);
  vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(260);
});

afterEach(() => {
  vi.restoreAllMocks();
  HTMLButtonElement.prototype.getBoundingClientRect = ownRect;
  shown.clear();
  const root = document.documentElement as unknown as Record<string, unknown>;
  delete root.clientWidth;
  delete root.clientHeight;
  delete (HTMLElement.prototype as unknown as Record<string, unknown>).showPopover;
  delete (HTMLElement.prototype as unknown as Record<string, unknown>).hidePopover;
});

describe("useAnchoredPanel", () => {
  it("lifts the open panel into the top layer next to its button, inside the window", () => {
    HTMLButtonElement.prototype.getBoundingClientRect = rect(900, 220, 80, 32);
    const { getByTestId, rerender } = render(<Menu open />);
    const panel = getByTestId("panel");
    expect(panel).toHaveAttribute("popover", "manual");
    expect(panel).toHaveAttribute("data-anchored");
    expect(shown.has(panel)).toBe(true);
    // No room above the first card's button: below it, right edges lined up.
    expect(panel.dataset.side).toBe("below");
    expect(panel.style.position).toBe("fixed");
    expect(panel.style.top).toBe("258px");
    expect(panel.style.left).toBe("780px");
    expect(panel.style.maxHeight).toBe(`${768 - 8 - 258}px`);
    rerender(<Menu open={false} />);
    expect(shown.size).toBe(0);
  });

  it("calls onAway once its button is scrolled out of its column", async () => {
    const onAway = vi.fn();
    HTMLButtonElement.prototype.getBoundingClientRect = rect(900, 600, 80, 32);
    const { container } = render(<Menu open onAway={onAway} />);
    const col = container.querySelector<HTMLElement>(".col")!;
    col.style.overflowY = "auto";
    col.getBoundingClientRect = rect(600, 260, 420, 500);
    expect(onAway).not.toHaveBeenCalled();
    HTMLButtonElement.prototype.getBoundingClientRect = rect(900, 200, 80, 32);
    col.dispatchEvent(new Event("scroll"));
    await new Promise((r) => requestAnimationFrame(r));
    expect(onAway).toHaveBeenCalled();
  });

  it("leaves the panel to its CSS without the Popover API", () => {
    delete (HTMLElement.prototype as unknown as Record<string, unknown>).showPopover;
    const { getByTestId } = render(<Menu open />);
    expect(getByTestId("panel")).not.toHaveAttribute("popover");
    expect(getByTestId("panel").style.top).toBe("");
  });
});
