#!/usr/bin/env bash
# On the AWS box: fetch the official "LexUZ oflayn" package (linked from https://lex.uz/uz/offline, Google Drive,
# LexUzOffline.zip, 4.7 GB), unpack it into its own empty folder and report what the document database is made of.
# The package is a Windows program: nothing in it is ever executed here; we only read its data files.
# Terms on lex.uz/uz/offline: free demo for 2 months, then a per-computer licence key from the Adolat centre.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=data/raw/lexuz_offline
mkdir -p "$OUT/zip" "$OUT/unpacked"
ZIP="$OUT/zip/LexUzOffline.zip"
ID=1Nc6j0Uhpce6uJUu_3aLB-36vOgf31iQv
if [ ! -s "$ZIP" ]; then
  curl -L --fail --retry 5 -C - -o "$ZIP" "https://drive.usercontent.google.com/download?id=$ID&export=download&confirm=t"
fi
ls -l "$ZIP"; sha256sum "$ZIP" | tee "$OUT/zip/sha256.txt"
unzip -l "$ZIP" > "$OUT/listing.txt"; tail -3 "$OUT/listing.txt"
unzip -n -q "$ZIP" -d "$OUT/unpacked"
echo "== largest files (the document base is usually the biggest)"
find "$OUT/unpacked" -type f -printf "%s\t%p\n" | sort -rn | head -25 | tee "$OUT/largest.txt"
echo "== file types"
find "$OUT/unpacked" -type f -size +5M -exec file {} \; | tee "$OUT/types.txt"
echo "== extensions"
find "$OUT/unpacked" -type f | sed -n 's/.*\.\([A-Za-z0-9]*\)$/\1/p' | tr 'A-Z' 'a-z' | sort | uniq -c | sort -rn | head -20
du -sh "$OUT/unpacked"
