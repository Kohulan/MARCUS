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

  it("an annotate step has its own words where the shared ones do not fit", () => {
    expect(reasonText("bad_input", "annotate")).toBe("no title, abstract or introduction was found");
    expect(reasonText("timeout", "annotate")).toBe("it took too long");
    expect(reasonText("engine_error", "annotate")).toBe("the model failed");
    expect(reasonText("worker_lost", "annotate")).toBe("the worker stopped");
    expect(reasonText(null, "annotate")).toBe("an unknown error");
    expect(reasonText("toString", "annotate")).toBe("an unknown error");
    expect(reasonText("bad_input", "constructor")).toBe("the page could not be opened");
  });
});
