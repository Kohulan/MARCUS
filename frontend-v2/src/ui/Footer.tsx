import { Link } from "react-router-dom";
import "./ui.css";

/** One mono line: who makes it, where it is published, and the small links. */
export default function Footer() {
  return (
    <footer className="site-footer">
      <p className="site-footer__line">
        <span>MARCUS · Friedrich Schiller University Jena · NFDI4Chem</span>
        <a href="https://doi.org/10.1039/d5dd00313j">
          Digital Discovery 2025 · DOI 10.1039/d5dd00313j
        </a>
      </p>
      <nav aria-label="Footer" className="site-footer__links">
        <Link to="/about">About</Link>
        <Link to="/privacy">Privacy</Link>
        <Link to="/disclaimer">Disclaimer</Link>
        <a href="https://decimer.ai">DECIMER</a>
        <a href="https://coconut.naturalproducts.net">COCONUT</a>
        <a href="https://github.com/Kohulan/MARCUS">GitHub</a>
      </nav>
    </footer>
  );
}
