import { Link } from "react-router-dom";

// Placeholder: the Field Sheet landing is built in a later task.
export default function Landing() {
  return (
    <main>
      <p className="wordmark">MARCUS</p>
      <h1>Every molecule has a source.</h1>
      <p>
        Upload a PDF. MARCUS finds every chemical structure, reads it with DECIMER, MolNexTR or
        MolScribe, keeps its page and text beside it, and helps you check it before it goes into
        COCONUT.
      </p>
      <p>
        <Link to="/app">Open the tool</Link>
      </p>
    </main>
  );
}
