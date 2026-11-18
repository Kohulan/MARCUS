import { Link } from "react-router-dom";
import { InfoSection, InfoSheet } from "./InfoSheet";
import { pageMeta } from "./meta";

export default function NotFound() {
  return (
    <InfoSheet
      title="Page not found"
      docTitle={pageMeta("/__marcus_not_found__").title}
      lede="This page does not exist."
    >
      <InfoSection title="Where to go">
        <p>
          <Link to="/">Go to the start page</Link>
        </p>
      </InfoSection>
    </InfoSheet>
  );
}
