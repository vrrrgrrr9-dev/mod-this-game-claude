#!/bin/bash
# quick native build of the blob (no APK): cc.sh <gen dir with engine.ld/engine_vars.h/stage_decor.h/assets headers> <out dir>
set -e
J=/home/user/mod-this-game-claude/jeff
GEN=$1; OUT=$2; mkdir -p $OUT
CF="--target=aarch64-linux-android21 -O2 -std=gnu11 -ffreestanding -fno-builtin -fno-pic -fno-pie -mcmodel=small -ffixed-x18 -fno-stack-protector -fno-exceptions -fno-unwind-tables -fno-asynchronous-unwind-tables -fno-common -Wall -Wextra -Wno-unused-parameter -Wno-unused-function"
objs=""
for c in jeff scyther grey hooks libc; do
  clang $CF -I $GEN -I $J/src -c $J/src/$c.c -o $OUT/$c.o
  objs="$objs $OUT/$c.o"
done
if llvm-objdump -r $objs | grep -q R_AARCH64_ABS; then echo "ABS RELOC"; exit 1; fi
ld.lld -m aarch64linux -static -no-pie --no-relax -L $GEN -T $J/src/jeff.ld -o $OUT/jeff.elf $objs
echo built $OUT/jeff.elf
python3 -I $J/build/elfpatch.py /tmp/claude-0/-home-user-mod-this-game-claude/51a3ce15-244d-5021-bb4f-fc7dfc2fb7b8/scratchpad/jout2/libyoyo.orig.so $OUT/jeff.elf $OUT/libyoyo.so > $OUT/elfpatch.log 2>&1 || { tail -5 $OUT/elfpatch.log; exit 1; }
echo patched $OUT/libyoyo.so
