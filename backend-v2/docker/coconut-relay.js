// The COCONUT relay's answer filter (nginx.conf, `location ^~ /api/v2/coconut/`): of COCONUT's
// answer only the status, the body and its Content-Type / Content-Length reach the browser.
// Every other upstream header (cookies, CORS, redirects, caching, rate-limit counters, anything
// new) is dropped here; the security headers in KEEP are nginx's own fixed ones (add_header),
// COCONUT's versions of them are removed by proxy_hide_header before this runs.
const KEEP = [
    "content-type",
    "content-length",
    "cache-control",
    "content-security-policy",
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
    "cross-origin-resource-policy",
];

// njs (not full ES6): no for...of, so a plain loop.
function onlyStatusAndBody(r) {
    var names = Object.keys(r.headersOut);
    for (var i = 0; i < names.length; i++) {
        if (KEEP.indexOf(names[i].toLowerCase()) === -1) {
            delete r.headersOut[names[i]];
        }
    }
}

export default { onlyStatusAndBody };
