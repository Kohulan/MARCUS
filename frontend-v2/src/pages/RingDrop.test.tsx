// The ring when the tool cannot be opened (its chunk does not load): it leaves "Uploading…",
// says so in the tool's own words, keeps nothing in memory, and stays on the landing.
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { takeHandOff } from "../tool/files";
import RingDrop, { NO_CONNECTION } from "./RingDrop";

vi.mock("../api/QueryProvider", () => {
  throw new Error("chunk did not load");
});

describe("RingDrop when the tool cannot be opened", () => {
  it("shows the problem, re-enables the zone, and does not leave the landing", async () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<RingDrop />} />
          <Route path="/app" element={<p>tool opened</p>} />
        </Routes>
      </MemoryRouter>,
    );
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    fireEvent.change(input, {
      target: { files: [new File(["%PDF"], "a.pdf", { type: "application/pdf" })] },
    });
    expect(container.querySelector(".dz")).toHaveClass("is-done");
    expect(await screen.findByRole("alert")).toHaveTextContent(NO_CONNECTION);
    const zone = container.querySelector(".dz");
    expect(zone).toHaveClass("is-error");
    expect(zone).not.toHaveAttribute("aria-disabled");
    expect(screen.queryByText("tool opened")).toBeNull();
    expect(takeHandOff("h1")).toBeNull();
  });
});
