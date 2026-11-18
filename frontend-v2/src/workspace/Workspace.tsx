import { useParams } from "react-router-dom";
import { usePageTitle } from "../pages/meta";

// Placeholder: the review and paper views come in later tasks.
export default function Workspace() {
  const { id } = useParams();
  usePageTitle("Paper · MARCUS");
  return (
    <main>
      <h1>Paper {id}</h1>
    </main>
  );
}
