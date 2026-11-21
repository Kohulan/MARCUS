import { useEffect } from "react";

// Whether a page renders as the first screen of the page load (the pre-rendered HTML and its
// hydration), not after a click inside the app. The landing plays its full entrance (the
// header and footer arriving) only then. On the server every render is a first screen.
let first = true;

export const isFirstScreen = (): boolean => first;

/** Called once by the app frame: after its first commit, every later page is a navigation. */
export function useFirstScreenDone(): void {
  useEffect(() => {
    first = false;
  }, []);
}
