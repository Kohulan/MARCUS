#!/bin/sh
# Serves dist/ on http://localhost:18091 with the production location rules
# (deploy/ui-locations.conf), proxying /api/v2/ to the fake stack on 127.0.0.1:18090.
# Host network; nginx binds only the loopback port 18091. Stop with `npm run serve:stop`.
# The bind mount follows the dist/ directory itself: after `rm -rf dist`, run this again.
set -eu
cd "$(dirname "$0")/.."

if [ ! -f dist/index.html ] || [ ! -f dist/ketcher/index.html ]; then
  echo "serve-local: no complete dist/ (run npm run build first)" >&2
  exit 1
fi

docker rm -f marcus-ui-dev >/dev/null 2>&1 || true
docker run -d --rm --name marcus-ui-dev --network host \
  -v "$PWD/dist:/usr/share/nginx/marcus-ui:ro" \
  -v "$PWD/deploy/dev-nginx.conf:/etc/nginx/nginx.conf:ro" \
  -v "$PWD/deploy/ui-locations.conf:/etc/nginx/marcus/ui-locations.conf:ro" \
  nginxinc/nginx-unprivileged:1.27-alpine >/dev/null

i=0
until curl -fsS -o /dev/null http://127.0.0.1:18091/; do
  i=$((i + 1))
  if [ "$i" -ge 50 ]; then
    echo "serve-local: nginx did not answer on 127.0.0.1:18091" >&2
    docker logs marcus-ui-dev >&2 || true
    exit 1
  fi
  sleep 0.2
done
echo "serve-local: http://localhost:18091 (container marcus-ui-dev)"
