#!/bin/sh
# Makes the fake COCONUT's TLS files (fake stack only, docker-compose.fake.yml): a throwaway
# test CA (ca.pem; its key is deleted right after signing, so nothing else can ever be signed
# by it) and a certificate for coconut.naturalproducts.net (cert.pem, key.pem) that only that
# CA vouches for. The fake stack's nginx trusts ca.pem and nothing else. Valid 20 years.
set -eu
cd "$(dirname "$0")"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
openssl req -x509 -newkey rsa:2048 -nodes -days 7300 -subj "/CN=MARCUS fake COCONUT test CA" \
  -keyout "$work/ca.key" -out ca.pem
openssl req -newkey rsa:2048 -nodes -subj "/CN=coconut.naturalproducts.net" \
  -keyout key.pem -out "$work/cert.csr"
printf 'subjectAltName=DNS:coconut.naturalproducts.net\nbasicConstraints=CA:FALSE\nextendedKeyUsage=serverAuth\n' \
  > "$work/ext.cnf"
openssl x509 -req -in "$work/cert.csr" -CA ca.pem -CAkey "$work/ca.key" -CAserial "$work/ca.srl" -CAcreateserial \
  -days 7300 -extfile "$work/ext.cnf" -out cert.pem
chmod 644 key.pem cert.pem ca.pem  # read by the fake's uid 10001 through a bind mount
