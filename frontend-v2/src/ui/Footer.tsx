import { Fragment } from "react";
import { Link, matchPath, useLocation } from "react-router-dom";
import "./ui.css";

const LINKS: { label: string; to: string; internal?: boolean }[] = [
  { label: "About", to: "/about", internal: true },
  { label: "Disclaimer", to: "/disclaimer", internal: true },
  { label: "GitHub", to: "https://github.com/Kohulan/MARCUS" },
  { label: "MIT License", to: "https://opensource.org/license/MIT" },
  { label: "Privacy", to: "/privacy", internal: true },
];

/** The review workspace (focus mode and the paper view included) keeps the thin line. */
function isWorkspace(pathname: string): boolean {
  return matchPath("/app/papers/:id", pathname) !== null;
}

/** The workspace's thin mono line: who makes it, where it is published, the small links. */
function ThinFooter() {
  return (
    <footer className="site-footer site-footer--thin">
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

/** One band of three ruled cells: copyright, credit, links. Stacks on a phone. */
function BandFooter() {
  return (
    <footer className="site-footer site-footer--band">
      <p className="site-footer__cell site-footer__copy">© 2025 MARCUS</p>
      <p className="site-footer__cell site-footer__credit">
        by <a href="https://kohulanr.com">Kohulan Rajan</a> @{" "}
        <a href="https://github.com/Steinbeck-Lab">Steinbeck Lab</a>
      </p>
      <nav aria-label="Footer" className="site-footer__cell site-footer__nav">
        {LINKS.map(({ label, to, internal }, i) => (
          <Fragment key={label}>
            {i > 0 && (
              <span className="site-footer__dot" aria-hidden="true">
                ·
              </span>
            )}
            {internal ? <Link to={to}>{label}</Link> : <a href={to}>{label}</a>}
          </Fragment>
        ))}
      </nav>
    </footer>
  );
}

export default function Footer() {
  return isWorkspace(useLocation().pathname) ? <ThinFooter /> : <BandFooter />;
}
