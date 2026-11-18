// PubChem by SMILES (v1 searchPubChemBySmiles): one identity lookup that answers the first
// match's CID and Title together. Any failure is null. Response values are checked and shown
// as text only.
import { fetchJson, isRecord } from "./fetchJson";

const BASE = "https://pubchem.ncbi.nlm.nih.gov";

export type PubchemHit = { cid: number; name: string | null; url: string };

function firstMatch(body: unknown): { cid: number; name: string | null } | null {
  if (!isRecord(body) || !isRecord(body.PropertyTable)) return null;
  const props = body.PropertyTable.Properties;
  const first: unknown = Array.isArray(props) ? props[0] : undefined;
  if (!isRecord(first)) return null;
  const cid = first.CID;
  // CID 0 is PubChem's "no match" placeholder.
  if (typeof cid !== "number" || !Number.isSafeInteger(cid) || cid <= 0) return null;
  const t = first.Title;
  return { cid, name: typeof t === "string" && t.trim() ? t.trim().slice(0, 300) : null };
}

export async function pubchemBySmiles(
  smiles: string,
  signal?: AbortSignal,
): Promise<PubchemHit | null> {
  const s = smiles.trim();
  if (!s) return null;
  try {
    const match = firstMatch(
      await fetchJson(
        `${BASE}/rest/pug/compound/smiles/property/Title/JSON?smiles=${encodeURIComponent(s)}`,
        { headers: { Accept: "application/json" } },
        signal,
      ),
    );
    return match && { ...match, url: `${BASE}/compound/${match.cid}` };
  } catch {
    return null;
  }
}
