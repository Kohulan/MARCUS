import type { ReactNode } from "react";
import caffeine from "../assets/caffeine.svg";
import chromene from "../assets/chromene.svg";
import coumarin from "../assets/coumarin.svg";
import exampleCrop from "../assets/example-crop.png";
import { GlassButton, GlassLink } from "../ui/GlassButton";
import Kbd from "../ui/Kbd";
import Stamp from "../ui/Stamp";
import StateBadge from "../ui/StateBadge";
import Structure from "../ui/Structure";
import { useToast } from "../ui/Toasts";
import { pageMeta, usePageTitle } from "./meta";
import "./landing.css";

// The landing (Persuade mode), top to bottom as the Survey Sheet board draws it: the hero
// sheet, the headline row, three numbered cards, the review preview, how to cite.
//
// Honest example (ruling I12): the hero is labelled "Example page". Marker [01] holds a real
// crop that DECIMER Segmentation cut from page 1 of the synthetic sample paper (synth_015),
// with its recorded bbox (backend-v2/tests/fixtures/v1_decimer.json crops[0]); [02] holds our
// own caffeine drawing in the Reading… state (its bbox is the board's). The page's text is
// the sample paper's own. The steps are that sample paper's (5 pages, 15 structures), "9 / 15"
// a snapshot of a read in progress. The review preview is labelled "Example". No accuracy,
// speed or usage numbers.

export const CITATION_TEXT =
  "Rajan K., Weißenborn V., Lederer L., Zielesny A., Steinbeck C. MARCUS: molecular " +
  "annotation and recognition for curating unravelled structures. Digital Discovery 2025, " +
  "4(11), 3137–3148. https://doi.org/10.1039/d5dd00313j";

const DOI_URL = "https://doi.org/10.1039/d5dd00313j";

/** Router state for /app: the visitor came to upload, so the tool opens the file picker. */
export const OPEN_PICKER = { openPicker: true } as const;

type StepState = "done" | "running" | "todo";
const STEP_WORD: Record<StepState, string> = {
  done: "Done",
  running: "Running",
  todo: "Not started",
};
const STEPS: [StepState, string][] = [
  ["done", "001 Check PDF"],
  ["done", "002 Render 5 pages"],
  ["done", "003 Find structures · 15"],
  ["running", "004 Reading with DECIMER · 9 / 15"],
  ["todo", "005 Look up DOI"],
];

// The sample paper's own text (synth_015 prints the same paragraph on every page), run to fill
// the board's blocks around the two markers: about 7 lines, 3 and 6.
const PAGE_TITLE = "Synthetic paper 0015 structures";
const S1 = "Isolation and structural elucidation.";
const S2 =
  "The crude extract was fractionated by silica gel column chromatography and purified by " +
  "semi-preparative HPLC to give the compounds shown below.";
const S3 = "Structures were assigned by 1D and 2D NMR and HRMS; the numbering follows the text.";
const PAGE_TEXT = [
  `${S1} ${S2} ${S3} ${S1} ${S3}`,
  `${S1} ${S2} ${S3}`,
  `${S1} ${S2} ${S3} ${S2}`,
];

/** Text on the example page (decorative: the hero's label says what the page is). */
function PageText({ text, className }: { text: string; className: string }) {
  return (
    <p className={`xpage__text ${className}`} aria-hidden="true">
      {text}
    </p>
  );
}

function Hero() {
  return (
    <section className="hero" aria-label="Example: a page read by MARCUS">
      <div className="hero__caption">
        <span className="corner" aria-hidden="true">
          +
        </span>
        <p className="mono-label">Sheet 01 · Example page · 300 DPI</p>
        <span className="corner" aria-hidden="true">
          +
        </span>
      </div>
      <div className="ticks hero__ticks" aria-hidden="true" />
      <div className="hero__body">
        <div className="vticks" aria-hidden="true" />
        <div className="hero__field">
          <div className="xpage">
            <div className="xpage__inner">
              <p className="xpage__title" aria-hidden="true">
                {PAGE_TITLE}
              </p>
              <div className="xpage__row">
                <div className="marker marker--found">
                  <img
                    className="marker__img"
                    src={exampleCrop}
                    width={546}
                    height={449}
                    alt="Example: a structure drawing that DECIMER Segmentation cut from page 1 of the sample paper"
                  />
                  <span className="marker__corner marker__corner--start" aria-hidden="true" />
                  <span className="marker__tag marker__tag--charcoal">[01] Structure</span>
                </div>
                <PageText text={PAGE_TEXT[0]!} className="xpage__column" />
              </div>
              <PageText text={PAGE_TEXT[1]!} className="xpage__para" />
              <div className="xpage__row xpage__row--end">
                <PageText text={PAGE_TEXT[2]!} className="xpage__column" />
                <div className="marker marker--reading">
                  <img className="marker__img" src={caffeine} alt="Caffeine, being read" />
                  <svg className="marker__ants" aria-hidden="true" focusable="false">
                    <rect width="100%" height="100%" />
                  </svg>
                  <span className="marker__corner marker__corner--end" aria-hidden="true" />
                  <span className="marker__tag marker__tag--orange">[02] Reading…</span>
                </div>
              </div>
            </div>
          </div>
          <div className="readout hero__bbox">
            <p>BBox [01] X0 967 · Y0 671 · X1 1513 · Y1 1120 px</p>
            <p>BBox [02] X0 1410 · Y0 2010 · X1 2190 · Y1 2400 px</p>
          </div>
          <ol className="readout hero__steps">
            {STEPS.map(([state, label]) => (
              <li key={label} className={`step step--${state}`}>
                <span className="step__mark" aria-hidden="true" />
                <span className="visually-hidden">{`${STEP_WORD[state]}: `}</span>
                {label}
              </li>
            ))}
          </ol>
        </div>
        <div className="vticks" aria-hidden="true" />
      </div>
      <div className="ticks hero__ticks" aria-hidden="true" />
      <div className="hero__caption" aria-hidden="true">
        <span className="corner">+</span>
        <span className="corner">+</span>
      </div>
    </section>
  );
}

function Lead() {
  return (
    <div className="lead">
      <div className="lead__title">
        <h1>Every molecule has a source.</h1>
      </div>
      <div className="lead__text">
        <p>
          MARCUS finds every chemical structure in a PDF, reads it, and helps you check it before
          it goes into COCONUT.
        </p>
        <p className="mono-label lead__facts">
          Open source (MIT) · No login · Files deleted after 30 days
        </p>
      </div>
      <div className="lead__cta glassbed">
        <GlassLink tint="orange" to="/app" state={OPEN_PICKER}>
          Upload a PDF<span aria-hidden="true">→</span>
        </GlassLink>
        <GlassLink tint="clear" to="/app?sample=1">
          Try a sample paper<span aria-hidden="true">→</span>
        </GlassLink>
      </div>
    </div>
  );
}

const CARDS = [
  {
    label: "Find",
    tag: "[01]",
    title: "Every structure on every page",
    line: "DECIMER Segmentation marks each drawing and keeps its page and position.",
  },
  {
    label: "Read",
    tag: "[02]",
    title: "Three engines, side by side",
    line: "DECIMER by default. Compare with MolNexTR and MolScribe.",
  },
  {
    label: "Curate",
    tag: "[03]",
    title: "Checked, then into COCONUT",
    line: "Accept or reject with one key. Send what you accepted.",
  },
];

function How() {
  return (
    <section id="how" className="how" aria-label="What MARCUS does">
      {CARDS.map((card) => (
        <article key={card.tag} className="how__card">
          <p className="mono-label">{card.label}</p>
          <p className="how__tag">{card.tag}</p>
          <h2 className="how__title">{card.title}</h2>
          <p className="how__line">{card.line}</p>
        </article>
      ))}
    </section>
  );
}

/** A glass pill drawn in the illustration: a span, never a control. */
function Pill({ tint, children }: { tint: "green" | "clear"; children: ReactNode }) {
  return <span className={`glass glass--${tint} glass--sm glass--still`}>{children}</span>;
}

/** The review grid as the tool shows it: an illustration, so nothing in it is focusable. */
function Preview() {
  return (
    <section className="preview" aria-label="Example: the review grid">
      <div className="preview__bar">
        <div className="preview__name">
          <p className="mono-label">In the tool · Review</p>
          <p className="preview__title">Example paper</p>
        </div>
        <p className="preview__counts">
          <span className="count">
            <span className="count__dot count__dot--accepted" aria-hidden="true" />9 Accepted
          </span>
          <span className="count">
            <span className="count__dot count__dot--check" aria-hidden="true" />4 To check
          </span>
          <span className="count">
            <span aria-hidden="true">✕ </span>2 Rejected
          </span>
        </p>
        <div className="preview__send glassbed">
          <Pill tint="green">
            Send 9 to COCONUT<span aria-hidden="true">→</span>
          </Pill>
        </div>
      </div>

      <div className="preview__grid">
        <div className="pcard">
          <p className="pcard__tags">
            <span>[03] · Page 2</span>
            <StateBadge state="accepted" />
          </p>
          <div className="pcard__draw">
            <Structure src={caffeine} alt="Caffeine" />
          </div>
          <code className="pcard__smiles">Cn1cnc2c1c(=O)n(C)c(=O)n2C</code>
          <span className="pcard__stamp">
            <Stamp state="accepted" />
          </span>
        </div>

        <div className="pcard pcard--check">
          <p className="pcard__tags">
            <span>[04] · Page 2</span>
            <StateBadge state="to-check" />
          </p>
          <div className="pcard__draw">
            <Structure src={coumarin} alt="Coumarin" />
          </div>
          <code className="pcard__smiles">O=c1ccc2ccccc2o1</code>
          <p className="pcard__note pcard__note--check">DECIMER and MolNexTR differ</p>
          <p className="pcard__actions">
            <Pill tint="green">
              Accept <Kbd>A</Kbd>
            </Pill>
            <Pill tint="clear">
              Reject <Kbd>R</Kbd>
            </Pill>
            <Pill tint="clear">
              Compare <Kbd>C</Kbd>
            </Pill>
          </p>
        </div>

        <div className="pcard">
          <p className="pcard__tags">
            <span>[07] · Page 4</span>
            <StateBadge state="rejected" />
          </p>
          <div className="pcard__draw">
            <Structure src={chromene} alt="2H-Chromene, crossed out" crossed />
          </div>
          <code className="pcard__smiles pcard__smiles--struck">C1=Cc2ccccc2OC1</code>
          <p className="pcard__note">Note: a figure label, not a compound</p>
        </div>

        <div className="pcard pcard--failed hatch">
          <p className="pcard__tags">
            <span>Page 5</span>
            <StateBadge state="failed" />
          </p>
          <div className="pcard__reason">
            <p className="pcard__reason-title">Page 5 could not be read</p>
            <p>It took too long.</p>
          </div>
          <p className="pcard__actions">
            <Pill tint="clear">
              Retry this page<span aria-hidden="true">→</span>
            </Pill>
          </p>
        </div>
      </div>

      <div className="preview__foot">
        <p>Keys · A accept · R reject · E edit · C compare · ← → move · ? help</p>
        <p>Export JSON · CSV · SDF</p>
      </div>
    </section>
  );
}

function Cite() {
  const toast = useToast();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(CITATION_TEXT);
      toast("Citation copied");
    } catch {
      toast("Could not copy", "error");
    }
  };

  return (
    <section id="cite" className="cite" aria-labelledby="cite-heading">
      <div className="cite__label">
        <h2 id="cite-heading" className="cite__heading">
          Cite
        </h2>
      </div>
      <div className="cite__text">
        <p>
          Rajan K., Weißenborn V., Lederer L., Zielesny A., Steinbeck C. MARCUS: molecular
          annotation and recognition for curating unravelled structures. <i>Digital Discovery</i>{" "}
          2025, 4(11), 3137–3148. <a href={DOI_URL}>{DOI_URL}</a>
        </p>
      </div>
      <div className="cite__copy glassbed">
        <GlassButton tint="clear" size="sm" onClick={() => void copy()}>
          Copy<span className="visually-hidden"> citation</span>
        </GlassButton>
      </div>
    </section>
  );
}

export default function Landing() {
  usePageTitle(pageMeta("/").title);
  return (
    <main className="landing">
      <Hero />
      <Lead />
      <How />
      <Preview />
      <Cite />
    </main>
  );
}
