import { useEffect, useRef } from "react";
import { mediaMatches, subscribeMedia } from "./motion";

// Soft sage beams rising slowly on a diagonal behind the landing, pulsing gently. One canvas,
// drawn at a third of its CSS size and blurred in CSS (landing.css .beams), so the device
// pixel ratio never matters and a frame is 14 gradient rects on a small bitmap. A fixed seed
// gives the same picture on every visit. The loop stops while the canvas is off screen or the
// tab is hidden; under reduced motion it draws one still frame. The pre-rendered page carries
// an empty canvas (plain paper) and the beams appear on hydration. Canvas 2D needs no inline
// style, no eval and no worker: CSP-safe.

const COUNT = 14;
const SCALE = 1 / 3;
const SEED = 7;
const REDUCE = "(prefers-reduced-motion: reduce)";

type Beam = {
  x: number;
  y: number;
  w: number;
  len: number;
  angle: number;
  speed: number;
  alpha: number;
  hue: number;
  pulse: number;
  pulseSpeed: number;
};

/** The sky: beams from a seeded generator, re-made at each size. */
function sky(W: number, H: number) {
  let seed = SEED;
  const rnd = () => {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };
  const make = (i: number, fresh: boolean): Beam => ({
    x: ((i + 0.5 + (rnd() - 0.5) * 0.6) / COUNT) * W * 1.3 - W * 0.15,
    y: fresh ? H + rnd() * H * 0.6 : rnd() * H * 1.4,
    w: (26 + rnd() * 54) * SCALE * 3 * (W / 480 > 1 ? 1 : 0.7),
    len: H * 2.2,
    angle: ((-34 + rnd() * 10) * Math.PI) / 180,
    speed: 0.12 + rnd() * 0.22,
    alpha: 0.07 + rnd() * 0.07,
    hue: 132 + rnd() * 26,
    pulse: rnd() * Math.PI * 2,
    pulseSpeed: 0.006 + rnd() * 0.008,
  });
  const beams = Array.from({ length: COUNT }, (_, i) => make(i, false));
  return { beams, make };
}

function draw(ctx: CanvasRenderingContext2D, W: number, H: number, s: ReturnType<typeof sky>, move: boolean) {
  ctx.clearRect(0, 0, W, H);
  s.beams.forEach((beam, i) => {
    let b = beam;
    if (move) {
      b.y -= b.speed;
      b.pulse += b.pulseSpeed;
      if (b.y + b.len < -H * 0.3) b = s.beams[i] = s.make(i, true);
    }
    const a = b.alpha * (0.8 + Math.sin(b.pulse) * 0.2);
    const c = `hsla(${b.hue.toFixed(0)},34%,46%,`;
    ctx.save();
    ctx.translate(b.x, b.y);
    ctx.rotate(b.angle);
    const g = ctx.createLinearGradient(0, 0, 0, b.len);
    g.addColorStop(0, `${c}0)`);
    g.addColorStop(0.15, `${c}${(a * 0.5).toFixed(3)})`);
    g.addColorStop(0.45, `${c}${a.toFixed(3)})`);
    g.addColorStop(0.75, `${c}${(a * 0.5).toFixed(3)})`);
    g.addColorStop(1, `${c}0)`);
    ctx.fillStyle = g;
    ctx.fillRect(-b.w / 2, 0, b.w, b.len);
    ctx.restore();
  });
}

export default function Beams() {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cv = canvas.current;
    const ctx = cv?.getContext("2d");
    if (!cv || !ctx) return;
    let W = 1;
    let H = 1;
    let s = sky(W, H);
    let raf = 0;
    let onScreen = true;

    const size = () => {
      W = Math.max(1, Math.round(cv.clientWidth * SCALE));
      H = Math.max(1, Math.round(cv.clientHeight * SCALE));
      cv.width = W;
      cv.height = H;
      s = sky(W, H);
    };
    const tick = () => {
      draw(ctx, W, H, s, true);
      raf = window.requestAnimationFrame(tick);
    };
    const run = () => {
      window.cancelAnimationFrame(raf);
      raf = 0;
      if (mediaMatches(REDUCE) === true || document.hidden || !onScreen) {
        draw(ctx, W, H, s, false);
        return;
      }
      raf = window.requestAnimationFrame(tick);
    };
    // A new width re-makes the sky; a height-only change (a phone's URL bar showing or
    // hiding while scrolling) keeps the beams where they are and only resizes the bitmap.
    const resize = () => {
      const w = Math.max(1, Math.round(cv.clientWidth * SCALE));
      const h = Math.max(1, Math.round(cv.clientHeight * SCALE));
      if (w !== W) size();
      else if (h !== H) {
        H = h;
        cv.height = H;
      } else return;
      run();
    };

    size();
    run();
    window.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", run);
    const unsubscribe = subscribeMedia(REDUCE, run);
    const seen =
      typeof IntersectionObserver === "function"
        ? new IntersectionObserver((entries) => {
            onScreen = entries[0]?.isIntersecting ?? true;
            run();
          })
        : null;
    seen?.observe(cv);
    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", run);
      unsubscribe();
      seen?.disconnect();
    };
  }, []);

  return <canvas ref={canvas} className="beams" aria-hidden="true" />;
}
