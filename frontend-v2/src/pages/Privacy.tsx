import { InfoSection, InfoSheet } from "./InfoSheet";
import { pageMeta } from "./meta";

// Carried over from v1 (frontend/src/views/PrivacyPolicyPage.vue), rewritten for v2: no
// accounts, files deleted after 30 days, Matomo as the only tracker, upload limit 20 MB.

export default function Privacy() {
  return (
    <InfoSheet
      title="Privacy"
      docTitle={pageMeta("/privacy").title}
      lede="What MARCUS keeps, for how long, and who sees it."
      updated="18 November 2026"
    >
      <InfoSection title="What you upload">
        <p>
          A PDF or one structure image, max 20 MB. To read it, MARCUS stores the file, the page
          images, the structure crops, the extracted text, the structures it found and your
          decisions on them, on the servers of Friedrich Schiller University Jena.
        </p>
        <ul>
          <li>Everything from one upload is deleted 30 days after the upload.</li>
          <li>Deleting a paper in the tool removes it for you at once.</li>
          <li>Your files are not sent to outside AI services and not shared with others.</li>
          <li>
            To show the paper&apos;s title, the server looks up its DOI at Crossref or DataCite;
            only the DOI is sent.
          </li>
        </ul>
      </InfoSection>

      <InfoSection title="No login">
        <p>
          There are no accounts. Your browser gets a random key in a cookie (marcus_owner) that
          ties your papers to it; the server keeps only a hash of the key. In another browser,
          or after you clear your cookies, those papers cannot be opened again.
        </p>
        <p>
          When a browser first gets its key, the server records the IP address it came from,
          to limit how many new keys one address can get per hour. This IP address is deleted
          after 30 days. The address is also kept with a paper while it is being processed.
          The web server also keeps
          standard access logs (IP address, time, address of the request) to run and protect
          the service.
        </p>
      </InfoSection>

      <InfoSection title="Analytics">
        <p>
          MARCUS counts visits with Matomo, run by NFDI4Chem at matomo.nfdi4chem.de. It is the
          only tracker; there are no ads. Matomo records which page was opened, your browser
          and its settings, and may set its own cookies. For the tool it records only the kind
          of page (for example “a paper”), never which paper.
        </p>
      </InfoSection>

      <InfoSection title="COCONUT and PubChem">
        <p>
          When you send structures to COCONUT, your browser sends them straight to COCONUT
          with your COCONUT login. MARCUS keeps that login only in the open browser tab and
          never sends it to its own server. Looking a structure up in PubChem or COCONUT sends
          that structure from your browser to that service. Opening a paper with a DOI asks
          COCONUT how many structures it already has for that DOI.
        </p>
      </InfoSection>

      <InfoSection title="Your rights">
        <p>
          Under the GDPR you can ask what we hold about you, and have it corrected or deleted.
          Write to Prof. Dr. Christoph Steinbeck, Friedrich Schiller University Jena,{" "}
          <a href="mailto:christoph.steinbeck@uni-jena.de">christoph.steinbeck@uni-jena.de</a>.
          The code that does all of this is open on{" "}
          <a href="https://github.com/Kohulan/MARCUS">GitHub</a>.
        </p>
      </InfoSection>
    </InfoSheet>
  );
}
