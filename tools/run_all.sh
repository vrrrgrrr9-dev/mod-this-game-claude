#!/usr/bin/env bash
# Rebuild every analysis artefact from the split upload.
# usage: tools/run_all.sh <workdir> <WOTU_COCO69.apk.xz.part01> [part02 ...]
#   parts must be given in order. Needs: python3 + capstone, binutils (nm/readelf), unzip, xz.
set -euo pipefail
T="$(cd "$(dirname "$0")" && pwd)"; W="$1"; shift
mkdir -p "$W/apk" "$W/out"
cat "$@" | xz -d > "$W/apk/game.apk"
rm -rf "$W/apk/x"; mkdir "$W/apk/x"; unzip -q "$W/apk/game.apk" -d "$W/apk/x"
SO="$W/apk/x/lib/arm64-v8a/libyoyo.so"
cd "$W/out"
python3 -I "$T/scan.py"  "$SO"                   > patches.txt   # every B/BL/ADRP from game code into the mod segment
python3 -I "$T/dis.py"   "$SO" 0x3000000 0x3056000 > inj.asm     # annotated disassembly of the injected code
python3 -I "$T/regtab.py" inj.asm 0x3000098 0x30007c8 > regtab.txt # new YYC event functions registered by the InitLLVM hook
python3 -I "$T/funcs.py"  regtab.txt             > funcs.txt     # per-function summary (hook tags, calls, strings)
for c in "0x3004830 0x30058a0 Coco" "0x301b200 0x301b970 RealitySlicer" "0x301b970 0x301c620 GreenNature" "0x302b230 0x302bf00 SolarCoco"; do
  set -- $c; echo "## $3"; python3 -I "$T/varset.py" "$1" "$2"; done > char_stats.txt
echo "done -> $W/out"
