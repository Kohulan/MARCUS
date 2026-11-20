#!/usr/bin/env bash
# Real-model smoke test of paper annotation: llama-server with the MARCUS GGUF, the sample PDF
# through docling, then the annotate step's own handler against the server (ops/annotate_smoke.py).
#
#   cd backend-v2
#   MARCUS_LLM_GGUF=/path/to/qwen3.5-9b-marcus-v1-Q8_0.gguf ops/annotate_smoke.sh [--cpu] [PDF]
#
# PDF defaults to the sample paper (frontend-v2/public/sample/synth_015.pdf). GPU (default): the
# CUDA image marcus-v2-llama:cuda-b12554 with one GPU (needs the NVIDIA Container Toolkit and
# about 11 GB of free GPU memory). --cpu: the CPU image, no GPU, a long request timeout,
# MARCUS_SMOKE_THREADS threads (default 16).
# Images: marcus-v2-api:local and marcus-v2-cpu:local must exist (docker compose build api
# worker-cpu); the llama image is built if missing (docker/Dockerfile.llama).
#
# Nothing of a running stack is used or changed: its own internal network (no route out), its own
# containers and temp dir, all removed at exit. The model file is mounted read-only and run as
# its owner's uid:gid. The server arguments are read from docker-compose.gpu.yml (llama-server), so
# the smoke test runs the server exactly as the stack does.
set -euo pipefail
cd "$(dirname "$0")/.."

VARIANT=cuda
if [[ ${1:-} == --cpu ]]; then VARIANT=cpu; shift; fi
PDF=${1:-../frontend-v2/public/sample/synth_015.pdf}
GGUF=${MARCUS_LLM_GGUF:?set MARCUS_LLM_GGUF to the model file}
[[ -f $GGUF && -r $GGUF ]] || { echo "cannot read $GGUF" >&2; exit 2; }
[[ -f $PDF ]] || { echo "no PDF at $PDF" >&2; exit 2; }
GGUF=$(realpath "$GGUF")
if [[ $VARIANT == cuda ]]; then TIMEOUT=${MARCUS_SMOKE_TIMEOUT_S:-110}; else TIMEOUT=${MARCUS_SMOKE_TIMEOUT_S:-3600}; fi
IMAGE=marcus-v2-llama:${VARIANT}-b12554
for img in marcus-v2-api:local marcus-v2-cpu:local; do
  docker image inspect "$img" >/dev/null 2>&1 || { echo "missing image $img (docker compose build)" >&2; exit 2; }
done
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  docker build -f docker/Dockerfile.llama --build-arg VARIANT="$VARIANT" -t "$IMAGE" .
fi

# llama-server's arguments as the GPU stack runs it
mapfile -t ARGS < <(env -i PATH="$PATH" HOME="$HOME" POSTGRES_PASSWORD=x REDIS_PASSWORD=x \
  docker compose --project-directory . --env-file /dev/null -f docker-compose.yml \
  -f docker-compose.gpu.yml config --format json \
  | python3 -c 'import json,sys; print("\n".join(json.load(sys.stdin)["services"]["llama-server"]["command"]))')

NAME=marcus-annotate-smoke-$$
WORK=$(mktemp -d)
cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker network rm "$NAME" >/dev/null 2>&1 || true
  docker run --rm -v "$WORK":/w marcus-v2-api:local sh -c 'rm -rf /w/papers' >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT
trap 'exit 130' INT TERM  # so an interrupted run still cleans up

docker network create --internal "$NAME" >/dev/null
GPU_FLAGS=()
if [[ $VARIANT == cuda ]]; then
  GPU_FLAGS=(--gpus 1)
else
  # CPU only: a fixed thread count (llama.cpp's spinning threads crawl on a busy host)
  ARGS+=(--threads "${MARCUS_SMOKE_THREADS:-16}")
fi
echo "starting llama-server ($IMAGE)"
docker run -d --name "$NAME" --network "$NAME" --read-only --tmpfs /tmp --cap-drop ALL \
  --security-opt no-new-privileges:true --user "$(stat -c %u:%g "$GGUF")" "${GPU_FLAGS[@]}" \
  -v "$GGUF":/models/marcus.gguf:ro "$IMAGE" "${ARGS[@]}" >/dev/null
started=$(date +%s)
until docker exec "$NAME" curl -fsS http://127.0.0.1:8080/health >/dev/null 2>&1; do
  if ! docker ps -q --filter "name=^$NAME$" | grep -q .; then
    docker logs --tail 40 "$NAME" >&2; echo "llama-server stopped" >&2; exit 1
  fi
  if (( $(date +%s) - started > 900 )); then
    docker logs --tail 40 "$NAME" >&2; echo "llama-server not healthy after 900 s" >&2; exit 1
  fi
  sleep 5
done
echo "llama-server healthy after $(( $(date +%s) - started )) s"

PAPER=$(python3 -c 'import uuid; print(uuid.uuid4())')
mkdir -p "$WORK/papers/$PAPER"
cp "$PDF" "$WORK/papers/$PAPER/source.pdf"
chmod -R a+rwX "$WORK"
echo "docling: $PDF"
docker run --rm --network none --read-only --tmpfs /tmp -e MARCUS_DATA_ROOT=/data -v "$WORK":/data \
  marcus-v2-cpu:local python -c "
import uuid
from marcus.core.storage import paper_dir, pdf_path
from marcus.workers import pdfsafe
p = uuid.UUID('$PAPER')
pdfsafe.run_docling(pdf_path(p), paper_dir(p), timeout_s=900)
"

echo "annotating (request timeout ${TIMEOUT} s)"
docker run --rm --network "$NAME" --read-only --tmpfs /tmp -e MARCUS_DATA_ROOT=/data \
  -e MARCUS_ANNOTATOR_URL="http://$NAME:8080" -e MARCUS_ANNOTATOR_TIMEOUT_S="$TIMEOUT" \
  -v "$WORK":/data:ro -v "$PWD/ops":/ops:ro marcus-v2-api:local python /ops/annotate_smoke.py "$PAPER"
echo "annotate smoke test passed"
