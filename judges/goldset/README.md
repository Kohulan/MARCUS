# Gold set judge

Question: of the structures that COCONUT links to a paper, how many does
MARCUS find in that paper's PDF, per OCSR engine (decimer, molnextr,
molscribe)? The same manifest and scorer are used for the current build (v1)
and the rebuild (v2); only the client that produces `runs/*.jsonl` changes.

## Files

| File | Committed | What |
|---|---|---|
| `build.py` | yes | builds the gold set (downloads + selection + manifest) |
| `chem.py` | yes | the one structure standardisation used by builder and scorer |
| `score.py` | yes | scores run JSONL files against the manifest |
| `test_score.py` | yes | unit tests for the scorer |
| `manifest.jsonl` | yes | one line per paper: ids, PDF URL, sha256, pages, bytes, split, expected structures |
| `manifest_meta.json` | yes | source URLs and versions, selection funnel, distributions, RDKit failures |
| `data/` | no (git-ignored) | COCONUT dump, Europe PMC responses, PDF zips, `data/pdf/<PMCID>.pdf` |

## Build

```bash
cd judges
uv run python goldset/build.py            # first run: ~250 MB COCONUT zip + ~100 PDFs
uv run python goldset/build.py --offline  # rebuild from cache only, no network
```

The client agent reads `pdf_path` (`goldset/data/pdf/<PMCID>.pdf`, relative
to `judges/`) and should check `sha256` before uploading. The `paper_id` in
each run line must be the manifest `paper_id` (the PMCID).

How it is built:

1. **COCONUT** release 2026-11, full CSV
   (`https://coconut.s3.uni-jena.de/prod/downloads/2026-11/coconut_csv-11-2026.zip`,
   linked from https://coconut.naturalproducts.net/download). The CSV has a
   `dois` column (pipe-separated). DOIs are lower-cased, `doi.org/` prefixes
   stripped, and split on `|` only (old SICI DOIs contain `;`).
2. Molecules are grouped by DOI. Candidates are DOIs with 1 to 60 distinct
   COCONUT identifiers, put in four strata by that count: 1, 2-5, 6-15, 16-60.
3. Per stratum the DOIs are shuffled with a fixed seed and looked up in the
   **Europe PMC REST search** in rounds of 1000 (at least 3000 per stratum,
   more until 30 usable PDFs are in the pool) (`DOI:"..." OR ...`, 40 per
   query). A paper qualifies if `isOpenAccess == "Y"`, it has a PMCID, it is
   not a review (`pubTypeList`), and Europe PMC's open-access PDF bundle has
   it (`https://ftp.ebi.ac.uk/pub/databases/pmc/pdf/OA/PMCxxxx<n>/<PMCID>.zip`).
   The `europepmc.org/articles/<PMCID>?pdf=render` links are behind a
   Cloudflare browser challenge, so the FTP bundle (same PDFs, same provider)
   is used instead. No Unpaywall, no email, no key.
4. Per stratum 25 papers: the 2 largest PDFs first (so the set has a few long
   PDFs), then the seeded order. A PDF is kept only if it starts with
   `%PDF-` and pypdf opens it with at least one page. Rejections are listed in
   `manifest_meta.json`.
5. Split inside each stratum by alternating dev/test, so 50/50 overall and
   balanced per stratum. The 5 largest PDFs by bytes and the 5 largest by
   pages are flagged `load_test_candidate`.
6. Every COCONUT SMILES is standardised with `chem.py` (below). Molecules
   RDKit cannot parse stay in the manifest with `rdkit_ok: false` and are
   listed in `manifest_meta.json`; the scorer leaves them out of the
   denominators and reports how many it left out.

Every response and file is cached in `data/`, so a rebuild with the cache is
identical. A rebuild without the cache uses the same pinned COCONUT file, but
Europe PMC's open-access status and search results can change over time; the
retrieval date is in each record's `provenance`.

## Current set (built 2026-11-16)

- COCONUT 2026-11: 738,793 molecules, 241,765 with a DOI, 96,735 distinct
  DOIs; 96,518 DOIs have 1 to 60 structures (strata 1: 27,585; 2-5: 40,966;
  6-15: 22,410; 16-60: 5,557).
- Looked up 12,000 of them in Europe PMC: 6,538 found, 367 open access with
  a PMCID (about 3% of those looked up), 30 reviews dropped, 334 with a PDF
  in the OA bundle. 100 selected, no PDF rejected.
- dev 50 / test 50; per stratum 13/12, 12/13, 13/12, 12/13.
- 865 COCONUT ids (861 distinct full keys); per paper median 6, p95 28,
  max 40. RDKit parsed all 865; 2 change InChIKey on standardisation.
- Pages: median 12, p95 19, max 33. Bytes: median 1.47 MB, p95 8.7 MB,
  max 48.7 MB. Production has median 1.5 MB and p95 7.5 MB, so file size is
  realistic; segment counts will be far below production's p95 of 190
  (these are short research articles). Load-test candidates (largest by
  bytes or pages): PMC9259500 (48.7 MB), PMC6017977 (21.3 MB), PMC6100211
  (19.2 MB), PMC3933326, PMC7912134, and PMC4519256 (23 pages).
- Journals: mostly Molecules (25), Marine Drugs (11), PLoS ONE (10);
  years 2008-2022. 94 of 100 PDFs contain the DOI string in their first
  three pages; the other 6 (BMC/Springer 2011-2014 and one Braz. J.
  Microbiol.) were not checked by hand.

## Standardisation (`chem.py`)

`MolFromSmiles` -> `Normalizer` -> `LargestFragmentChooser(preferOrganic=True)`
-> `Uncharger`, then canonical SMILES and standard InChIKey. No metal
disconnection, no tautomer canonicalisation (the standard InChI already
merges mobile-H tautomers; RDKit's canonical tautomer can drop stereo). The
same function runs on predictions, so salts, charges and drawing
differences of nitro groups etc. do not count as misses.

## Score

```bash
cd judges
uv run python goldset/score.py runs/v1-*.jsonl runs/v2-*.jsonl \
    --out goldset/score.json --md goldset/score.md
uv run pytest goldset -q
```

A system is one `(build, engine)` pair. Each system is scored per split.
Report dev while iterating; touch test only to compare final builds.

| Number | Meaning |
|---|---|
| recall full | per paper: distinct expected full InChIKeys found among the paper's predictions / distinct expected full InChIKeys. Averaged over papers (macro), with a paper-level bootstrap 95% CI (2000 resamples, seed 12345). |
| recall full grouped | expected structures grouped by first block; a group counts as found if the prediction's full key equals ANY COCONUT stereo record in the group. COCONUT often holds 2 to 10 stereo records for one compound (from different source collections), so strict recall full cannot reach 100% on those papers (30 of the 100). Use this as the stereo-aware headline. |
| recall skeleton | same with the InChIKey first block: connectivity only, so wrong or missing stereo still counts as found. The gap between the two is mostly stereo. |
| micro recall full | all matches / all expected structures, pooled over papers (big papers weigh more). |
| mean best Tanimoto | per expected structure, the highest Morgan (r=2, 2048 bit) Tanimoto to any valid prediction in the paper, averaged. Near-misses (one wrong atom) show up here but not in recall. 0 when a paper has no valid prediction. |
| invalid SMILES % | predictions with a non-empty SMILES that RDKit cannot parse or standardise, over all predictions with a non-empty SMILES. Segments with no SMILES at all are counted separately (`segment_errors`). |
| papers w/ page errors | papers whose run reported at least one page error. |
| segments/paper | segments returned per paper (median, max; mean in JSON). |
| paired comparison | for every pair of systems, on the papers both ran in that split: mean per-paper difference (B - A) with bootstrap CI, counts of papers where B or A is better, and an exact sign test. Use this to compare engines and to compare v1 with v2. |

A paper that was run but failed (no segments) scores 0. A paper that was not
run at all is listed under `missing_papers` and left out of that system's
mean, so always check `papers run/total`. Run lines whose `pdf_sha256`
differs from the manifest are skipped and listed. If the same system ran a
paper twice, the latest `started_at` is used.

**Precision is not measured.** Papers draw many structures that COCONUT does
not list for that DOI (synthetic intermediates, known reference compounds,
reagents, partial structures, R-group tables), so an unmatched prediction is
not evidence of an error. The scorer says so in its output and does not
report it.

## Known limits

- **COCONUT DOI links can be wrong or incomplete.** COCONUT merges many
  source collections; some attach a DOI of a later citing paper, a review,
  a database paper or a paper where the compound is only mentioned. Recall
  of 100% is therefore not always reachable, and the ceiling is unknown. Use
  the numbers to compare systems on the same papers, not as absolute truth.
  Example in the set: PMC3229060 is a dermatology case report (epidermal
  cysts under tacrolimus) linked to tacrolimus; it very likely draws no
  structure. Such papers sit mostly in the 1-structure stratum and pull
  every system's recall down equally.
- **Structures may be in the SI, not the main PDF.** The PDFs are Europe
  PMC's main-article PDFs (`pdf_kind: main_article`); supplementary files
  are not included. Known natural products that a paper only names (for
  example "compounds 5-12 were identified as known ...") are often drawn only
  in the SI or not at all.
- **Different paper, same DOI.** `doi_in_first_pages` records whether the DOI
  string was found in the text of the first three pages (pypdf text
  extraction). `false` is usually an older layout without a printed DOI, but
  check those papers by hand if a result looks odd.
- **Stereo in COCONUT.** Ids `CNPxxxxxxx.0` have no stereo at all; `.1`,
  `.2`, ... are stereo records of the same base compound. In 30 papers
  COCONUT links several stereo records of one compound to the DOI (74
  skeleton groups; one has 10 records), often the same compound entered by
  different sources with different or partial stereo. Strict recall full is
  capped below 100% there; use recall full grouped and recall skeleton.
- **Selection bias.** Only open-access papers in PMC; reviews excluded;
  strata are equal-sized (25 each), not proportional to COCONUT, so small
  papers are under-represented relative to COCONUT and large ones over.
- **Europe PMC changes.** Without the `data/` cache a rebuild may pick
  different papers if open-access status changed.
