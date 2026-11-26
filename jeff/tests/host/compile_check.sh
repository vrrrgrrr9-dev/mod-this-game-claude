#!/bin/bash
# Compile-only check of the mod blob (no APK, no tests): headers from v10's libyoyo.so/game.droid.
# usage: compile_check.sh <repo jeff dir> <out dir>
set -e
J=$1; OUT=$2; X=${V10:?set V10 to an unzipped base APK dir (lib/, assets/game.droid)}; A=${ASSETS:?set ASSETS to the rendered art dir}
mkdir -p $OUT
CF="--target=aarch64-linux-android21 -O2 -std=gnu11 -ffreestanding -fno-builtin -fno-pic -fno-pie -mcmodel=small -ffixed-x18 -fno-stack-protector -fno-exceptions -fno-unwind-tables -fno-asynchronous-unwind-tables -fno-common -Wall -Wextra -Wno-unused-parameter -Wno-unused-function"
cd $J
python3 -c "import sys; sys.path.insert(0,'art'); import manifest; open('$OUT/jeff_assets.h','w').write(manifest.header('$A'))"
python3 art/scyther/manifest.py $A $OUT/scyther_assets.h
python3 art/grey/grey_manifest.py $A $OUT
python3 build/gen_engine.py $X/lib/arm64-v8a/libyoyo.so $OUT/engine.ld $OUT/engine_vars.h
python3 build/gen_stage.py $X/assets/game.droid $OUT/stage_decor.h
objs=""
for c in jeff scyther grey hooks libc; do
  clang $CF -I $OUT -I $J/src -c $J/src/$c.c -o $OUT/$c.o
  objs="$objs $OUT/$c.o"
done
if llvm-objdump -r $objs | grep -q R_AARCH64_ABS; then echo "ABS RELOC"; exit 1; fi
ld.lld -m aarch64linux -static -no-pie --no-relax -L $OUT -T $J/src/jeff.ld -o $OUT/jeff.elf $objs
echo "OK $OUT/jeff.elf"
llvm-objdump -r $objs | grep -c -i -E "draw_primitive|draw_vertex" || true
