#!/usr/bin/env bash
# Download the MARCUS model (nuextract3-marcus-multi-v1, Apache-2.0) from Zenodo and check it.
# https://doi.org/10.5281/zenodo.24562147
#
#   scripts/get-marcus-model.sh [folder]      (default folder: ./models)
#
# It downloads the model (4.5 GB) and its vision projector (0.7 GB), checks their SHA-256 sums,
# and prints the two lines to put in .env. A file that is already there and correct is kept.
set -euo pipefail

RECORD="24562147"
BASE="https://zenodo.org/records/${RECORD}/files"
DIR="${1:-./models}"

declare -A SHA256=(
  [nuextract3-marcus-multi-v1-Q8_0.gguf]="23b6cd870851c6146219651305627ff94c5525ebc31833c550808072941a2fc2"
  [nuextract3-marcus-multi-v1-mmproj-f16.gguf]="3610f755e9c8630d42fd295970df1e8572c688a9fe3883f9e459f73cd085649b"
)

mkdir -p "$DIR"
DIR="$(cd "$DIR" && pwd)"

ok() { [ -f "$1" ] && echo "$2  $1" | sha256sum --check --status; }

for name in "${!SHA256[@]}"; do
  file="$DIR/$name"
  if ok "$file" "${SHA256[$name]}"; then
    echo "have   $name"
    continue
  fi
  echo "fetch  $name"
  curl -fL --retry 3 -C - -o "$file.part" "$BASE/$name?download=1"
  mv "$file.part" "$file"
  if ! ok "$file" "${SHA256[$name]}"; then
    echo "error: $name has the wrong SHA-256; delete it and run this again" >&2
    exit 1
  fi
  echo "ok     $name"
done

cat <<EOF

Done. Put these two lines in backend-v2/.env:
MARCUS_LLM_GGUF=$DIR/nuextract3-marcus-multi-v1-Q8_0.gguf
MARCUS_LLM_MMPROJ=$DIR/nuextract3-marcus-multi-v1-mmproj-f16.gguf
EOF
