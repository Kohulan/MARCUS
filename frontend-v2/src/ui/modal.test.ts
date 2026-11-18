import { afterEach, describe, expect, it } from "vitest";
import { returnFocus } from "./modal";

afterEach(() => {
  document.body.replaceChildren();
});

function setup() {
  const home = document.createElement("section");
  home.tabIndex = -1;
  const opener = document.createElement("button");
  home.append(opener);
  document.body.append(home);
  return { home, opener };
}

describe("returnFocus", () => {
  it("gives focus back to the opener while it is there", () => {
    const { home, opener } = setup();
    returnFocus(opener, home);
    expect(opener).toHaveFocus();
  });

  it("falls back to the host's fallback when the opener is gone", () => {
    const { home, opener } = setup();
    opener.remove();
    returnFocus(opener, home);
    expect(home).toHaveFocus();
  });

  it("falls back when the opener is disabled or was the body", () => {
    const { home, opener } = setup();
    opener.disabled = true;
    returnFocus(opener, home);
    expect(home).toHaveFocus();
    home.blur();
    returnFocus(document.body, home);
    expect(home).toHaveFocus();
  });

  it("leaves focus alone with no fallback", () => {
    const { opener } = setup();
    opener.remove();
    returnFocus(opener, null);
    expect(document.activeElement).toBe(document.body);
  });
});
