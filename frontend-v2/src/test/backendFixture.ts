// A JSON fixture of the backend's tests (backend-v2/tests/fixtures), for frontend tests that
// check the same real engine output.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export const backendFixture = <T = unknown>(name: string): T =>
  JSON.parse(
    readFileSync(
      resolve(process.cwd(), "../backend-v2/tests/fixtures", name),
      "utf8",
    ),
  ) as T;
