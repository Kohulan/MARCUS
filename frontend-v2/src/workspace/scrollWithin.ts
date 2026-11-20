/**
 * Scrolls `container` so `el` is in view: only as far as needed ("nearest"), to its top
 * ("start"), or to the container's middle ("center": an occurrence keeps text around it). The
 * view is the container under its sticky caption (a `.pv-cap` child), which would otherwise
 * cover what it scrolled to; "nearest" and "start" leave room for a marker's tag above its box.
 */
export function scrollWithin(
  container: HTMLElement | null,
  el: Element | null | undefined,
  block: "nearest" | "start" | "center",
  smooth: boolean,
) {
  if (!container || !el) return;
  const c = container.getBoundingClientRect();
  const r = el.getBoundingClientRect();
  let delta = 0;
  if (block === "center") {
    delta = r.top - c.top - (c.height - r.height) / 2;
  } else {
    const margin = 28; // room for a marker's tag above its box
    const cap = container.querySelector(":scope > .pv-cap")?.getBoundingClientRect().height ?? 0;
    const edge = c.top + cap + margin;
    if (block === "start" || r.top < edge) delta = r.top - edge;
    else if (r.bottom > c.bottom - margin) {
      delta = Math.min(r.bottom - c.bottom + margin, r.top - edge);
    }
    if (Math.abs(delta) < 1) return;
  }
  const top = container.scrollTop + delta;
  if (typeof container.scrollTo === "function") {
    container.scrollTo({ top, behavior: smooth ? "smooth" : "auto" });
  } else {
    container.scrollTop = top;
  }
}
