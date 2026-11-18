import { afterEach, describe, expect, it } from "vitest";
import { returnFocus } from "./modal";

afterEach(() => {
  document.body.replaceChildren();
});

function setup(withHome = true) {
  const home = document.createElement("section");
  home.tabIndex = -1;
  if (withHome) home.setAttribute("data-focus-home", "");
  const opener = document.createElement("button");
  home.append(opener);
  document.body.append(home);
  return { home, opener };
}

describe("returnFocus", () => {
  it("gives focus back to the opener while it is there", () => {
    const { opener } = setup();
    returnFocus(opener);
    expect(opener).toHaveFocus();
  });

  it("falls back to the focus home when the opener is gone", () => {
    const { home, opener } = setup();
    opener.remove();
    returnFocus(opener);
    expect(home).toHaveFocus();
  });

  it("falls back to the focus home when the opener is disabled or was the body", () => {
    const { home, opener } = setup();
    opener.disabled = true;
    returnFocus(opener);
    expect(home).toHaveFocus();
    home.blur();
    returnFocus(document.body);
    expect(home).toHaveFocus();
  });

  it("leaves focus alone with no home", () => {
    const { opener } = setup(false);
    opener.remove();
    returnFocus(opener);
    expect(document.activeElement).toBe(document.body);
  });
});
