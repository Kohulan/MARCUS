import { faCopyright } from "@fortawesome/free-regular-svg-icons";
import { faMugHot, faScaleBalanced, faShieldHalved } from "@fortawesome/free-solid-svg-icons";
import type { ReactNode } from "react";
import { Link, matchPath, useLocation } from "react-router-dom";
import Icon from "./Icon";
import "./ui.css";

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

/** A link that opens in a new tab, and says so to a screen reader. */
function Away({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
      <span className="visually-hidden"> (opens in a new tab)</span>
    </a>
  );
}

/**
 * Three porcelain bubbles: the copyright far left, the credit in the middle, the two small
 * links far right. Sticky at the bottom of the window from 1024 px, in the flow after the
 * page (so at the end of a page it rests below the content); below 1024 px they stack.
 */
function BubbleFooter() {
  return (
    <footer className="site-footer site-footer--bubbles">
      <p className="site-footer__copy">
        <Icon icon={faCopyright} />
        <span className="visually-hidden">Copyright </span>2026 MARCUS
      </p>
      <p className="site-footer__credit">
        Built with <Icon icon={faMugHot} className="fa-mug" />
        <span className="visually-hidden">coffee</span> by <Away href="https://kohulanr.com">Kohulan.R</Away> at the{" "}
        <Away href="https://github.com/Steinbeck-Lab">Steinbeck Lab</Away>,{" "}
        <Away href="https://www.uni-jena.de">Friedrich Schiller University Jena</Away>
      </p>
      <nav aria-label="Footer" className="site-footer__nav">
        <Link to="/disclaimer">
          <Icon icon={faScaleBalanced} />
          Disclaimer
        </Link>
        <span className="site-footer__dot" aria-hidden="true">
          ·
        </span>
        <Link to="/privacy">
          <Icon icon={faShieldHalved} />
          Privacy
        </Link>
      </nav>
    </footer>
  );
}

export default function Footer() {
  return isWorkspace(useLocation().pathname) ? <ThinFooter /> : <BubbleFooter />;
}
