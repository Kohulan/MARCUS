// Runs before the CSS (blocking <script src> in <head>) so a visitor who chose
// a theme gets it on the first paint of a pre-rendered page. No inline script:
// the CSP is script-src 'self'.
(function () {
  try {
    var theme = window.localStorage.getItem("marcus-theme");
    if (theme === "light" || theme === "dark") {
      document.documentElement.setAttribute("data-theme", theme);
    }
  } catch {
    // Storage blocked or unavailable: follow the system setting.
  }
})();
