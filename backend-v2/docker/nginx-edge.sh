#!/bin/sh
# MARCUS v2 nginx settings from the environment, run by the image's entrypoint before nginx
# starts (mounted as /docker-entrypoint.d/25-marcus-edge.sh). Writes the two files nginx.conf
# includes, in /tmp/nginx (tmpfs). nginx.conf includes them by exact path, so nginx refuses to
# start if this script did not run; an invalid value stops the container here.
#
#   MARCUS_NGINX_CONN_PER_IP     requests in progress per client address (default 64)
#   MARCUS_NGINX_UPLOADS_PER_IP  uploads (POST /papers, /images) in progress per address (4)
#   MARCUS_REAL_IP_FROM          switch day: the address(es) the outer proxy (and any proxy hop
#                                in front of this nginx) connects from, comma-separated, single
#                                addresses only (no names, no ranges). Empty (default) = off:
#                                the socket peer is the client and X-Forwarded-For is ignored.
#                                On: nginx takes the client from X-Forwarded-For, but only from
#                                these peers, walking right to left past the listed hops; that
#                                address is what limit_conn counts and what the API is sent.
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

real="$out/real_ip.conf"
: > "$real"
octet='(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])'
if [ -n "${MARCUS_REAL_IP_FROM:-}" ]; then
    for addr in $(echo "$MARCUS_REAL_IP_FROM" | tr ',' ' '); do
        ok=0
        case "$addr" in
            *[!0-9a-fA-F:.]*|''|0.0.0.0|::) ;;
            *:*) ok=1 ;;  # IPv6: nginx -t checks the rest
            *) echo "$addr" | grep -Eq "^$octet(\.$octet){3}$" && ok=1 ;;
        esac
        if [ "$ok" != 1 ]; then
            echo "$0: MARCUS_REAL_IP_FROM: '$addr' is not a single IP address" >&2
            exit 1
        fi
        echo "set_real_ip_from $addr;" >> "$real"
    done
    printf 'real_ip_header X-Forwarded-For;\nreal_ip_recursive on;\n' >> "$real"
    echo "$0: real_ip on, trusted proxies: $MARCUS_REAL_IP_FROM"
else
    echo "$0: real_ip off (MARCUS_REAL_IP_FROM empty)"
fi
