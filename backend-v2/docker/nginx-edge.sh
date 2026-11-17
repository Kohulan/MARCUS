#!/bin/sh
# MARCUS v2 nginx settings from the environment, run by the image's entrypoint before nginx
# starts (mounted as /docker-entrypoint.d/25-marcus-edge.sh). Writes the two files nginx.conf
# includes, in /tmp/nginx (tmpfs). nginx.conf includes them by exact path, so nginx refuses to
# start if this script did not run; an invalid value stops the container here.
#
#   MARCUS_NGINX_CONN_PER_IP     requests in progress per client address (default 64)
#   MARCUS_NGINX_UPLOADS_PER_IP  uploads (POST /papers, /images) in progress per address (4)
set -eu

out=/tmp/nginx
mkdir -p "$out"

int_or_die() {  # name value
    case "$2" in
        ''|*[!0-9]*|0) echo "$0: $1 must be a positive integer, got '$2'" >&2; exit 1 ;;
    esac
}

conn="${MARCUS_NGINX_CONN_PER_IP:-64}"
uploads="${MARCUS_NGINX_UPLOADS_PER_IP:-4}"
int_or_die MARCUS_NGINX_CONN_PER_IP "$conn"
int_or_die MARCUS_NGINX_UPLOADS_PER_IP "$uploads"
printf 'limit_conn perip %s;\nlimit_conn uploads %s;\n' "$conn" "$uploads" > "$out/limits.conf"
echo "$0: limit_conn perip $conn, uploads $uploads"
