import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "./App";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("App routes", () => {
  it("renders the landing headline at /", () => {
    renderAt("/");
    expect(
      screen.getByRole("heading", { level: 1, name: "Every molecule has a source." }),
    ).toBeInTheDocument();
  });

  it("loads the lazy tool route at /app and shows MARCUS", async () => {
    renderAt("/app");
    expect(await screen.findByText("MARCUS")).toBeInTheDocument();
  });

  it("renders the not-found page for an unknown path", () => {
    renderAt("/no-such-page");
    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
  });
});
