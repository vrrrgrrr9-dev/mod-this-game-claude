#!/bin/bash
# build_host.sh <jeff dir> <gen dir> <out .so>: grey.c + the shim as an x86-64 shared library
set -e
J=$1; G=$2; OUT=$3; H=$(cd "$(dirname "$0")" && pwd)
python3 $H/gen_shim.py $J/src/yyc.h $G/engine_vars.h $H/shim.c $H/shim.json
clang -O1 -g -fPIC -shared -std=gnu11 -fno-builtin -Wall -Wno-unused-parameter -Wno-unused-function \
  -fsanitize=undefined -fsanitize-trap=all -fno-sanitize=alignment \
  -I $G -I $J/src -o $OUT $J/src/grey.c $H/shim.c -lm
echo built $OUT
