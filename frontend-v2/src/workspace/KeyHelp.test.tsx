// The Keys dialog: a native <dialog> (top layer, the page behind inert), Close is a glass
// pill, and closing it gives focus back to the opener, or to the focus-mode region when the
// opener is gone (so the review keys, which act only inside the region, stay alive).
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import KeyHelp from "./KeyHelp";

function Host() {
  const [open, setOpen] = useState(false);
  return (
    <section data-focus-home="" tabIndex={-1} aria-label="Focus [01]">
      {/* The opener goes while the list is open, as a re-rendered control would. */}
      {!open && (
        <button type="button" onClick={() => setOpen(true)}>
          Keys
        </button>
      )}
      {open && <KeyHelp onClose={() => setOpen(false)} />}
    </section>
  );
}

describe("KeyHelp", () => {
  it("is a native dialog named Keys, open, with a glass Close that has focus", () => {
    render(<KeyHelp onClose={() => undefined} />);
    const dialog = screen.getByRole("dialog", { name: "Keys" });
    expect(dialog.tagName).toBe("DIALOG");
    expect(dialog).toHaveAttribute("open");
    const close = screen.getByRole("button", { name: "Close" });
    expect(close).toHaveClass("glass", "glass--clear", "glass--sm");
    expect(close).toHaveFocus();
  });

  it("closing with the opener gone puts focus on the focus-mode region", () => {
    render(<Host />);
    const opener = screen.getByRole("button", { name: "Keys" });
    opener.focus();
    fireEvent.click(opener);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("region", { name: "Focus [01]" })).toHaveFocus();
  });
});
