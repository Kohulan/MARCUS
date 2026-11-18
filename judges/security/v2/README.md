# Security judge on v2

The v1 security suite (`../`, 17 tests from 16 functions: `test_pdf_upload_filename_cannot_escape_pdf_dir`
is parametrized twice) ported to the v2 routes (`/api/v2`, `backend-v2/`). Every v1 test has a
v2 test of the same name in a file of the same name, attacking the same weakness on the v2 route
that replaced the v1 one. Every test asserts the SAFE behaviour.

**No vacuous passes.** Each test first calls its v2 route with a valid request and asserts a 2xx
(`helpers.expect_ok`, "EXISTENCE CHECK FAILED ..."), inside the test body, so a missing route
fails the test. Run against v1 (which has no `/api/v2`), all 20 runnable tests fail at that check.

## Running

```bash
cd /home/kohulan/MARCUS/judges
# local v2 fake-engine stack (backend-v2: docker compose -p marcus-v2 -f docker-compose.yml
#   -f docker-compose.fake.yml up -d --build); nginx is the only published port
MARCUS_BACKEND_URL=http://localhost:18090 MARCUS_FRONTEND_URL=http://localhost:18090 \
    MARCUS_FS_PROBE=docker:marcus-v2-api-1 uv run pytest security/v2 -v
```

The stack's nginx serves the v2 web UI too (the `marcus-v2-nginx:local` image built from
`frontend-v2/`), so `MARCUS_FRONTEND_URL` is the same edge. The browser half of #14 needs
Playwright's Chromium (`uv run playwright install chromium`).

Expected: 20 passed, 0 skipped. About 7 minutes, most of it the fake pipeline
(one paper is about 35 s, mostly docling) and the XFF test, which waits for the start of a
rate-limit window and, after its burst, for the next one.

- `common/target.py` picks the URL and refuses production hosts (the `backend` fixture).
- `MARCUS_FS_PROBE=docker:<v2 api container>` is required (the v1 `fs_probe.py`). Beyond file
  checks, the docker probe is used to read the API's effective limits (`effective_settings`) and
  to list the API's real route table (`route_table`), to burst straight at the API from an
  untrusted peer (`direct_burst`), and to send raw requests straight to the API inside its container (`direct_get_many`,
  `127.0.0.1:8000`), so nginx's own URI handling cannot be what stops an attack.
- Owner cookie: the server issues `marcus_owner` as HttpOnly, SameSite=Strict, Path=/api/v2 and
  Secure. httpx does not send a Secure cookie over `http://localhost`, so `helpers.V2Owner`
  reads Set-Cookie and sends the Cookie header itself (as `common/client_v2.py` does).
- The v1 conftest (`../conftest.py`) still loads. Its autouse `ensure_backend_up` is overridden
  here: v1's `/health` does not exist on v2, and a missing v2 route must fail each test's
  existence check, not error the session. `__init__.py` makes the files `v2.test_*`, so they
  do not clash with the v1 files of the same name.
- Direct bursts go to the api container's own network address, not 127.0.0.1: gunicorn ran
  with `--forwarded-allow-ips=127.0.0.1` until R19 was fixed (now `--forwarded-allow-ips=`), so
  uvicorn rewrote a loopback peer from X-Forwarded-For before the app saw it (measured: 6104 spoofed loopback requests, no 429;
  the same without X-Forwarded-For, 429 at 6001). Only processes inside the container can
  connect from loopback, so this is not reachable from outside.
- Uploads are retried (twice, 6 s apart) on 503 `{"detail":"service unavailable"}`: 3 failed
  Redis calls within 5 s (an error, or slower than `rate_limit_redis_timeout_s`, default 1.0 s)
  open the limiter's circuit breaker, and uploads fail closed for 5 s by design. Before D3b one
  0.5 s timeout was enough; that was seen once in these runs (one Redis timeout in the ip scope,
  no load from the judge at the time).
- Each run creates a few dozen owners from one IP. That is far under the fake stack's raised
  1000 new owners per hour, but over the real 10. Against a stack with real limits, expect 429s
  (which is the designed limit working, not a judge result).

## v1 → v2 mapping

| # | v1 test (file::function) | v1 route | v2 test (same file/function name in `v2/`) | v2 route(s) attacked | Safe behaviour asserted on v2 |
|---|---|---|---|---|---|
| 1 | `test_path_traversal_read::test_get_segment_image_does_not_leak_etc_passwd` | `GET /latest/decimer/get_segment_image/{dir}/{image_name:path}` | same | `GET /api/v2/segments/{id}/image`, `GET /api/v2/papers/{id}/pages/{n}/image` | 20 traversal shapes (absolute, `../`, `%2F`, extra segments), via nginx and straight to the API: none returns `/etc/passwd` |
| 2 | `test_path_traversal_read::test_get_segment_image_cannot_reach_arbitrary_container_file` | same | same | same | canaries written by the probe to `/tmp` and `/data` (the data volume, outside any paper) are never served, via nginx or straight to the API |
| 3 | `test_upload_filename_traversal::test_pdf_upload_filename_cannot_escape_pdf_dir[extract_text]` | `POST /latest/docling_conversion/extract_text` | `...[store-upload]` | `POST /api/v2/papers` (the API stores the upload) | 4 escaping filenames (`../`, absolute, `..\`, `../data/`): no file named with the canary under `/tmp` or `/data`; `display_name` is a bare basename |
| 4 | `test_upload_filename_traversal::test_pdf_upload_filename_cannot_escape_pdf_dir[extract_doi]` | `POST /latest/decimer/extract_doi` | `...[doi-pipeline]` | `POST /api/v2/papers` + the `check_pdf`, `docling`, `doi` worker steps (checked via `GET /papers/{id}/steps`) | the same, after the full pipeline ran |
| 5 | `test_upload_filename_traversal::test_ocsr_upload_filename_cannot_escape_images_dir` | `POST /latest/ocsr/generate_smiles` (`image_file`) | same | `POST /api/v2/images` (fake OCSR runs to `done`) | the same for image jobs |
| 6 | `test_ocsr_image_path_oracle::test_ocsr_image_path_is_not_an_existence_oracle` | `POST /latest/ocsr/generate_smiles` (`image_path` form field) | same | `POST /api/v2/segments/{id}/predictions`, `POST /api/v2/images` + `GET /api/v2/images/{id}` | another owner's segment gets the byte-identical 404 as a random id; an `image_path` field is ignored: identical answers without a file, and with a file the FINISHED jobs (status, error, prediction) for an existing and a missing path both equal a plain upload of the same image |
| 7 | `test_highlighted_page_traversal::test_highlighted_page_pdf_filename_is_not_an_existence_oracle` | `GET /latest/decimer/get_highlighted_page/{f}?pdf_filename=` | same | `GET /api/v2/papers/{id}/pages/{n}/image` | existing vs missing target, byte-identical answers for: `pdf_filename` query, traversal in `n`, traversal in the paper id, pages past the end (via nginx and direct); another owner's existing page vs a random id give the same 404 |
| 8 | `test_rate_limit_and_session_bypass::test_burst_requests_eventually_get_rate_limited` | `GET /latest/decimer/health` burst | same | `POST /api/v2/tools/smiles-to-molfile` burst (tools 60/min per owner) | 429 `{"detail": "rate limited"}` with `Retry-After` within 2×60+1 calls; another owner is not limited by it |
| 9 | `test_rate_limit_and_session_bypass::test_api_calls_without_any_session_are_rejected` | `GET /latest/docling_conversion/list_pdfs` with no session | same | `GET /api/v2/papers` with no credential, with a forged cookie, with a forged `mk_` key | v2 does not 401 a credential-less call by design: it becomes a NEW empty owner (cookie HttpOnly, SameSite=Strict, Path=/api/v2, Secure), sees nothing of anyone, never shares an owner with another credential-less call; a forged cookie is a new owner; a forged API key is 401 |
| 10 | `test_no_auth_session_and_listings::test_session_cannot_be_removed_by_an_unrelated_caller` | `DELETE /session/remove/{id}` | same | `DELETE /api/v2/papers/{id}` | another owner and a credential-less caller get the byte-identical 404 as a random id; the paper is untouched; a deleted paper gets the same 404 as a missing one |
| 11 | `test_no_auth_session_and_listings::test_global_session_reset_requires_a_credential` | `POST /session/reset` | same | the API's real route table (`create_app()` inside the api container) + `DELETE /api/v2/papers/{id}` for the existence check | the route table equals the reviewed allowlist (29 routes, the same set as `backend-v2/tests/api/test_security_layer.py` ALLOWED_ROUTES; a new route fails until reviewed and listed); every route but `GET /health` and `GET /ready` depends on `current_owner`; 11 global/admin shapes are never 2xx without a credential; a forged API key is 401 on read, delete and tools |
| 12 | `test_no_auth_session_and_listings::test_uploaded_pdf_is_not_listed_to_an_unrelated_caller` | `GET /latest/docling_conversion/list_pdfs` | same | `GET /api/v2/papers`, `GET /api/v2/queue`, and 12 per-resource routes incl. the new `GET /api/v2/papers/{id}/steps` (R18), `/events`, `/text`, `/export`, `/segments/{id}/image`, `POST .../predictions`, `PUT .../curation`, `GET /api/v2/images/{id}` | another owner and a credential-less caller: not listed, not in `/queue`, and every route gives the byte-identical 404 as a random id |
| 13 | `test_upload_size_limit::test_oversized_image_upload_is_rejected_by_the_backend_directly` | `POST /latest/ocsr/generate_smiles` 20 MB + 1 | same | `POST /api/v2/images` and `POST /api/v2/papers`, 20 MiB + 1 byte | the API itself answers 413 `{"detail": "File too large"}` (JSON, so not nginx's HTML 413; nginx's cap is 21 MiB) |
| 14 | `test_stored_xss_frontend::test_extracted_text_html_does_not_execute_in_browser` | the Vue UI (`v-html`) | same | the React UI behind the stack's nginx (`/app`, upload with "Find structures automatically" off, `?view=paper`) | browser flow: the payload is on screen as text (Text column, header) and never ran |
| 14b | (API half of #14, new) | | `test_stored_xss_frontend::test_display_name_is_returned_only_as_json` | `GET /api/v2/papers`, `/papers/{id}`, `/papers/{id}/text`, `/papers/{id}/export`, `/images/{id}` | an `<img onerror>` filename (kept as `display_name`) and PDF text come back only in JSON as `application/json` (export: a JSON attachment), with nosniff and `default-src 'none'` |
| 15 | `test_security_headers::test_frontend_sends_content_security_policy` | frontend `GET /` (:18080) | same | the v2 edge (:18090): 200 JSON, 200 PNG, owned 404, unknown-route 404, 422, nginx's own 404 | CSP on all |
| 16 | `test_security_headers::test_frontend_sends_nosniff` | same | same | same | `X-Content-Type-Options: nosniff` on all |
| 17 | `test_security_headers::test_frontend_restricts_framing` | same | same | same | `frame-ancestors` or `X-Frame-Options` DENY/SAMEORIGIN on all |
| new | (v1 README: "worth a judge test once claim 5 is fixed") | | `test_rate_limit_and_session_bypass::test_xff_spoof_cannot_escape_rate_limit[via-nginx]` and `[direct-to-api]` | every counted route (burst to an unknown `/api/v2` path) | a burst with a different spoofed `X-Forwarded-For`/`X-Real-IP`/`CF-Connecting-IP`/`True-Client-IP`/`Forwarded` per request, and no cookie, still hits the per-IP limit in one window: through nginx within limit + 9, and straight to the API from an untrusted peer on the Docker network at exactly limit + 1 (the API's own trusted-proxy check, which nginx's X-Forwarded-For rewrite would otherwise hide) |

## Which limits the tests meet

`docker-compose.fake.yml` raises the per-IP limits for single-IP e2e (ip 6000/min, 1000 new
owners per hour, 100 active papers). Per-owner limits are not raised.

| Limit (real value) | Fake stack | Met by |
|---|---|---|
| tools 60/min per owner | 60 | `test_burst_requests_eventually_get_rate_limited` (real value) |
| ip 300/min per IP (IPv6 /64) | 6000 | `test_xff_spoof_cannot_escape_rate_limit` reads the effective limit from the API container and goes past it (6000 on the fake stack, 300 on a real one); the real 300 is unit-tested in `backend-v2/tests/api/test_security_layer.py::test_rate_limit_hits_429`, the /64 in `test_ipv6_rate_bucket_is_the_64_prefix` |
| upload 20 MiB | 20 MiB | `test_oversized_image_upload_is_rejected_by_the_backend_directly` (real value) |
| upload 10/min per owner | 10 | not met by the judge (unit: `test_rate_limit_hits_429`, `test_other_owner_has_own_upload_bucket`) |
| 3 active papers per owner, 6 per IP, 10 new owners per IP per hour | 3 / 100 / 1000 | not met by the judge: exhausting them from the single e2e IP would lock the stack (an hour for new owners). Unit: `test_owner_auth.py::test_eleventh_new_owner_from_one_ip_in_an_hour_is_429`, `test_concurrent_new_owners_respect_the_ip_limit`, `test_security_layer.py::test_ipv6_*_limit_is_per_64`, `test_unknown_peers_share_*` |

## Not covered (and why)

- File checks look in the API container only (`/tmp`, `/data`). `/data` is the volume all
  workers share, so a worker writing a stray file there is caught; a worker's own `/tmp` (a
  tmpfs per container) is not.
- Expired resources (the same 404 as missing) need a clock or DB change; they are unit-tested
  (`backend-v2/tests/api/test_ownership.py::test_expired_paper_gets_same_404`).
