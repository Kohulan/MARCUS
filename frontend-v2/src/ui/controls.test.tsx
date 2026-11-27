import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import SegmentedControl from "./SegmentedControl";
import Switch from "./Switch";

function Segments({ disabled = false }: { disabled?: boolean }) {
  const [v, setV] = useState<"a" | "b" | "c">("a");
  return (
    <SegmentedControl
      label="Pick"
      value={v}
      onChange={setV}
      disabled={disabled}
      options={[
        { value: "a", label: "Alpha", tone: { fill: "red", ink: "white", dot: "red" } },
        { value: "b", label: "Beta" },
        { value: "c", label: "Gamma" },
      ]}
    />
  );
}

describe("SegmentedControl", () => {
  it("is a radio group: click and arrow keys move the choice, focus follows, the knob slides", () => {
    render(<Segments />);
    const group = screen.getByRole("radiogroup", { name: "Pick" });
    expect(screen.getByRole("radio", { name: "Alpha" })).toHaveAttribute("aria-checked", "true");
    expect(group.style.getPropertyValue("--seg-fill")).toBe("red");
    fireEvent.click(screen.getByRole("radio", { name: "Beta" }));
    expect(screen.getByRole("radio", { name: "Beta" })).toHaveAttribute("aria-checked", "true");
    expect(group.style.getPropertyValue("--seg-at")).toBe("1");
    expect(group.style.getPropertyValue("--seg-fill")).toBe(""); // no tone: the default green
    fireEvent.keyDown(screen.getByRole("radio", { name: "Beta" }), { key: "ArrowRight" });
    expect(screen.getByRole("radio", { name: "Gamma" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "Gamma" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("radio", { name: "Gamma" }), { key: "ArrowRight" }); // wraps
    expect(screen.getByRole("radio", { name: "Alpha" })).toHaveAttribute("aria-checked", "true");
    fireEvent.keyDown(screen.getByRole("radio", { name: "Alpha" }), { key: "End" });
    expect(screen.getByRole("radio", { name: "Gamma" })).toHaveAttribute("aria-checked", "true");
  });

  it("disabled: nothing is checked and nothing can be chosen", () => {
    render(<Segments disabled />);
    for (const name of ["Alpha", "Beta", "Gamma"]) {
      expect(screen.getByRole("radio", { name })).toBeDisabled();
      expect(screen.getByRole("radio", { name })).toHaveAttribute("aria-checked", "false");
    }
  });
});

describe("Switch", () => {
  it("is a switch named by its label; a click flips it", () => {
    function S() {
      const [on, setOn] = useState(true);
      return <Switch label="Marks" checked={on} onChange={setOn} />;
    }
    render(<S />);
    const sw = screen.getByRole("switch", { name: "Marks" });
    expect(sw).toHaveAttribute("aria-checked", "true");
    fireEvent.click(sw);
    expect(sw).toHaveAttribute("aria-checked", "false");
  });
});
