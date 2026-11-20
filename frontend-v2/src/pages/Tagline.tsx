import { Fragment, useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "../ui/motion";

// The landing's second screen: the tagline in the acrostic's voice, lit word by word as it
// scrolls in (skill B11). The words start dimmed (still 3:1, large text) and each comes to
// full tone, in reading order, as the text crosses a line from 88 % to 60 % of the window
// height. One scroll listener, throttled to a frame, only while the text is on screen; a
// word once lit stays lit. Pre-rendered, without IntersectionObserver, and under reduced
// motion the text is never dimmed.

const WORDS = ["A", "machine", "finds", "and", "reads", "the", "structures.", "You", "decide", "which", "ones", "are", "right."];
const YOU = WORDS.indexOf("You");

export default function Tagline() {
  const reduce = usePrefersReducedMotion();
  const textRef = useRef<HTMLParagraphElement>(null);
  const [armed, setArmed] = useState(false);
  const [lit, setLit] = useState(0);

  useEffect(() => {
    const el = textRef.current;
    if (!el || reduce || typeof IntersectionObserver !== "function") {
      setArmed(false);
      return;
    }
    let shown = 0;
    let queued = false;
    let frame = 0;
    let listening = false;

    const measure = () => {
      queued = false;
      const box = el.getBoundingClientRect();
      const vh = window.innerHeight;
      const start = vh * 0.88; // the first word lights here
      const end = vh * 0.6; // the last word by here
      let p = (start - box.top) / (start - end + box.height);
      const doc = document.documentElement;
      if (window.scrollY + vh >= doc.scrollHeight - 2 && box.top < vh) p = 1; // the page's end
      const n = Math.ceil(Math.max(0, Math.min(1, p)) * WORDS.length);
      if (n > shown) {
        shown = n;
        setLit(n);
      }
      if (shown >= WORDS.length) stop();
    };
    const onScroll = () => {
      if (queued) return;
      queued = true;
      frame = window.requestAnimationFrame(measure);
    };
    const listen = (on: boolean) => {
      if (on === listening) return;
      listening = on;
      if (on) {
        window.addEventListener("scroll", onScroll, { passive: true });
        window.addEventListener("resize", onScroll);
      } else {
        window.removeEventListener("scroll", onScroll);
        window.removeEventListener("resize", onScroll);
      }
    };
    const io = new IntersectionObserver((entries) => {
      const visible = entries.some((e) => e.isIntersecting);
      listen(visible);
      if (visible) measure();
    });
    function stop() {
      listen(false);
      io.disconnect();
    }

    measure(); // words already past the line are lit before the dimming applies
    if (shown < WORDS.length) {
      setArmed(true);
      io.observe(el);
    }
    return () => {
      stop();
      window.cancelAnimationFrame(frame);
    };
  }, [reduce]);

  return (
    <section className={armed ? "tagline is-armed" : "tagline"} aria-label="What MARCUS is for">
      <span className="corner" aria-hidden="true">
        +
      </span>
      <span className="corner" aria-hidden="true">
        +
      </span>
      <p className="tagline__text" ref={textRef}>
        {WORDS.map((word, i) => (
          <Fragment key={i}>
            {i > 0 && " "}
            <span
              className={
                (i === YOU ? "tagline__w tagline__w--you" : "tagline__w") +
                (i < lit ? " is-lit" : "")
              }
            >
              {i === YOU ? <b>{word}</b> : word}
            </span>
          </Fragment>
        ))}
      </p>
    </section>
  );
}
