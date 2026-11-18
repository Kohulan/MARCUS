import { useParams } from "react-router-dom";
import { usePageTitle } from "../pages/meta";

// Placeholder: the single image result comes in a later task.
export default function ImageResult() {
  usePageTitle("Image · MARCUS");
  return (
    <main>
      <h1>Image {useParams().id}</h1>
    </main>
  );
}
