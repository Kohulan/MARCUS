// What COCONUT answered, per structure: the created report id, or the error as text.
import { GlassButton } from "../ui/GlassButton";
import { structureTag } from "../ui/tag";
import type { SubmitResult, SubmitStructure } from "./types";
import "./coconut.css";

type SubmitResultsProps = {
  /** The structures that were sent, in order. */
  structures: SubmitStructure[];
  results: SubmitResult[];
  onBack: () => void;
  onClose: () => void;
};

export default function SubmitResults({ structures, results, onBack, onClose }: SubmitResultsProps) {
  const bySegment = new Map(results.map((r) => [r.segmentId, r]));
  const sent = results.filter((r) => r.ok).length;
  const failed = results.length - sent;

  return (
    <section className="coconut-results" aria-labelledby="coconut-results-title">
      <header className="coconut-results__head">
        <h3 id="coconut-results-title" className="coconut-results__title">
          {failed === 0 ? `${sent} sent` : `${sent} sent, ${failed} failed`}
        </h3>
        <div className="coconut-results__actions">
          <GlassButton tint="clear" size="sm" onClick={onBack}>
            Back to form
          </GlassButton>
          <GlassButton tint="clear" size="sm" onClick={onClose}>
            Close
          </GlassButton>
        </div>
      </header>
      <ol className="coconut-rows">
        {structures.map((s) => {
          const r = bySegment.get(s.segmentId);
          const tagId = `coconut-result-${s.segmentId}`;
          return (
            <li
              key={s.segmentId}
              className={r?.ok ? "coconut-row coconut-row--result" : "coconut-row coconut-row--result hatch"}
              aria-labelledby={tagId}
            >
              <span id={tagId} className="coconut-row__tag">
                {structureTag(s.n)}
              </span>
              <code className="coconut-row__smiles" title={s.smiles}>
                {s.smiles}
              </code>
              {r?.ok ? (
                <span className="coconut-row__ok">{r.reportId ? `Report ${r.reportId}` : "Sent"}</span>
              ) : (
                <span className="coconut-row__failed">
                  <span className="coconut-row__failtag">Failed</span>
                  <span className="coconut-row__error">{r ? r.error : "Not sent"}</span>
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
