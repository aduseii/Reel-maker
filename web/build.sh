#!/usr/bin/env bash
# Assembles the website in ../site: the web/ files plus the app's fonts and emoji pictures.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/site}"
rm -rf "$OUT" && mkdir -p "$OUT/fonts" "$OUT/emoji"
cp -R "$ROOT/web/." "$OUT/"
rm -f "$OUT/build.sh"
cp "$ROOT"/app/fonts/*.ttf "$ROOT/app/fonts/Inter-LICENSE.txt" "$OUT/fonts/"
cp "$ROOT"/app/emoji/*.webp "$OUT/emoji/"
cp "$ROOT"/app/emoji/*.txt "$OUT/emoji/" 2>/dev/null || true
python3 - "$OUT/emoji" <<'PY'
import os, sys, json
d = sys.argv[1]
idx = {}
for f in sorted(os.listdir(d)):
    stem, ext = os.path.splitext(f)
    if ext != ".webp":
        continue
    key = "-".join(p for p in stem.lower().split("-") if p != "fe0f")
    idx.setdefault(key, f)
json.dump(idx, open(os.path.join(d, "index.json"), "w"), separators=(",", ":"))
print(len(idx), "emoji")
PY
touch "$OUT/.nojekyll"
echo "site in $OUT"
