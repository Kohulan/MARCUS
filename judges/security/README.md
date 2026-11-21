# Security judge

Proves or disproves the ten security claims from the earlier read-only code
review against the **local CPU copy** of production (backend
`http://localhost:19000`, frontend `http://localhost:18080`, container
`marcus-judge-backend`). Every test asserts the SAFE behaviour, so it FAILS
on a vulnerable build and PASSES on a fixed one. No test skips: a test that
needs a probe it doesn't have (`MARCUS_FS_PROBE`) errors, it never passes
quietly.

## Running

```bash
cd /home/kohulan/MARCUS/judges
MARCUS_FS_PROBE=docker:marcus-judge-backend uv run pytest security -v
```

The local backend is CPU-only and loads several large ML/document-parsing
models on first use; `conftest.py` waits up to 10 minutes for `/health`
before running anything, and the HTTP client default timeout is 300s. A
cold run of the full suite can take several minutes.

### What was added to the judges environment

- `uv add reportlab playwright` (+ `uv run playwright install chromium`),
  for building real PDFs with literal text and for the stored-XSS
  end-to-end browser test. Recorded in `judges/pyproject.toml` /
  `uv.lock`.
- `security/fs_probe.py`: the pluggable filesystem probe described in the
  task brief, selected by `MARCUS_FS_PROBE`. `v2` points this at its own
  backend by setting a different `MARCUS_FS_PROBE` value (or by swapping in
  a new probe backend in this file) -- no test file changes.

## Results on v1 (commit 4400fb7 / images in `../stack/IMAGES.md`)

| Test file : test | Claim | File:line evidence | Result on v1 |
|---|---|---|---|
| `test_path_traversal_read.py` (both tests) | 1 | `decimer_segmentation.py:367` (`..` substring check only) + `:384` (`os.path.join` with an absolute `image_name`) | **FAIL** (vulnerable) -- `GET /latest/decimer/get_segment_image/x//etc/passwd` returns the container's `/etc/passwd`, HTTP 200, live |
| `test_upload_filename_traversal.py` (3 tests) | 2 | `docling_conversion.py:137-173` (no validator called), `decimer_segmentation.py:66-116`, `ocsr_wrapper.py:76-86` | **FAIL** (vulnerable) -- confirmed live: `pdf_file` filename `../../../../tmp/<name>.pdf` writes to `/tmp/<name>.pdf` on all three endpoints (decimer's uuid insertion doesn't stop it) |
| `test_ocsr_image_path_oracle.py` | 3 | `ocsr_engine.py:62-77` (`find_image_path` returns any existing path verbatim) | **FAIL** (vulnerable) -- live: `image_path=/etc/hostname` -> 500 "cannot identify image file"; a nonexistent path -> 404. Status differs -> oracle confirmed |
| `test_highlighted_page_traversal.py` | 4 | `decimer_segmentation_wrapper.py:477` (`os.path.join(PDF_DIR, pdf_filename)`, no check) | **FAIL** (vulnerable) -- live: `pdf_filename=../../../../etc/passwd` -> 500 echoing the resolved path `/app/uploads/pdfs/../../../../etc/passwd`; nonexistent -> 404 |
| `test_rate_limit_and_session_bypass.py::test_burst_requests...` | 5 | `rate_limit_middleware.py` exempt list containing `"/"`, matched with `startswith` | **FAIL** (vulnerable) -- live: 40-60 consecutive requests to `/latest/decimer/health`, all HTTP 200, no 429, no rate-limit headers |
| `test_rate_limit_and_session_bypass.py::test_api_calls_without_any_session...` | 5 | `session_middleware.py` exempt list containing `"/"`, `"/latest"`, `"/v1"` | **FAIL** (vulnerable) -- `GET /latest/docling_conversion/list_pdfs` with no session id of any kind returns 200, not 401 |
| `test_no_auth_session_and_listings.py` (3 tests) | 6 | `session_router.py:226-233` (`remove_session`), `:293-324` (`reset_all_sessions`), `docling_conversion.py:197-227` (`list_pdfs`) | **FAIL** (vulnerable) -- live: an unrelated client with zero credentials removed another client's session; `POST /session/reset` succeeded with no credential; `list_pdfs` returned a file uploaded by an unrelated, session-less caller |
| `test_upload_size_limit.py` | 7 | `config.py` (`MAX_UPLOAD_SIZE` defined, never imported by any router/module); `file_validator.py` only wired into `extract_pdf_json` | **FAIL** (vulnerable) -- a 20MB+1 byte image upload to `generate_smiles` was *not* rejected with 413 (see also "Anything new" below: a 20MB+ PDF to `extract_doi` is accepted and then runs for minutes through pdf2doi's fallback chain, at one point appearing to hang indefinitely on Method #4's title lookup) |
| `test_stored_xss_frontend.py` | 8 | `HighlightedText.vue` (`v-html` on unescaped extracted text) | **FAIL** (vulnerable) -- full real UI flow at `:18080` (upload PDF -> click "Extract Text") ran `window.__judge_xss_fired = true` from the rendered `<img onerror>` payload. No fallback needed; the end-to-end flow worked |
| `test_security_headers.py` (3 tests) | 9 | `frontend/nginx.conf` (no `add_header` for CSP/nosniff/frame-ancestors) | **FAIL** (vulnerable) -- live: `curl -D- http://localhost:18080/` has no `Content-Security-Policy`, `X-Content-Type-Options`, or `X-Frame-Options` |

All ten listed claims were confirmed true against both the source and the
running local copy. None turned out false.

## Claim 10 / anything else found

- **Unbounded, apparently unbounded-time processing of adversarial
  uploads (DoS).** Sending a 20MB file of repeated `0x00` bytes with a
  `%PDF-` header to `/latest/decimer/extract_doi` is accepted (no size
  check -- see claim 7) and then run through `pdf2doi`'s full fallback
  chain (PyPDF2 -> pdfminer -> "Method #4: looking for possible
  publication titles"), observed live to still be running after several
  minutes with no response. The backend appears to be a single
  CPU-bound worker (processing one request blocks `/health` itself), so
  this is a full-service DoS reachable by any anonymous caller, made
  worse by claim 5 (no rate limiting) and claim 6 (no auth): nothing
  stops a script from doing this in a loop. **Not** turned into an
  automated test: reproducing it reliably took the shared local backend
  container out of service for several minutes each time (it was
  restarted by hand once, with `docker restart marcus-judge-backend`, to
  recover for the rest of this suite), and running it on every judge
  invocation would make the whole suite (and the `load`/`goldset`
  judges sharing the same container) unreliable. Documented here with
  reproduction steps instead:
  ```bash
  python3 -c "open('/tmp/big.pdf','wb').write(b'%PDF-1.4\n' + b'\x00'*(20*1024*1024))"
  curl -F "pdf_file=@/tmp/big.pdf;type=application/pdf" \
       http://localhost:19000/latest/decimer/extract_doi
  ```
- **Rate limiting's client identifier trusts client-supplied headers.**
  `app/security/rate_limiter.py::get_client_identifier` falls back to
  `X-Forwarded-For` / `X-Real-IP` / `CF-Connecting-IP` with no
  trusted-proxy check, so even after fixing the claim-5 exempt-path bug,
  any client can reset which "client" they appear as on every request by
  sending a different `X-Forwarded-For` header, bypassing per-client rate
  limiting entirely. Not testable as a distinct, falsifiable check right
  now because claim 5 already means *no* request is ever rate-limited on
  v1 (there is nothing to distinguish "limited but spoofable" from
  "never limited" from the outside) -- worth a judge test once claim 5 is
  fixed in v2.

Final verified run (clean container, after fixing a bug in the harness
itself -- see below):

```
17 failed in 241.74s (0:04:01)
```

All 17 tests FAIL on v1. Zero false passes.

## Notes on test design

- `test_ocsr_image_path_oracle.py` and `test_highlighted_page_traversal.py`
  compare the HTTP status for an existing-but-unauthorized path against a
  guaranteed-nonexistent one, rather than asserting a fixed status code --
  a safe v2 might reasonably reject both with 400 *or* 404, as long as
  it's the same answer either way (no oracle). The `fs_probe` fixture is
  used to independently confirm both files' existence/non-existence on the
  real filesystem rather than guessing.
- `test_upload_size_limit.py` deliberately avoids the (very slow, see
  above) PDF upload path and instead oversizes a PNG sent to the OCSR
  endpoint, which fails fast on invalid pixel data regardless of file
  size, to make the 413 check fast and repeatable.
- `test_stored_xss_frontend.py` needs the payload PDF to extract to ten
  words or fewer so the backend's own `extract_pdf_text` falls back to raw
  `pypdf` text (its docling pass happens to HTML-escape `<`/`>`, which
  would otherwise mask the vulnerability for this particular payload --
  the component itself still has no escaping either way, and a differently
  laid-out PDF or a different extraction endpoint would still be
  exploitable through the same `v-html` sink).
- A bug in this harness, not in MARCUS: an earlier version of
  `test_upload_filename_traversal.py` searched `/tmp` for the literal
  string `"<token>.pdf"`, but `extract_doi` and the ocsr upload both
  insert their own uuid *before* the extension (`<token>_<uuid>.pdf`), so
  the substring never matched and those two checks passed vacuously. Fixed
  by searching for the bare token instead of `token + extension`; all
  three endpoints then correctly FAIL (confirmed by directly listing the
  container's `/tmp` via the fs probe). The numbers above are from the
  run after that fix.
