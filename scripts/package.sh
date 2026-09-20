#!/usr/bin/env bash
set -euo pipefail

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_dir"

ref="${1:-HEAD}"
short_ref="$(git rev-parse --short "$ref")"
mkdir -p dist
archive="dist/skillsmith-src-${short_ref}.tar.gz"

git archive --format=tar.gz --prefix=skillsmith/ --output="$archive" "$ref"
shasum -a 256 "$archive" | tee "${archive}.sha256"
echo "Tracked source package: $archive"
