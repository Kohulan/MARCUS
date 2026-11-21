import { act, StrictMode } from "react";
import { hydrateRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { render } from "./entry-server";

afterEach(() => {
  vi.restoreAllMocks();
  document.body.replaceChildren();
});

// The pre-rendered HTML must hydrate without a mismatch, which also proves no
// component reads window, document, localStorage or matchMedia during render.
describe("pre-rendered pages hydrate cleanly", () => {
  it.each(["/", "/about", "/privacy", "/disclaimer", "/no-such-page"])("%s", async (url) => {
    const html = render(url);
    expect(html).toContain("<h1");

    const container = document.createElement("div");
    container.append(document.createRange().createContextualFragment(html));
    document.body.append(container);

    const errors: unknown[] = [];
    vi.spyOn(console, "error").mockImplementation((...args) => errors.push(args));

    const root = await act(async () =>
      hydrateRoot(
        container,
        <StrictMode>
          <MemoryRouter initialEntries={[url]}>
            <App />
          </MemoryRouter>
        </StrictMode>,
        { onRecoverableError: (error) => errors.push(error) },
      ),
    );

    expect(errors).toEqual([]);
    act(() => root.unmount());
  });
});
