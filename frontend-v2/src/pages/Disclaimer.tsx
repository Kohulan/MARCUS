import { Link } from "react-router-dom";
import { InfoSection, InfoSheet } from "./InfoSheet";
import { pageMeta } from "./meta";

// Carried over from v1 (frontend/src/views/DisclaimerPage.vue), shortened, updated for v2.

export default function Disclaimer() {
  return (
    <InfoSheet
      title="Disclaimer"
      docTitle={pageMeta("/disclaimer").title}
      lede="MARCUS is a research tool. Check every structure before you use it."
      updated="18 November 2026"
    >
      <InfoSection title="A research tool">
        <p>
          MARCUS finds, reads and helps you annotate chemical structures in scientific papers,
          with a focus on natural products. It is under active development: treat it as a
          research prototype, not a production service.
        </p>
      </InfoSection>

      <InfoSection title="Check the results">
        <p>
          Reading structures from a paper automatically is hard, and MARCUS makes mistakes.
          Have a qualified person check every result before it goes into research, a
          publication or a database. How well it reads depends on:
        </p>
        <ul>
          <li>the image quality of the document</li>
          <li>how complex the structures are</li>
          <li>the layout of the publication</li>
          <li>hand-drawn or printed structures</li>
        </ul>
      </InfoSection>

      <InfoSection title="Your files">
        <p>
          Uploads are stored on our servers to process them and are deleted after 30 days.
          Take care before you upload confidential or unpublished work. You are responsible for
          having the right to use the papers you upload. See <Link to="/privacy">Privacy</Link>.
        </p>
      </InfoSection>

      <InfoSection title="Licence and citation">
        <p>
          MARCUS is released under the MIT licence, as is, without warranty. The models and
          parts it uses (DECIMER, MolParser, MolScribe, Docling) have their own licences.
          The MolParser model weights are CC BY-NC-SA 4.0, for non-commercial use only. If you
          use MARCUS in your research, please cite it (<Link to="/about#cite">How to cite</Link>)
          and the tools it builds on (<Link to="/about">About</Link>).
        </p>
        <p>
          Icons: Font Awesome Free 6.7.2 by Fonticons, Inc., under{" "}
          <a href="https://fontawesome.com/license/free">CC BY 4.0</a>.
        </p>
      </InfoSection>

      <InfoSection title="Contact">
        <p>
          Kohulan Rajan, Cheminformatics and Computational Metabolomics, Friedrich Schiller
          University Jena, Germany:{" "}
          <a href="mailto:kohulan.rajan@uni-jena.de">kohulan.rajan@uni-jena.de</a>
        </p>
      </InfoSection>
    </InfoSheet>
  );
}
