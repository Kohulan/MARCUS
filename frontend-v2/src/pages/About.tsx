import { InfoSection, InfoSheet } from "./InfoSheet";
import { pageMeta } from "./meta";

// Carried over from v1 (frontend/src/views/AboutPage.vue), shortened, updated for v2.

type Ref = { title: string; authors: string; where: string; doi: string };

const REFS: Ref[] = [
  {
    title: "MARCUS: molecular annotation and recognition for curating unravelled structures",
    authors: "Rajan K., Weißenborn V., Lederer L., Zielesny A., Steinbeck C.",
    where: "Digital Discovery 2025, 4(11), 3137–3148",
    doi: "https://doi.org/10.1039/d5dd00313j",
  },
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

export default function About() {
  return (
    <InfoSheet
      title="About MARCUS"
      docTitle={pageMeta("/about").title}
      lede="Molecular Annotation and Recognition for Curating Unravelled Structures."
    >
      <InfoSection title="What it does">
        <p>
          MARCUS turns a journal article into checked chemical structures. It finds the
          structure drawings on each page, reads each one into a structure with DECIMER,
          MolNexTR or MolScribe, extracts the text, and lets you check, fix, accept or reject
          every structure before you send it to COCONUT, the open natural products database.
        </p>
        <p>
          It is made at the Steinbeck group (Cheminformatics and Computational Metabolomics),
          Friedrich Schiller University Jena, as part of the DECIMER project and NFDI4Chem. It
          runs on the group&apos;s own servers and sends no paper to outside AI services.
        </p>
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
              Chemometrics, Friedrich Schiller University Jena
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
