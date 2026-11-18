// PubChem by SMILES (v1 searchPubChemBySmiles): the first CID of the identity lookup, then
// its Title. Any failure is null. Response values are checked and shown as text only.
import { fetchJson, isRecord } from "./fetchJson";

const BASE = "https://pubchem.ncbi.nlm.nih.gov";

export type PubchemHit = { cid: number; name: string | null; url: string };

function firstCid(body: unknown): number | null {
  if (!isRecord(body) || !isRecord(body.IdentifierList)) return null;
  const cids = body.IdentifierList.CID;
  const cid = Array.isArray(cids) ? cids[0] : undefined;
  // CID 0 is PubChem's "no match" placeholder.
  return typeof cid === "number" && Number.isSafeInteger(cid) && cid > 0
    ? cid
    : null;
}

function title(body: unknown): string | null {
  if (!isRecord(body) || !isRecord(body.PropertyTable)) return null;
  const props = body.PropertyTable.Properties;
  const first: unknown = Array.isArray(props) ? props[0] : undefined;
  const t = isRecord(first) ? first.Title : undefined;
  return typeof t === "string" && t.trim() ? t.trim().slice(0, 300) : null;
}

export async function pubchemBySmiles(
  smiles: string,
  signal?: AbortSignal,
): Promise<PubchemHit | null> {
  const s = smiles.trim();
  if (!s) return null;
  try {
    const found = await fetchJson(
      `${BASE}/rest/pug/compound/smiles/cids/JSON?smiles=${encodeURIComponent(s)}`,
      { headers: { Accept: "application/json" } },
      signal,
    );
    const cid = firstCid(found);
    if (cid === null) return null;
    let name: string | null = null;
    try {
      name = title(
        await fetchJson(
          `${BASE}/rest/pug/compound/cid/${cid}/property/Title/JSON`,
          { headers: { Accept: "application/json" } },
          signal,
        ),
      );
    } catch {
      // The CID alone is still a result.
    }
    return { cid, name, url: `${BASE}/compound/${cid}` };
  } catch {
    return null;
  }
}
