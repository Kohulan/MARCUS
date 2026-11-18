import { GlassLink } from "../ui/GlassButton";
import "./workspace.css";

/**
 * The one page for a paper the API answers 404 for: deleted, expired, or owned by another
 * browser (the API does not say which, and neither does this page). Never a spinner.
 */
export default function GonePage() {
  return (
    <main className="ws-gone">
      <div className="ws-gone__sheet">
        <span className="corner ws-gone__corner" aria-hidden="true">
          +
        </span>
        <h1 className="ws-gone__title">This paper is not here any more.</h1>
        <p className="ws-gone__why">
          It was deleted, it expired after 30 days, or it was opened in another browser.
        </p>
        <div className="ws-gone__bed glassbed">
          <GlassLink tint="clear" to="/app">
            Your papers
          </GlassLink>
        </div>
      </div>
    </main>
  );
}
