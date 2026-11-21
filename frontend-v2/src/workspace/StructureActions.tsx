// The actions for one structure (focus mode and the card menu): copy and download the
// structure, look it up in PubChem, and hand Edit and Compare back to the caller. Props in,
// callbacks out: it touches no workspace state. Third-party text is rendered as text only.
import { QueryClientContext } from "@tanstack/react-query";
import { useContext, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { loadedDrawing } from "../api/depictions";
import { molfileQuery } from "./useCompare";
import { pubchemBySmiles, type PubchemHit } from "../lookup/pubchem";
import { GlassButton } from "../ui/GlassButton";
import ProgressBar from "../ui/ProgressBar";
import { saveBlob } from "../ui/saveBlob";
import "./structureActions.css";

export type StructureActionsProps = {
  /** The paper's name, for the file names: `<name>-<n>.mol` and `.svg`. */
  name: string;
  n: number;
  /** The shown structure: the curated one, else the chosen prediction's. */
  smiles: string | null;
  /** The curated molfile, then the chosen prediction's, else the SMILES is converted. */
  curatedMolfile?: string | null;
  predictionMolfile?: string | null;
  /** api.depictionUrl(...) of the shown structure (an API URL, fetched on Download). */
  depictionUrl: string | null;
  /**
   * The drawing the caller already holds (the image page's /tools/depict reply), used for
   * Download instead of `depictionUrl`. Never a fetch of a blob: URL: the app CSP has no
   * blob: in connect-src.
   */
  image?: (() => Blob) | undefined;
  onEdit?: (() => void) | undefined;
  onCompare?: (() => void) | undefined;
  /** Injectable for tests; defaults to the shared ["molfile", smiles] query (Compare's). */
  convert?: (smiles: string) => Promise<string>;
};

/** A safe file stem: no path or control characters, bounded. */
export function fileStem(name: string, n: number): string {
  const base =
    name
      .replace(/\.[A-Za-z0-9]{1,5}$/, "")
      .replace(/[^\p{L}\p{N}._-]+/gu, "_")
      .replace(/^[._]+|_+$/g, "")
      .slice(0, 80) || "structure";
  return `${base}-${n}`;
}

type Lookup =
  { state: "busy" } | { state: "none" } | { state: "hit"; hit: PubchemHit };

export default function StructureActions({
  name,
  n,
  smiles,
  curatedMolfile,
  predictionMolfile,
  depictionUrl,
  image,
  onEdit,
  onCompare,
  convert: convertProp,
}: StructureActionsProps) {
  // One conversion per SMILES for the tab: Copy then Download (or Compare's common part)
  // reuse it.
  const client = useContext(QueryClientContext);
  const convert =
    convertProp ??
    ((s: string) =>
      client
        ? client.fetchQuery({ ...molfileQuery(s), retry: false }) // one call, as before
        : api.smilesToMolfile(s));
  const [note, setNote] = useState<string | null>(null);
  const [lookup, setLookup] = useState<Lookup | null>(null);
  const abort = useRef<AbortController | null>(null);
  const stem = fileStem(name, n);

  // A new structure (focus mode steps on) drops the old lookup and note; unmount aborts too.
  useEffect(() => {
    setLookup(null);
    setNote(null);
    return () => {
      abort.current?.abort();
      abort.current = null;
    };
  }, [smiles]);

  async function molfile(): Promise<string> {
    if (curatedMolfile) return curatedMolfile;
    if (predictionMolfile) return predictionMolfile;
    if (!smiles) throw new Error("No structure");
    return convert(smiles);
  }

  async function copy(text: string, done: string) {
    try {
      await navigator.clipboard.writeText(text);
      setNote(done);
    } catch {
      setNote("Could not copy");
    }
  }

  async function copyMolfile() {
    try {
      await copy(await molfile(), "Molfile copied");
    } catch {
      setNote("No molfile");
    }
  }

  async function downloadMolfile() {
    try {
      saveBlob(
        new Blob([await molfile()], { type: "chemical/x-mdl-molfile" }),
        `${stem}.mol`,
      );
      setNote(null);
    } catch {
      setNote("No molfile");
    }
  }

  async function downloadImage() {
    try {
      if (image) {
        saveBlob(image(), `${stem}.svg`);
        setNote(null);
        return;
      }
      if (!depictionUrl) return;
      // The drawing on screen when this tab has loaded it, else asked for once more.
      let blob = loadedDrawing(depictionUrl);
      if (!blob) {
        const res = await fetch(depictionUrl, { credentials: "same-origin" });
        if (!res.ok) throw new Error(String(res.status));
        blob = new Blob([await res.text()], { type: "image/svg+xml" });
      }
      saveBlob(blob, `${stem}.svg`);
      setNote(null);
    } catch {
      setNote("Could not download the image");
    }
  }

  async function findInPubchem() {
    if (!smiles) return;
    abort.current?.abort();
    setNote(null);
    const ctl = new AbortController();
    abort.current = ctl;
    setLookup({ state: "busy" });
    const hit = await pubchemBySmiles(smiles, ctl.signal);
    if (ctl.signal.aborted) return;
    setLookup(hit ? { state: "hit", hit } : { state: "none" });
  }

  const has = Boolean(smiles);
  const hasMol = Boolean(smiles || curatedMolfile || predictionMolfile);
  return (
    <div className="structure-actions">
      <div className="structure-actions__row">
        <GlassButton
          tint="clear"
          size="sm"
          disabled={!hasMol}
          onClick={() => void copyMolfile()}
        >
          Copy molfile
        </GlassButton>
        <GlassButton
          tint="clear"
          size="sm"
          disabled={!hasMol}
          onClick={() => void downloadMolfile()}
        >
          Download molfile
        </GlassButton>
        <GlassButton
          tint="clear"
          size="sm"
          disabled={!image && !depictionUrl}
          onClick={() => void downloadImage()}
        >
          Download image
        </GlassButton>
        <GlassButton
          tint="clear"
          size="sm"
          disabled={!has || lookup?.state === "busy"}
          onClick={() => void findInPubchem()}
        >
          Look up in PubChem
        </GlassButton>
        {onEdit && (
          <GlassButton tint="clear" size="sm" onClick={onEdit}>
            Edit
          </GlassButton>
        )}
        {onCompare && (
          <GlassButton
            tint="clear"
            size="sm"
            disabled={!has}
            onClick={onCompare}
          >
            Compare
          </GlassButton>
        )}
      </div>
      <div className="structure-actions__status" role="status" aria-live="polite">
        {lookup?.state === "busy" && (
          <>
            Looking up…
            <ProgressBar value={null} label="Looking up in PubChem" size="sm" className="structure-actions__bar" />
          </>
        )}
        {lookup?.state === "none" && "Not found in PubChem"}
        {lookup?.state === "hit" && (
          <>
            <span className="structure-actions__cid">CID {lookup.hit.cid}</span>
            {lookup.hit.name && <span> {lookup.hit.name}</span>}{" "}
            <a href={lookup.hit.url} target="_blank" rel="noopener noreferrer">
              Open in PubChem
            </a>
          </>
        )}
        {!lookup && note}
        {lookup && note && <span> {note}</span>}
      </div>
    </div>
  );
}
