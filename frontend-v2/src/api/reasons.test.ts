import { describe, expect, it } from "vitest";
import { reasonText } from "./reasons";

describe("reasonText", () => {
  it("maps each error class to its exact text", () => {
    expect(reasonText("timeout")).toBe("it took too long");
    expect(reasonText("worker_lost")).toBe("the worker stopped while reading it");
    expect(reasonText("bad_input")).toBe("the page could not be opened");
    expect(reasonText("engine_error")).toBe("the engine failed");
    expect(reasonText("something_new")).toBe("an unknown error");
    expect(reasonText(null)).toBe("an unknown error");
    expect(reasonText("toString")).toBe("an unknown error");
  });
});
