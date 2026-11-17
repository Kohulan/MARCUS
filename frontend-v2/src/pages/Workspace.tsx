import { useParams } from "react-router-dom";

// Placeholder: the review and paper views come in later tasks.
export default function Workspace() {
  const { id } = useParams();
  return (
    <main>
      <h1>Paper {id}</h1>
    </main>
  );
}
