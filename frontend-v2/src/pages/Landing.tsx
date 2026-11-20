import { faArrowRight } from "@fortawesome/free-solid-svg-icons";
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

/** One line of the acrostic: the bold green initial, then the rest of the word. */
function Line({ initial, rest, link }: { initial: string; rest: string; link?: string }) {
  return (
    <span className="acro__line">
      <b>{initial}</b>
      {rest}
      {link && (
        <>
          {" "}
          <span className="acro__link">{link}</span>
        </>
      )}
    </span>
  );
}

export default function Landing() {
  usePageTitle(pageMeta("/").title);
  return (
    <main className="home">
      <section className="landing" aria-label="MARCUS">
        <Beams />
        <div className="lead">
          <div className="lead__title">
            {/* Drawn as an acrostic, read as the plain name: a screen reader would split
                "M olecular" at each bold initial. */}
            <h1 className="acro">
              <span aria-hidden="true">
                {/* the spaces keep a copied selection readable: "Molecular Annotation and …" */}
                <Line initial="M" rest="olecular" />{" "}
                <Line initial="A" rest="nnotation" link="and" />{" "}
                <Line initial="R" rest="ecognition" link="for" />{" "}
                <Line initial="C" rest="urating" />{" "}
                <Line initial="U" rest="nravelled" />{" "}
                <Line initial="S" rest="tructures" />
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
