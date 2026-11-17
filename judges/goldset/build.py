"""Build the MARCUS gold set from COCONUT + Europe PMC open-access PDFs.

    cd judges && uv run python goldset/build.py            # build / rebuild
    cd judges && uv run python goldset/build.py --offline  # only use cached data

Deterministic: every download and API response is cached under
goldset/data/ (git-ignored). With the cache present the manifest is
rebuilt byte-for-byte. Without it, the same pinned COCONUT release is used,
but Europe PMC's open-access status can change over time.

Outputs (committed): goldset/manifest.jsonl, goldset/manifest_meta.json
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import logging
import random
import re
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chem import STANDARDISATION, standardise  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
MANIFEST = HERE / "manifest.jsonl"
META = HERE / "manifest_meta.json"

# ---- pinned sources ---------------------------------------------------------
COCONUT_RELEASE = "2026-11"
COCONUT_URL = "https://coconut.s3.uni-jena.de/prod/downloads/2026-11/coconut_csv-11-2026.zip"
COCONUT_PAGE = "https://coconut.naturalproducts.net/download"
EPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
# Europe PMC's open-access PDF bundle. The europepmc.org "?pdf=render" links
# sit behind a Cloudflare browser challenge and are not scriptable, so we use
# the same PDFs from Europe PMC's public FTP mirror.
EPMC_PDF_FTP = "https://ftp.ebi.ac.uk/pub/databases/pmc/pdf/OA"
USER_AGENT = "marcus-judges/0.1"

# ---- selection parameters ---------------------------------------------------
SEED = 20261116
BINS = [(1, 1), (2, 5), (6, 15), (16, 60)]  # number of COCONUT ids per DOI
PER_BIN = 25          # 4 bins x 25 = 100 papers
QUERY_CHUNK = 1000      # DOIs looked up in Europe PMC per round
MIN_QUERY_PER_BIN = 3000  # at least this many per bin (bigger pool for long PDFs)
POOL_MARGIN = 5         # keep querying until PER_BIN + margin OA PDFs are in the pool
EPMC_BATCH = 40       # DOIs per Europe PMC query
LONG_PER_BIN = 2      # largest open-access PDFs forced into each bin
N_LOAD_TEST = 5       # largest selected PDFs flagged as load-test candidates
CONCURRENCY = 3

log = logging.getLogger("goldset.build")


# ---- HTTP -------------------------------------------------------------------
def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(60.0, connect=20.0),
        follow_redirects=True,
    )


def http(client: httpx.Client, method: str, url: str, *, tries: int = 5, **kw) -> httpx.Response:
    """Request with retries and exponential backoff on network errors, 429 and 5xx."""
    delay = 2.0
    for attempt in range(1, tries + 1):
        try:
            r = client.request(method, url, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
            return r
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if attempt == tries:
                raise
            log.warning("retry %d/%d %s %s: %s", attempt, tries, method, url, exc)
            time.sleep(delay)
            delay *= 2
    raise AssertionError("unreachable")


def sha256_file(p: Path) -> str:
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


# ---- 1. COCONUT -------------------------------------------------------------
def norm_doi(raw: str) -> str | None:
    d = raw.strip().lower()
    d = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", d)
    return d if re.match(r"^10\.\d{4,9}/\S+$", d) else None


def load_coconut(offline: bool) -> tuple[dict, dict, dict]:
    """Return (doi -> sorted ids, id -> molecule row, source info)."""
    zpath = DATA / "coconut" / Path(COCONUT_URL).name
    zpath.parent.mkdir(parents=True, exist_ok=True)
    if not zpath.exists():
        if offline:
            raise SystemExit(f"--offline but {zpath} is missing")
        log.info("downloading %s", COCONUT_URL)
        tmp = zpath.with_suffix(".part")
        with _client() as c, c.stream("GET", COCONUT_URL) as r:
            r.raise_for_status()
            with tmp.open("wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
        tmp.rename(zpath)
    zsha = sha256_file(zpath)
    index_path = DATA / "coconut" / f"doi_index-{zsha[:16]}.json.gz"
    if index_path.exists():
        idx = json.loads(gzip.decompress(index_path.read_bytes()))
    else:
        log.info("parsing COCONUT CSV (one-off, ~1 min)")
        csv.field_size_limit(10**9)
        by_doi: dict[str, set] = {}
        mols: dict[str, dict] = {}
        n_rows = n_with_doi = 0
        with zipfile.ZipFile(zpath) as z:
            name = z.namelist()[0]
            with z.open(name) as raw:
                rd = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
                columns = rd.fieldnames
                for row in rd:
                    n_rows += 1
                    dois = {d for d in (norm_doi(x) for x in row["dois"].split("|")) if d}
                    if not dois:
                        continue
                    n_with_doi += 1
                    cid = row["identifier"]
                    mols[cid] = {
                        "smiles": row["canonical_smiles"],
                        "inchikey": row["standard_inchi_key"],
                        "name": row["name"],
                    }
                    for d in dois:
                        by_doi.setdefault(d, set()).add(cid)
        idx = {
            "csv_name": name,
            "columns": columns,
            "n_rows": n_rows,
            "n_with_doi": n_with_doi,
            "by_doi": {d: sorted(v) for d, v in sorted(by_doi.items())},
            "mols": mols,
        }
        index_path.write_bytes(gzip.compress(json.dumps(idx).encode(), mtime=0))
    info = {
        "url": COCONUT_URL,
        "download_page": COCONUT_PAGE,
        "release": COCONUT_RELEASE,
        "zip_sha256": zsha,
        "zip_bytes": zpath.stat().st_size,
        "csv_name": idx["csv_name"],
        "columns": idx["columns"],
        "doi_column": "dois (pipe-separated; split on '|' only, lower-cased, doi.org prefix stripped)",
        "n_molecules": idx["n_rows"],
        "n_molecules_with_doi": idx["n_with_doi"],
        "n_distinct_dois": len(idx["by_doi"]),
    }
    return idx["by_doi"], idx["mols"], info


def bin_of(n: int) -> int | None:
    for i, (lo, hi) in enumerate(BINS):
        if lo <= n <= hi:
            return i
    return None


# ---- 2. Europe PMC ----------------------------------------------------------
def epmc_lookup(client: httpx.Client, dois: list[str], offline: bool) -> dict[str, dict]:
    """Search Europe PMC for a batch of DOIs. Cached per batch. Returns doi -> best record."""
    dois = [d for d in dois if '"' not in d]
    query = " OR ".join(f'DOI:"{d}"' for d in dois)
    key = hashlib.sha256(query.encode()).hexdigest()[:24]
    cache = DATA / "epmc" / "search" / f"{key}.json"
    if cache.exists():
        payload = json.loads(cache.read_text())
    else:
        if offline:
            raise SystemExit(f"--offline but Europe PMC cache {cache} missing")
        params = {"query": query, "resultType": "core", "format": "json", "pageSize": 1000}
        r = http(client, "GET", EPMC_SEARCH, params=params)
        r.raise_for_status()
        full = r.json()
        keep = ("doi", "pmcid", "pmid", "id", "source", "title", "journalInfo", "pubYear",
                "isOpenAccess", "inEPMC", "inPMC", "hasPDF", "license", "pubTypeList",
                "fullTextUrlList", "firstPublicationDate")
        payload = {
            "query": query,
            "retrieved": dt.date.today().isoformat(),
            "api_version": full.get("version"),
            "hitCount": full.get("hitCount"),
            "results": [{k: rec.get(k) for k in keep} for rec in full["resultList"]["result"]],
        }
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload, sort_keys=True))
        time.sleep(0.3)
    wanted = set(dois)
    best: dict[str, dict] = {}
    for rec in payload["results"]:
        d = norm_doi(rec.get("doi") or "")
        if d not in wanted:
            continue
        rec = dict(rec, _api_version=payload["api_version"], _retrieved=payload["retrieved"])
        score = (rec.get("isOpenAccess") == "Y", bool(rec.get("pmcid")), rec.get("source") == "MED")
        if d not in best or score > best[d]["_score"]:
            best[d] = dict(rec, _score=score)
    return best


def pub_types(rec: dict) -> list[str]:
    return list((rec.get("pubTypeList") or {}).get("pubType") or [])


def is_review(rec: dict) -> bool:
    return any("review" in t.lower() for t in pub_types(rec))


def ftp_zip_url(pmcid: str) -> str:
    n = int(pmcid[3:])
    return f"{EPMC_PDF_FTP}/PMCxxxx{(n - 1) // 10000 + 1}/{pmcid}.zip"


def ftp_head(client: httpx.Client, pmcid: str, heads: dict, offline: bool) -> int | None:
    """Size in bytes of the OA PDF zip, or None if Europe PMC has no PDF. Cached."""
    if pmcid in heads:
        return heads[pmcid]
    if offline:
        return None
    r = http(client, "HEAD", ftp_zip_url(pmcid))
    size = int(r.headers.get("content-length", 0)) if r.status_code == 200 else None
    heads[pmcid] = size
    return size


# ---- 3. PDFs ----------------------------------------------------------------
def fetch_pdf(client: httpx.Client, pmcid: str, doi: str, offline: bool) -> dict:
    """Download + validate one OA PDF. Returns pdf facts or {'error': ...}."""
    zdir = DATA / "zips"
    pdir = DATA / "pdf"
    zdir.mkdir(parents=True, exist_ok=True)
    pdir.mkdir(parents=True, exist_ok=True)
    zpath = zdir / f"{pmcid}.zip"
    url = ftp_zip_url(pmcid)
    if not zpath.exists():
        if offline:
            return {"error": "offline and zip not cached"}
        r = http(client, "GET", url)
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code} for {url}"}
        zpath.write_bytes(r.content)
        time.sleep(0.2)
    try:
        with zipfile.ZipFile(zpath) as z:
            names = z.namelist()
            pdfs = [n for n in names if n.lower().endswith(".pdf")]
            main = f"{pmcid}.pdf" if f"{pmcid}.pdf" in names else (pdfs[0] if len(pdfs) == 1 else None)
            if main is None:
                return {"error": f"no unambiguous main PDF in zip: {names}"}
            data = z.read(main)
    except zipfile.BadZipFile as exc:
        return {"error": f"bad zip: {exc}"}
    if not data.startswith(b"%PDF-"):
        return {"error": "missing %PDF- magic bytes"}
    ppath = pdir / f"{pmcid}.pdf"
    if not ppath.exists() or ppath.read_bytes() != data:
        ppath.write_bytes(data)
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = len(reader.pages)
        text = ""
        for i in range(min(3, pages)):
            try:
                text += reader.pages[i].extract_text() or ""
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        return {"error": f"pypdf could not open: {type(exc).__name__}: {exc}"}
    if pages < 1:
        return {"error": "PDF has no pages"}
    flat = re.sub(r"\s+", "", text).lower()
    return {
        "pdf_url": url,
        "pdf_member": main,
        "zip_members": names,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "pages": pages,
        "doi_in_first_pages": doi.lower() in flat,
        "pdf_path": f"goldset/data/pdf/{pmcid}.pdf",
    }


# ---- 4. expected structures --------------------------------------------------
def expected_for(ids: list[str], mols: dict) -> list[dict]:
    out = []
    for cid in ids:
        m = mols[cid]
        s = standardise(m["smiles"])
        out.append({
            "coconut_id": cid,
            "name": m["name"] or None,
            "canonical_smiles": m["smiles"],
            "coconut_inchikey": m["inchikey"] or None,
            "rdkit_ok": s.ok,
            "rdkit_error": s.error,
            "std_smiles": s.smiles,
            "inchikey": s.inchikey,
            "inchikey_first_block": s.first_block,
        })
    return out


# ---- main -------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="never touch the network; use cache only")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("pypdf").setLevel(logging.ERROR)

    by_doi, mols, coconut_info = load_coconut(args.offline)
    log.info("COCONUT %s: %d molecules, %d with DOI, %d distinct DOIs", COCONUT_RELEASE,
             coconut_info["n_molecules"], coconut_info["n_molecules_with_doi"], len(by_doi))

    # Candidate DOIs: 1..60 COCONUT ids, grouped into bins, shuffled with a fixed seed.
    bins: list[list[str]] = [[] for _ in BINS]
    for d, ids in by_doi.items():  # by_doi is sorted -> deterministic
        b = bin_of(len(ids))
        if b is not None:
            bins[b].append(d)
    for i, lst in enumerate(bins):
        random.Random(f"{SEED}-bin{i}").shuffle(lst)
    n_candidates = sum(len(b) for b in bins)
    log.info("candidate DOIs (1-60 structures): %d  per bin %s", n_candidates, [len(b) for b in bins])

    heads_path = DATA / "epmc" / "ftp_heads.json"
    heads = json.loads(heads_path.read_text()) if heads_path.exists() else {}
    stats = {"bins": []}
    selected: list[dict] = []
    unparsable_log: list[dict] = []

    with _client() as client:
        for bi, cand in enumerate(bins):
            # Query Europe PMC in fixed chunks (seeded order) until the pool of
            # open-access research papers with a PDF is big enough, or the bin is exhausted.
            found: dict[str, dict] = {}
            queried: list[str] = []
            with_pdf: list[tuple[str, int]] = []
            oa: list[str] = []
            reviews: list[str] = []
            while len(queried) < len(cand) and (len(queried) < MIN_QUERY_PER_BIN
                                                or len(with_pdf) < PER_BIN + POOL_MARGIN):
                chunk = cand[len(queried):len(queried) + QUERY_CHUNK]
                batches = [chunk[i:i + EPMC_BATCH] for i in range(0, len(chunk), EPMC_BATCH)]
                with ThreadPoolExecutor(CONCURRENCY) as ex:
                    for res in ex.map(lambda b: epmc_lookup(client, b, args.offline), batches):
                        found.update(res)
                queried.extend(chunk)
                c_oa = [d for d in chunk if d in found and found[d].get("isOpenAccess") == "Y"
                        and found[d].get("pmcid")]
                oa.extend(c_oa)
                reviews.extend(d for d in c_oa if is_review(found[d]))
                c_research = [d for d in c_oa if not is_review(found[d])]
                with ThreadPoolExecutor(CONCURRENCY) as ex:
                    sizes = list(ex.map(lambda d: ftp_head(client, found[d]["pmcid"], heads, args.offline),
                                        c_research))
                with_pdf.extend((d, sz) for d, sz in zip(c_research, sizes) if sz)
                heads_path.parent.mkdir(parents=True, exist_ok=True)
                heads_path.write_text(json.dumps(heads, sort_keys=True, indent=0))
            # order: LONG_PER_BIN largest first (ties -> DOI), then seeded order
            longest = [d for d, _ in sorted(with_pdf, key=lambda x: (-x[1], x[0]))[:LONG_PER_BIN]]
            order = longest + [d for d, _ in with_pdf if d not in longest]
            picked: list[dict] = []
            rejected: list[dict] = []
            seen_pmcid: set[str] = {p["pmcid"] for p in selected}
            for d in order:
                if len(picked) >= PER_BIN:
                    break
                rec = found[d]
                pmcid = rec["pmcid"]
                if pmcid in seen_pmcid:
                    rejected.append({"doi": d, "pmcid": pmcid, "reason": "duplicate PMCID"})
                    continue
                exp = expected_for(by_doi[d], mols)
                bad = [e for e in exp if not e["rdkit_ok"]]
                if len(bad) == len(exp):
                    rejected.append({"doi": d, "pmcid": pmcid, "reason": "no RDKit-parsable structure"})
                    unparsable_log.extend({"doi": d, "coconut_id": e["coconut_id"],
                                           "canonical_smiles": e["canonical_smiles"],
                                           "error": e["rdkit_error"], "paper_selected": False}
                                          for e in bad)
                    continue
                pdf = fetch_pdf(client, pmcid, d, args.offline)
                if "error" in pdf:
                    log.warning("reject %s %s: %s", d, pmcid, pdf["error"])
                    rejected.append({"doi": d, "pmcid": pmcid, "reason": pdf["error"]})
                    continue
                unparsable_log.extend({"doi": d, "coconut_id": e["coconut_id"],
                                       "canonical_smiles": e["canonical_smiles"],
                                       "error": e["rdkit_error"], "paper_selected": True}
                                      for e in bad)
                seen_pmcid.add(pmcid)
                uniq_full = {e["inchikey"] for e in exp if e["inchikey"]}
                uniq_fb = {e["inchikey_first_block"] for e in exp if e["inchikey_first_block"]}
                ji = rec.get("journalInfo") or {}
                picked.append({
                    "paper_id": pmcid,
                    "doi": d,
                    "pmcid": pmcid,
                    "pmid": rec.get("pmid"),
                    "title": rec.get("title"),
                    "journal": ((ji.get("journal") or {}).get("title")),
                    "year": rec.get("pubYear"),
                    "license": rec.get("license"),
                    "pub_types": pub_types(rec),
                    "stratum": f"{BINS[bi][0]}-{BINS[bi][1]}",
                    "forced_long": d in longest,
                    **{k: pdf[k] for k in ("pdf_url", "pdf_path", "sha256", "pages", "bytes",
                                           "doi_in_first_pages", "pdf_member", "zip_members")},
                    # Europe PMC OA bundle = publisher's main article PDF; SI is separate.
                    "pdf_kind": "main_article",
                    "n_coconut_ids": len(exp),
                    "n_expected_full_keys": len(uniq_full),
                    "n_expected_first_blocks": len(uniq_fb),
                    "n_rdkit_failed": len(bad),
                    "expected": exp,
                    "provenance": {
                        "coconut_url": COCONUT_URL,
                        "coconut_release": COCONUT_RELEASE,
                        "epmc_search": EPMC_SEARCH,
                        "epmc_api_version": rec["_api_version"],
                        "epmc_retrieved": rec["_retrieved"],
                    },
                })
            # stratified split inside the bin: alternate, start side flips per bin
            for k, p in enumerate(picked):
                p["split"] = ("dev", "test")[(k + bi) % 2]
            selected.extend(picked)
            stats["bins"].append({
                "stratum": f"{BINS[bi][0]}-{BINS[bi][1]}",
                "candidate_dois": len(cand),
                "queried_in_epmc": len(queried),
                "found_in_epmc": sum(d in found for d in queried),
                "open_access_with_pmcid": len(oa),
                "oa_reviews_excluded": len(reviews),
                "oa_research_with_ftp_pdf": len(with_pdf),
                "selected": len(picked),
                "rejected": rejected,
            })
            log.info("bin %s: queried %d, in EPMC %d, OA %d (reviews %d), PDF on FTP %d, selected %d",
                     stats["bins"][-1]["stratum"], len(queried), stats["bins"][-1]["found_in_epmc"],
                     len(oa), len(reviews), len(with_pdf), len(picked))

    # load-test candidates: largest PDFs by bytes and by pages
    by_bytes = sorted(selected, key=lambda p: (-p["bytes"], p["paper_id"]))[:N_LOAD_TEST]
    by_pages = sorted(selected, key=lambda p: (-p["pages"], p["paper_id"]))[:N_LOAD_TEST]
    flagged = {p["paper_id"] for p in by_bytes + by_pages}
    for p in selected:
        p["load_test_candidate"] = p["paper_id"] in flagged

    selected.sort(key=lambda p: (p["split"], p["stratum"], p["paper_id"]))
    with MANIFEST.open("w") as f:
        for p in selected:
            f.write(json.dumps(p, sort_keys=False, ensure_ascii=False) + "\n")

    def dist(vals):
        v = sorted(vals)
        if not v:
            return {}
        q = lambda x: v[min(len(v) - 1, int(round(x * (len(v) - 1))))]  # noqa: E731
        return {"n": len(v), "min": v[0], "p25": q(.25), "median": q(.5), "p75": q(.75),
                "p95": q(.95), "max": v[-1], "sum": sum(v)}

    meta = {
        "built_with": "goldset/build.py",
        "seed": SEED,
        "bins": [f"{lo}-{hi}" for lo, hi in BINS],
        "per_bin": PER_BIN,
        "query_chunk": QUERY_CHUNK,
        "min_query_per_bin": MIN_QUERY_PER_BIN,
        "standardisation": STANDARDISATION,
        "coconut": coconut_info,
        "europe_pmc": {
            "search_api": EPMC_SEARCH,
            "pdf_source": EPMC_PDF_FTP + "/PMCxxxx<bucket>/<PMCID>.zip",
            "pdf_source_note": "europepmc.org ?pdf=render is behind a Cloudflare JS challenge; "
                               "the FTP bundle is Europe PMC's own OA PDF distribution",
            "open_access_rule": "isOpenAccess == 'Y' and pmcid present and PDF zip present on FTP",
            "reviews_excluded": True,
        },
        "candidate_dois_1_to_60": n_candidates,
        "selection": stats,
        "counts": {
            "papers": len(selected),
            "dev": sum(p["split"] == "dev" for p in selected),
            "test": sum(p["split"] == "test" for p in selected),
            "per_split_stratum": {
                s: {f"{lo}-{hi}": sum(p["split"] == s and p["stratum"] == f"{lo}-{hi}" for p in selected)
                    for lo, hi in BINS} for s in ("dev", "test")},
            "expected_structures_coconut_ids": sum(p["n_coconut_ids"] for p in selected),
            "rdkit_unparsable": len(unparsable_log),
            "doi_found_in_first_pages": sum(p["doi_in_first_pages"] for p in selected),
        },
        "distributions": {
            "n_coconut_ids": dist([p["n_coconut_ids"] for p in selected]),
            "n_expected_full_keys": dist([p["n_expected_full_keys"] for p in selected]),
            "pages": dist([p["pages"] for p in selected]),
            "bytes": dist([p["bytes"] for p in selected]),
        },
        "load_test_candidates": [
            {"paper_id": p["paper_id"], "bytes": p["bytes"], "pages": p["pages"], "split": p["split"]}
            for p in sorted(selected, key=lambda p: -p["bytes"]) if p["load_test_candidate"]],
        "rdkit_unparsable": unparsable_log,
    }
    META.write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n")
    log.info("wrote %s (%d papers: %d dev / %d test) and %s", MANIFEST, len(selected),
             meta["counts"]["dev"], meta["counts"]["test"], META)


if __name__ == "__main__":
    main()
