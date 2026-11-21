import { errorText } from "../api/client";
import { GlassButton, GlassLink } from "./GlassButton";
import "./ui.css";

/**
 * The one page for a paper or image the API answers 404 for: deleted, expired, or owned by
 * another browser (the API does not say which, and neither does this page). Never a spinner.
 */
export default function GonePage({ noun }: { noun: "paper" | "image" }) {
  return (
    <main className="gone">
      <div className="gone__sheet">
        <span className="corner gone__corner" aria-hidden="true">
          +
        </span>
        <h1 className="gone__title">{`This ${noun} is not here any more.`}</h1>
        <p className="gone__why">
          It was deleted, it expired after 30 days, or it was opened in another browser.
        </p>
        <div className="gone__bed glassbed">
          <GlassLink tint="clear" to="/app">
            Your papers
          </GlassLink>
        </div>
      </div>
    </main>
  );
}

/** A paper or image that could not be opened (not gone): the reason and Try again. */
export function OpenFailed({
  noun,
  error,
  onRetry,
}: {
  noun: "paper" | "image";
  error: unknown;
  onRetry: () => void;
}) {
  return (
    <main className="gone">
      <div className="gone__sheet">
        <h1 className="gone__title">{`This ${noun} could not be opened.`}</h1>
        <p className="gone__why">{errorText(error)}</p>
        <div className="gone__bed glassbed">
          <GlassButton tint="clear" onClick={onRetry}>
            Try again
          </GlassButton>
        </div>
      </div>
    </main>
  );
}
