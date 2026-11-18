// Matomo, the one tracker of MARCUS (https://matomo.nfdi4chem.de/, site id 7). The v1
// snippet, moved to a file for the CSP (no inline scripts). Two changes from v1: the page
// views come from the app (src/analytics.ts), one per route with the route template, so a
// real paper or image id never reaches Matomo; and link tracking is off, because download
// links into /api/v2/ carry those ids.
(function () {
  var _paq = (window._paq = window._paq || []);
  var u = "https://matomo.nfdi4chem.de/";
  _paq.push(["setTrackerUrl", u + "matomo.php"]);
  _paq.push(["setSiteId", "7"]);
  var d = document;
  var g = d.createElement("script");
  g.async = true;
  g.src = u + "matomo.js";
  d.head.appendChild(g);
})();
