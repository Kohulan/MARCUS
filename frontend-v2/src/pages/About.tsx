import type { ReactNode } from "react";
import caffeine from "../assets/caffeine.svg";
import chromene from "../assets/chromene.svg";
import coumarin from "../assets/coumarin.svg";
import exampleCrop from "../assets/example-crop.png";
import { GlassButton } from "../ui/GlassButton";
import Stamp from "../ui/Stamp";
import StateBadge from "../ui/StateBadge";
import Structure from "../ui/Structure";
import { useToast } from "../ui/Toasts";
import { InfoSection, InfoSheet } from "./InfoSheet";
import { pageMeta } from "./meta";

// Carried over from v1 (frontend/src/views/AboutPage.vue), shortened, updated for v2. How it
// works, the example review grid and the citation moved here from the landing (2026-11-19).
//
// Honest examples (ruling I12): the steps are the synthetic sample paper's (synth_015: 5 pages,
// 15 structures), "9 / 15" a snapshot of a read in progress; the crop is a real one that
// DECIMER Segmentation cut from its page 1 (backend-v2/tests/fixtures/v1_decimer.json
// crops[0]); the review grid is labelled "Example" and drawn with our own structures. No
// accuracy, speed or usage numbers.

const CITATION_TEXT =
  "Rajan K., Weißenborn V., Lederer L., Zielesny A., Steinbeck C. MARCUS: molecular " +
  "annotation and recognition for curating unravelled structures. Digital Discovery 2025, " +
  "4(11), 3137–3148. https://doi.org/10.1039/d5dd00313j";

const DOI_URL = "https://doi.org/10.1039/d5dd00313j";

type Ref = { title: string; authors: string; where: string; doi: string };

const REFS: Ref[] = [
  {
    title:
      "DECIMER.ai: an open platform for automated optical chemical structure identification, segmentation and recognition in scientific publications",
    authors: "Rajan K., Brinkhaus H.O., Agea M.I., Zielesny A., Steinbeck C.",
    where: "Nat Commun 14, 5045 (2023)",
    doi: "https://doi.org/10.1038/s41467-023-40648-7",
  },
  {
    title:
      "Advancements in hand-drawn chemical structure recognition through an enhanced DECIMER architecture",
    authors: "Rajan K., Brinkhaus H.O., Zielesny A., Steinbeck C.",
    where: "J Cheminform 16, 78 (2024)",
    doi: "https://doi.org/10.1186/s13321-024-00901-5",
  },
  {
    title:
      "DECIMER-Segmentation: Automated extraction of chemical structure depictions from scientific literature",
    authors: "Rajan K., Brinkhaus H.O., Sorokina M., et al.",
    where: "J Cheminform 13, 20 (2021)",
    doi: "https://doi.org/10.1186/s13321-021-00508-0",
  },
  {
    title: "MolNexTR: a generalized deep learning model for molecular image recognition",
    authors: "Chen Y., Leung C.T., Huang Y., et al.",
    where: "J Cheminform 16, 141 (2024)",
    doi: "https://doi.org/10.1186/s13321-024-00926-w",
  },
  {
    title: "MolScribe: Robust molecular structure recognition with image-to-graph generation",
    authors: "Qian Y., Guo J., Tu Z., Li Z., Coley C.W., Barzilay R.",
    where: "J Chem Inf Model 63(7), 1925–1934 (2023)",
    doi: "https://doi.org/10.1021/acs.jcim.2c01480",
  },
  {
    title: "Docling Technical Report",
    authors: "Auer C., Lysak M., Nassar A., Dolfi M., Livathinos N., Vagenas P., et al.",
    where: "arXiv 2408.09869 (2024)",
    doi: "https://arxiv.org/abs/2408.09869",
  },
  {
    title:
      "COCONUT 2.0: a comprehensive overhaul and curation of the collection of open natural products database",
    authors:
      "Chandrasekhar V., Rajan K., Kanakam S.R.S., Sharma N., Weißenborn V., Schaub J., Steinbeck C.",
    where: "Nucleic Acids Research, gkae1063 (2024)",
    doi: "https://doi.org/10.1093/nar/gkae1063",
  },
];

const STEPS = [
  {
    tag: "[01]",
    title: "Every structure on every page",
    line: "DECIMER Segmentation marks each drawing and keeps its page and position.",
  },
  {
    tag: "[02]",
    title: "Four engines, side by side",
    line: "DECIMER by default. Compare with MolNexTR, MolScribe and DECIMER hand-drawn.",
  },
  {
    tag: "[03]",
    title: "Checked, then into COCONUT",
    line: "Accept or reject with one key. Send what you accepted.",
  },
];

type RunState = "done" | "running" | "todo";
const RUN_WORD: Record<RunState, string> = {
  done: "Done",
  running: "Running",
  todo: "Not started",
};
const RUN: [RunState, string][] = [
  ["done", "001 Check PDF"],
  ["done", "002 Render 5 pages"],
  ["done", "003 Find structures · 15"],
  ["running", "004 Reading with DECIMER · 9 / 15"],
  ["todo", "005 Look up DOI"],
];

/** The three steps, then the sample paper's crop and its run, as the tool logs it. */
function How() {
  return (
    <>
      <ol className="steps3">
        {STEPS.map((step) => (
          <li key={step.tag}>
            <span className="steps3__tag" aria-hidden="true">
              {step.tag}
            </span>
            <div>
              <h3>{step.title}</h3>
              <p>{step.line}</p>
            </div>
          </li>
        ))}
      </ol>
      <div className="how-ex">
        <figure className="crop">
          <img
            className="crop__img"
            src={exampleCrop}
            width={546}
            height={449}
            alt="Example: a structure drawing that DECIMER Segmentation cut from page 1 of the sample paper"
          />
          <figcaption className="crop__caption">
            Example crop · DECIMER Segmentation · sample paper, page 1
          </figcaption>
        </figure>
        <div className="runlog">
          <p className="runlog__head">Example paper</p>
          <ol>
            {RUN.map(([state, label]) => (
              <li key={label} className={`step step--${state}`}>
                <span className="step__mark" aria-hidden="true" />
                <span className="visually-hidden">{`${RUN_WORD[state]}: `}</span>
                {label}
              </li>
            ))}
          </ol>
        </div>
      </div>
    </>
  );
}

/** A glass pill drawn in the illustration: a span, never a control. */
function Pill({ tint, children }: { tint: "green" | "clear"; children: ReactNode }) {
  return <span className={`glass glass--${tint} glass--sm glass--still`}>{children}</span>;
}

/** The review grid as the tool shows it: an illustration, so nothing in it is focusable. */
function Preview() {
  return (
    <div className="preview">
      <div className="preview__bar">
        <div className="preview__name">
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
          <p className="pcard__note pcard__note--check">Engines differ</p>
          <p className="pcard__actions">
            <Pill tint="green">Accept</Pill>
            <Pill tint="clear">Reject</Pill>
            <Pill tint="clear">Compare</Pill>
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
        <p>Keys in focus mode · A accept · R reject · E edit · C compare · ← → move · ? help</p>
        <p>Export JSON · CSV · SDF</p>
      </div>
    </div>
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
    <div className="cite">
      <p>
        Rajan K., Weißenborn V., Lederer L., Zielesny A., Steinbeck C. MARCUS: molecular
        annotation and recognition for curating unravelled structures. <i>Digital Discovery</i>{" "}
        2025, 4(11), 3137–3148. <a href={DOI_URL}>{DOI_URL}</a>
      </p>
      <div className="cite__copy glassbed">
        <GlassButton tint="clear" size="sm" onClick={() => void copy()}>
          Copy<span className="visually-hidden"> citation</span>
        </GlassButton>
      </div>
    </div>
  );
}

export default function About() {
  return (
    <InfoSheet
      title="About MARCUS"
      docTitle={pageMeta("/about").title}
      lede="Molecular Annotation and Recognition for Curating Unravelled Structures."
    >
      <InfoSection title="What it does">
        <p>
          MARCUS turns a journal article into checked chemical structures for COCONUT, the open
          natural products database.
        </p>
        <p>
          It is made at the Steinbeck group (Cheminformatics and Computational Metabolomics),
          Friedrich Schiller University Jena, as part of the DECIMER project and NFDI4Chem. It
          runs on the group&apos;s own servers and sends no paper to outside AI services.
        </p>
      </InfoSection>

      <InfoSection title="How it works" id="how">
        <How />
      </InfoSection>

      <InfoSection title="Example: the review grid" id="review" figure>
        <Preview />
      </InfoSection>

      <InfoSection title="Team">
        <dl className="people">
          <div>
            <dt>Kohulan Rajan</dt>
            <dd>Project lead and lead developer</dd>
          </div>
          <div>
            <dt>Christoph Steinbeck</dt>
            <dd>
              Principal investigator. Professor of Analytical Chemistry, Cheminformatics and
              Chemometrics
            </dd>
          </div>
        </dl>
      </InfoSection>

      <InfoSection title="Open source">
        <p>
          MARCUS is free and open source under the MIT licence, with no login. The code, and a
          place to report problems or contribute, is on{" "}
          <a href="https://github.com/Kohulan/MARCUS">GitHub</a>.
        </p>
      </InfoSection>

      <InfoSection title="Cite" id="cite">
        <Cite />
      </InfoSection>

      <InfoSection title="Publications">
        <ol className="refs">
          {REFS.map((ref) => (
            <li key={ref.doi}>
              <p className="refs__title">{ref.title}</p>
              <p className="refs__meta">
                {ref.authors} {ref.where}. <a href={ref.doi}>{ref.doi.replace("https://", "")}</a>
              </p>
            </li>
          ))}
        </ol>
      </InfoSection>
    </InfoSheet>
  );
}
