// The send's announcements: start, each quarter crossed, end; never every count.
import { describe, expect, it } from "vitest";
import { chunkNews, endNews, quarterOf, startNews } from "./sendNews";

describe("sendNews", () => {
  it("says each quarter once, however many chunks cross it", () => {
    const said: string[] = [];
    let before = 0;
    for (let done = 10; done <= 200; done += 10) {
      const news = chunkNews(before, done, 200);
      if (news) said.push(news);
      before = done;
    }
    expect(said).toEqual(["Sent 50 of 200", "Sent 100 of 200", "Sent 150 of 200"]);
  });

  it("a chunk that jumps two quarters is said once", () => {
    expect(chunkNews(0, 120, 200)).toBe("Sent 120 of 200");
    expect(chunkNews(120, 140, 200)).toBeNull();
  });

  it("leaves the end to endNews", () => {
    expect(chunkNews(150, 200, 200)).toBeNull();
    expect(endNews(198, 200)).toBe("Sent 198 of 200");
  });

  it("says the start", () => {
    expect(startNews(60)).toBe("Sending 60 to COCONUT");
    expect(quarterOf(0, 0)).toBe(4);
  });
});
