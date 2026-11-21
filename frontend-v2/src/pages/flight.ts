// The landing's first screen: each initial of the acrostic is copied out of the header's
// wordmark. The copy lifts off its letter in MARCUS, falls to its line (it drifts across and
// grows on the way, and turns from the Gmarket wordmark into the Geist initial), lands with a
// small squash, and the rest of the word slides out from behind it.
//
// Web Animations on six throwaway copies in a layer over the page (aria-hidden, no pointer
// events); sizes and places go through the CSSOM, never a style attribute (CSP style-src
// 'self'). The h1 itself never moves out of its layout: it is hidden until each copy lands,
// so a failed script leaves the CSS fallback (landing.css, .acro--assemble) to show it.

/** When the copies lift off, in ms after the first screen started: the header has arrived. */
const LAUNCH_AT = 480;
/** Later than this the CSS fallback is about to show the name: leave it to the CSS. */
const LATEST = 1500;
const FLIGHT = 700;
/** Far enough apart that each letter falls on its own, not as one clump. */
const STAGGER = 110;
/** How far a copy hops up off its letter before it falls, in px. */
const HOP = 10;
/** A small turn on the way down, in degrees, one per letter; each lands upright. */
const SPIN = [-7, 5, -9, 6, -5, 8];

const EASE = "cubic-bezier(0.22, 1, 0.36, 1)"; // --ease
const LIFT = "cubic-bezier(0.2, 0.6, 0.4, 1)";
const GRAVITY = "cubic-bezier(0.55, 0, 0.85, 0.3)";
const DRIFT = "cubic-bezier(0.45, 0, 0.3, 1)";

const centre = (r: DOMRect) => ({ x: r.left + r.width / 2, y: r.top + r.height / 2 });

function span(className: string, text?: string): HTMLSpanElement {
  const el = document.createElement("span");
  el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

/** One copy: the place (drifts across), the fall (hops, then drops), the two glyphs. */
function copyOf(letter: string, to: DOMRect, font: CSSStyleDeclaration) {
  const fly = span("acro-fly");
  const fall = span("acro-fly__fall");
  const glyphs = span("acro-fly__glyphs");
  const mark = span("acro-fly__mark", letter);
  const bold = span("acro-fly__bold", letter);
  glyphs.append(mark, bold);
  fall.append(glyphs);
  fly.append(fall);
  fly.style.left = `${to.left + window.scrollX}px`;
  fly.style.top = `${to.top + window.scrollY}px`;
  fly.style.width = `${to.width}px`;
  fly.style.height = `${to.height}px`;
  fly.style.fontSize = font.fontSize;
  fly.style.lineHeight = `${to.height}px`;
  fly.style.letterSpacing = font.letterSpacing;
  return { fly, fall, glyphs, mark, bold };
}

/**
 * Starts the flight for the landing's h1, or does nothing when it is too late, the header's
 * wordmark is not there, or the browser has no Web Animations. `origin` is when the landing's
 * CSS started (performance.now() time): 0 for the page the load opened on, the mount for a
 * landing reached by a click. Returns the cleanup.
 */
export function flyInitials(h1: HTMLElement, origin: number): () => void {
  const word = document.querySelector<HTMLElement>(".site-header__word");
  const text = word?.firstChild;
  const initials = [...h1.querySelectorAll<HTMLElement>(".acro__line > b")];
  const rests = [...h1.querySelectorAll<HTMLElement>(".acro__rest")];
  const now = performance.now() - origin;
  const first = initials[0];
  if (
    !word ||
    !first ||
    !(text instanceof Text) ||
    text.data.length < initials.length ||
    initials.length === 0 ||
    rests.length !== initials.length ||
    typeof h1.animate !== "function" ||
    now > LATEST
  ) {
    return () => {};
  }

  h1.classList.add("acro--flying"); // the CSS fallback stands down; the initials wait hidden
  const layer = span("acro-flight");
  layer.setAttribute("aria-hidden", "true");
  const running: Animation[] = [];
  const run = (el: Element, frames: Keyframe[], options: KeyframeAnimationOptions) => {
    running.push(el.animate(frames, options));
  };

  const launch = () => {
    document.body.append(layer);
    const range = document.createRange();
    const font = getComputedStyle(first);
    const mark = getComputedStyle(word);
    const markSize = parseFloat(mark.fontSize);
    // a letter's range ends after its letter spacing: the glyph's centre is half of it before
    const spacing = parseFloat(mark.letterSpacing) || 0;
    const scale = markSize / parseFloat(font.fontSize);

    initials.forEach((b, i) => {
      const rest = rests[i];
      if (!rest) return;
      const to = b.getBoundingClientRect();
      range.setStart(text, i);
      range.setEnd(text, i + 1);
      const from = centre(range.getBoundingClientRect());
      from.x -= spacing / 2;
      const at = centre(to);
      const dx = from.x - at.x;
      const dy = from.y - at.y;
      const delay = i * STAGGER;
      const land = delay + FLIGHT;
      const c = copyOf(text.data.charAt(i), to, font);
      layer.append(c.fly);

      // shows on its letter at lift-off, and is gone the frame the initial takes its place
      run(c.fly, [{ opacity: 1 }, { opacity: 1, offset: 0.999 }, { opacity: 0 }], {
        duration: FLIGHT,
        delay,
        fill: "both",
      });
      run(c.fly, [{ transform: `translateX(${dx}px)` }, { transform: "none" }], {
        duration: FLIGHT,
        delay,
        easing: DRIFT,
        fill: "both",
      });
      run(
        c.fall,
        [
          { transform: `translateY(${dy}px)`, easing: LIFT },
          { transform: `translateY(${dy - HOP}px)`, offset: 0.2, easing: GRAVITY },
          { transform: "none" },
        ],
        { duration: FLIGHT, delay, fill: "both" },
      );
      run(
        c.glyphs,
        [
          { transform: `scale(${scale})` },
          { transform: `scale(${scale * 1.05}) rotate(${(SPIN[i % SPIN.length] ?? 0) / 2}deg)`, offset: 0.2 },
          { transform: "none" },
        ],
        { duration: FLIGHT, delay, easing: EASE, fill: "both" },
      );
      // the wordmark's light letter turns into the bold initial halfway down
      run(c.mark, [{ opacity: 1 }, { opacity: 1, offset: 0.25 }, { opacity: 0, offset: 0.5 }], {
        duration: FLIGHT,
        delay,
        fill: "both",
      });
      run(c.bold, [{ opacity: 0 }, { opacity: 0, offset: 0.25 }, { opacity: 1, offset: 0.5 }], {
        duration: FLIGHT,
        delay,
        fill: "both",
      });

      // the initial: hidden until its copy lands, then a squash on the impact
      const squash = 280;
      const hit = land / (land + squash);
      run(
        b,
        [
          { opacity: 0 },
          { opacity: 0, offset: hit },
          { opacity: 1, transform: "scale(1.08, 0.88)", offset: hit, easing: EASE },
          { opacity: 1, transform: "none" },
        ],
        { duration: land + squash, fill: "forwards" },
      );
      // the rest of the word slides out from behind it
      run(
        rest,
        [
          { opacity: 0, transform: "translateX(-0.3em)" },
          { opacity: 0, offset: 0.15 },
          { opacity: 1, transform: "none" },
        ],
        { duration: 520, delay: land + 40, easing: EASE, fill: "both" },
      );
    });
    void Promise.all(running.map((a) => a.finished)).then(
      () => layer.remove(),
      () => {}, // cancelled by the cleanup
    );
  };

  const timer = window.setTimeout(launch, Math.max(0, LAUNCH_AT - now));
  return () => {
    window.clearTimeout(timer);
    running.forEach((a) => a.cancel());
    layer.remove();
    h1.classList.remove("acro--flying");
  };
}
