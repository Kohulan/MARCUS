import { faArrowRight } from "@fortawesome/free-solid-svg-icons";
import { useEffect, useRef, useState } from "react";
import Beams from "../ui/Beams";
import { isFirstScreen } from "../ui/firstScreen";
import { GlassLink } from "../ui/GlassButton";
import Icon from "../ui/Icon";
import { mediaMatches } from "../ui/motion";
import { flyInitials } from "./flight";
import { pageMeta, usePageTitle } from "./meta";
import HistoryLink from "./HistoryLink";
import RingDrop from "./RingDrop";
import "./landing.css";

// The landing: a single screen of two cells. Left, the name spelled out as
// an acrostic and the one sentence; right, the benzene-ring drop zone and the sample paper.
// Soft beams of light rise behind both. How it works, the review grid and the citation are on About.

const NAME = "Molecular Annotation and Recognition for Curating Unravelled Structures";

/**
 * The first screen plays once per page load (landing.css, "The first screen"): the sheet's
 * lines draw themselves, the ring is built from its six bonds, and the initials are copied out
 * of the header's wordmark and fall into place (flight.ts). When the landing is the page the
 * load opened on, the header and footer arrive first ("entry"); after a click from another
 * page they are already there ("intro"). A later visit in the same tab shows it all at rest.
 * Lines, ring, header and footer are CSS from the first paint; only the flight needs the
 * script, and without it the CSS shows the name. False on the server and while hydrating.
 */
let assembled = false;

type Intro = "entry" | "intro" | null;

/**
 * One line of the acrostic: the bold green initial, then the rest of the word. `n` (1 to 6)
 * is the line's place in the assembly (.acro__line--n).
 */
function Line({
  n,
  initial,
  rest,
  link,
}: {
  n: number;
  initial: string;
  rest: string;
  link?: string;
}) {
  return (
    <span className={`acro__line acro__line--${n}`}>
      <b>{initial}</b>
      <span className="acro__rest">
        {rest}
        {link && (
          <>
            {" "}
            <span className="acro__link">{link}</span>
          </>
        )}
      </span>
    </span>
  );
}

export default function Landing() {
  usePageTitle(pageMeta("/").title);
  // when the first screen's CSS starts: the time origin for the page the load opened on,
  // this mount for a landing reached by a click
  const [{ intro, origin }] = useState<{ intro: Intro; origin: number }>(() =>
    assembled
      ? { intro: null, origin: 0 }
      : isFirstScreen()
        ? { intro: "entry", origin: 0 }
        : { intro: "intro", origin: performance.now() },
  );
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    assembled = true;
  }, []);
  useEffect(() => {
    if (!intro || !title.current || mediaMatches("(prefers-reduced-motion: reduce)")) return;
    return flyInitials(title.current, origin);
  }, [intro, origin]);
  const assemble = intro !== null;
  return (
    <main className="home">
      {intro && (
        // the sheet's frame, drawn over its border while the lines draw themselves
        <span className="rules" aria-hidden="true">
          <span className="rule rule--top" />
          <span className="rule rule--right" />
          <span className="rule rule--bottom" />
          <span className="rule rule--left" />
        </span>
      )}
      <section
        className={
          intro === "entry"
            ? "landing landing--intro landing--entry"
            : intro
              ? "landing landing--intro"
              : "landing"
        }
        aria-label="MARCUS"
      >
        <Beams />
        <div className="lead">
          <div className="lead__title">
            {/* Drawn as an acrostic, read as the plain name: a screen reader would split
                "M olecular" at each bold initial. */}
            <h1 ref={title} className={assemble ? "acro acro--assemble" : "acro"}>
              <span aria-hidden="true">
                {/* the spaces keep a copied selection readable: "Molecular Annotation and …" */}
                <Line n={1} initial="M" rest="olecular" />{" "}
                <Line n={2} initial="A" rest="nnotation" link="and" />{" "}
                <Line n={3} initial="R" rest="ecognition" link="for" />{" "}
                <Line n={4} initial="C" rest="urating" />{" "}
                <Line n={5} initial="U" rest="nravelled" />{" "}
                <Line n={6} initial="S" rest="tructures" />
              </span>
              <span className="visually-hidden">{NAME}</span>
            </h1>
          </div>
          <div className="lead__text">
            <p>
              MARCUS finds every chemical structure in a PDF, reads it, and helps you check it
              before it goes into COCONUT.
            </p>
            <p className="mono-label lead__facts">
              Open source (MIT) · No login · Files deleted after 30 days
            </p>
          </div>
        </div>

        <div className="act">
          <span className="corner act__corner" aria-hidden="true">
            +
          </span>
          <span className="corner act__corner" aria-hidden="true">
            +
          </span>
          <span className="corner act__corner" aria-hidden="true">
            +
          </span>
          <span className="corner act__corner" aria-hidden="true">
            +
          </span>
          <RingDrop />
          <HistoryLink />
          <p className="act__sample">
            <GlassLink tint="orange" to="/app?sample=1">
              Try a sample paper
              <Icon icon={faArrowRight} className="fa--after" />
            </GlassLink>
          </p>
        </div>
      </section>
    </main>
  );
}
