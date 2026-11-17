import { useParams } from "react-router-dom";

// Placeholder: the single image result comes in a later task.
export default function ImageResult() {
  return (
    <main>
      <h1>Image {useParams().id}</h1>
    </main>
  );
}
