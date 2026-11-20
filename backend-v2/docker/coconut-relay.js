// The COCONUT relay's njs helpers (nginx.conf): the answer filter and the per-client key.
//
// The answer filter (nginx.conf, `location ^~ /api/v2/coconut/`): of COCONUT's
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

// The key the per-client limits count (js_set $coconut_client): an IPv4 address as it is, an
// IPv6 address as its /64 (one client usually holds a whole /64; the API buckets /64 too).
// The address is nginx's client address after the real_ip switch.
function clientKey(r) {
    var addr = r.variables.remote_addr || "";
    if (addr.indexOf(":") === -1 || addr.indexOf(".") !== -1) {
        return addr;  // IPv4, or IPv6 with an embedded IPv4 (rare): the whole address
    }
    var halves = addr.toLowerCase().split("::");
    var head = halves[0] ? halves[0].split(":") : [];
    var tail = halves.length > 1 && halves[1] ? halves[1].split(":") : [];
    var groups = head;
    if (halves.length > 1) {
        for (var i = head.length + tail.length; i < 8; i++) {
            groups.push("0");
        }
        groups = groups.concat(tail);
    }
    var prefix = [];
    for (var j = 0; j < 4; j++) {
        prefix.push(parseInt(groups[j] || "0", 16).toString(16));
    }
    return prefix.join(":") + "::/64";
}

export default { onlyStatusAndBody, clientKey };
