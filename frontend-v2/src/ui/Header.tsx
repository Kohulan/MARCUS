import { Link } from "react-router-dom";
import "./ui.css";

/** The sheet's title row: the mark, then hairline nav cells, the last one into the tool. */
export default function Header() {
  return (
    <header className="site-header">
      <Link to="/" className="site-header__mark">
        <img src="/logo.png" alt="" width="36" height="36" />
        <span className="site-header__word">MARCUS</span>
      </Link>
      <nav aria-label="Main" className="site-nav">
        <a className="site-nav__cell" href="/#how">
          How it works
        </a>
        <a className="site-nav__cell" href="/#cite">
          Cite
        </a>
        <a className="site-nav__cell" href="https://github.com/Kohulan/MARCUS">
          GitHub
        </a>
        <Link className="site-nav__cell site-nav__cell--tool" to="/app">
          Open the tool<span aria-hidden="true"> →</span>
        </Link>
      </nav>
    </header>
  );
}
