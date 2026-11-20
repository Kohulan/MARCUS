import { faArrowRight } from "@fortawesome/free-solid-svg-icons";
import { useEffect } from "react";
import Beams from "../ui/Beams";
import { GlassLink } from "../ui/GlassButton";
import Icon from "../ui/Icon";
import { pageMeta, usePageTitle } from "./meta";
import RingDrop from "./RingDrop";
import "./landing.css";

// The landing: a single screen of two cells. Left, the name spelled out as
// an acrostic and the one sentence; right, the benzene-ring drop zone and the sample paper.
// Soft beams of light rise behind both. How it works, the review grid and the citation are on About.

const NAME = "Molecular Annotation and Recognition for Curating Unravelled Structures";

/**
 * The name assembles once per page load (landing.css, .acro--assemble): pure CSS from the
 * first paint, so the pre-rendered page needs no script for it. A later visit in the same tab
 * (back from /about) shows the name at rest. False on the server and while hydrating.
 */
let assembled = false;

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
  const assemble = !assembled;
  useEffect(() => {
    assembled = true;
  }, []);
  return (
    <main className="home">
      <section className="landing" aria-label="MARCUS">
        <Beams />
        <div className="lead">
          <div className="lead__title">
            {/* Drawn as an acrostic, read as the plain name: a screen reader would split
                "M olecular" at each bold initial. */}
            <h1 className={assemble ? "acro acro--assemble" : "acro"}>
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
