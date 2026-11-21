#!/bin/sh
# Makes the fake COCONUT's TLS files (fake stack only, docker-compose.fake.yml) in the folder
# given as $1: a throwaway test CA (ca.pem, also as ca-certificates.crt for nginx; its key is
# deleted right after signing, so nothing else can ever be signed by it) and a certificate for
# coconut.naturalproducts.net (cert.pem, key.pem) that only that CA vouches for.
# The fake-coconut service runs this at its first start into the fake-coconut-tls volume, so no
# key is ever stored in git. The fake stack's nginx trusts that CA and nothing else.
set -eu
out=${1:?usage: gen-certs.sh OUTPUT_DIR}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
openssl req -x509 -newkey rsa:2048 -nodes -days 7300 -subj "/CN=MARCUS fake COCONUT test CA" \
  -keyout "$work/ca.key" -out "$work/ca.pem" 2>/dev/null
openssl req -newkey rsa:2048 -nodes -subj "/CN=coconut.naturalproducts.net" \
  -keyout "$work/key.pem" -out "$work/cert.csr" 2>/dev/null
printf 'subjectAltName=DNS:coconut.naturalproducts.net\nbasicConstraints=CA:FALSE\nextendedKeyUsage=serverAuth\n' \
  > "$work/ext.cnf"
openssl x509 -req -in "$work/cert.csr" -CA "$work/ca.pem" -CAkey "$work/ca.key" \
  -CAserial "$work/ca.srl" -CAcreateserial -days 7300 -extfile "$work/ext.cnf" \
  -out "$work/cert.pem" 2>/dev/null
# key.pem last: the service treats a present key.pem as "all files made"
cp "$work/ca.pem" "$out/ca.pem"
cp "$work/ca.pem" "$out/ca-certificates.crt"
cp "$work/cert.pem" "$out/cert.pem"
cp "$work/key.pem" "$out/key.pem"
chmod 644 "$out/ca.pem" "$out/ca-certificates.crt" "$out/cert.pem" "$out/key.pem"
