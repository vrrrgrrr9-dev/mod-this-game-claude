"""Build the WOTU Coco mod + Jeff + Black Holing Scyther + Grey APK in one go.

usage:
  python build.py --apk WOTU_COCO69.apk --out <dir>
  python build.py --parts WOTU_COCO69.apk.xz.part01 ... part05 --out <dir>

needs: python3 (numpy, pillow, scipy), clang + ld.lld (any recent LLVM), binutils nm, ffmpeg (libvorbis),
       java + uber-apk-signer.jar (--signer, default: <out>/uber-apk-signer.jar)
result: <out>/WOTU_COCO69_Jeff.apk, signed with the debug key built into uber-apk-signer. That is the
        same certificate the Coco build is signed with, so the APK installs as an update over it and
        players keep their data. The build checks this after signing and stops if the certificate
        differs from the input APK's.
"""
import argparse, lzma, os, shutil, subprocess, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'src')
sys.path.insert(0, os.path.join(ROOT, 'art'))
sys.path.insert(0, HERE)
import apksig

CFLAGS = ['--target=aarch64-linux-android21', '-O2', '-std=gnu11', '-ffreestanding', '-fno-builtin',
          '-fno-pic', '-fno-pie', '-mcmodel=small', '-ffixed-x18', '-fno-stack-protector', '-fno-exceptions',
          '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '-fno-common', '-Wall', '-Wextra',
          '-Wno-unused-parameter', '-Wno-unused-function']
SIG_FILES = ('.SF', '.RSA', '.DSA', '.EC')


def run(cmd, **kw):
    print('+', ' '.join(cmd) if isinstance(cmd, list) else cmd)
    subprocess.run(cmd, check=True, **kw)


def get_apk(args, work):
    if args.apk:
        return args.apk
    path = os.path.join(work, 'input.apk')
    with open(path, 'wb') as out:
        dec = lzma.LZMADecompressor()
        for p in args.parts:
            with open(p, 'rb') as f:
                while True:
                    chunk = f.read(1 << 22)
                    if not chunk:
                        break
                    out.write(dec.decompress(chunk))
    return path


def build_native(work, libyoyo, assets, droid):
    gen = os.path.join(work, 'gen'); os.makedirs(gen, exist_ok=True)
    import manifest
    open(os.path.join(gen, 'jeff_assets.h'), 'w').write(manifest.header(assets))
    run([sys.executable, '-I', os.path.join(ROOT, 'art', 'scyther', 'manifest.py'), assets,
         os.path.join(gen, 'scyther_assets.h')])
    run([sys.executable, '-I', os.path.join(ROOT, 'art', 'grey', 'grey_manifest.py'), assets, gen])
    run([sys.executable, '-I', os.path.join(HERE, 'gen_engine.py'), libyoyo,
         os.path.join(gen, 'engine.ld'), os.path.join(gen, 'engine_vars.h')])
    run([sys.executable, '-I', os.path.join(HERE, 'gen_stage.py'), droid, os.path.join(gen, 'stage_decor.h')])
    objs = []
    for c in ('jeff.c', 'scyther.c', 'grey.c', 'hooks.c', 'libc.c'):
        o = os.path.join(gen, c[:-2] + '.o')
        run(['clang'] + CFLAGS + ['-I', gen, '-I', SRC, '-c', os.path.join(SRC, c), '-o', o])
        objs.append(o)
    # no absolute relocations allowed: the blob must work at any load address
    rel = subprocess.run(['llvm-objdump', '-r'] + objs, capture_output=True, text=True).stdout
    if 'R_AARCH64_ABS' in rel:
        sys.exit('absolute relocation found in Jeff objects:\n' + rel)
    elf = os.path.join(gen, 'jeff.elf')
    run(['ld.lld', '-m', 'aarch64linux', '-static', '-no-pie', '--no-relax', '-L', gen,
         '-T', os.path.join(SRC, 'jeff.ld'), '-o', elf] + objs)
    return elf


def repack(src_apk, out_apk, replace, add_dir):
    zin = zipfile.ZipFile(src_apk)
    with zipfile.ZipFile(out_apk, 'w') as zout:
        for info in zin.infolist():
            n = info.filename
            if n.startswith('META-INF/') and (n.endswith(SIG_FILES) or n == 'META-INF/MANIFEST.MF'):
                continue                                    # old signature
            data = open(replace[n], 'rb').read() if n in replace else zin.read(n)
            zi = zipfile.ZipInfo(n, info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zout.writestr(zi, data)
        for f in sorted(os.listdir(add_dir)):
            if not f.endswith(('.png', '.ogg')):           # build metadata stays out of the APK
                continue
            zi = zipfile.ZipInfo('assets/' + f, (2026, 11, 24, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_STORED
            zout.writestr(zi, open(os.path.join(add_dir, f), 'rb').read())


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--apk'); g.add_argument('--parts', nargs='+')
    ap.add_argument('--out', required=True)
    ap.add_argument('--signer')
    ap.add_argument('--assets', help='reuse an already rendered assets dir (skips the art build)')
    args = ap.parse_args()
    work = os.path.abspath(args.out); os.makedirs(work, exist_ok=True)

    apk = get_apk(args, work)
    z = zipfile.ZipFile(apk)
    lib_in = os.path.join(work, 'libyoyo.orig.so'); open(lib_in, 'wb').write(z.read('lib/arm64-v8a/libyoyo.so'))
    droid_in = os.path.join(work, 'game.orig.droid'); open(droid_in, 'wb').write(z.read('assets/game.droid'))

    assets = os.path.join(work, 'assets')
    if args.assets and os.path.abspath(args.assets) != assets:
        shutil.rmtree(assets, ignore_errors=True)
        shutil.copytree(args.assets, assets)
    elif not args.assets:
        shutil.rmtree(assets, ignore_errors=True)
        run([sys.executable, '-I', os.path.join(ROOT, 'art', 'build_art.py'), assets])
        run([sys.executable, '-I', os.path.join(ROOT, 'art', 'scyther', 'build_art.py'), assets])
        run([sys.executable, '-I', os.path.join(ROOT, 'art', 'grey', 'build_art.py'), assets])

    elf = build_native(work, lib_in, assets, droid_in)
    lib_out = os.path.join(work, 'libyoyo.so')
    droid_out = os.path.join(work, 'game.droid')
    run([sys.executable, '-I', os.path.join(HERE, 'elfpatch.py'), lib_in, elf, lib_out])
    run([sys.executable, '-I', os.path.join(HERE, 'droidpatch.py'), droid_in, droid_out])

    replace = {'lib/arm64-v8a/libyoyo.so': lib_out, 'assets/game.droid': droid_out}
    import dexpatch                                    # the user's save-recovery fix (classes5.dex)
    if dexpatch.DEX in z.namelist():
        fixed = dexpatch.patch(z.read(dexpatch.DEX))
        if fixed is not None:
            dex_out = os.path.join(work, dexpatch.DEX)
            open(dex_out, 'wb').write(fixed)
            replace[dexpatch.DEX] = dex_out
            print('save-recovery fix applied to', dexpatch.DEX)
        else:
            print('save-recovery fix: code not found, classes5.dex left as is')
    unsigned = os.path.join(work, 'WOTU_COCO69_Jeff-unsigned.apk')
    repack(apk, unsigned, replace, assets)
    signer = args.signer or os.path.join(work, 'uber-apk-signer.jar')
    if not os.path.exists(signer):
        print('no uber-apk-signer.jar: leaving the APK unsigned ->', unsigned)
        return
    signed_dir = os.path.join(work, 'signed'); shutil.rmtree(signed_dir, ignore_errors=True)
    run(['java', '-jar', signer, '-a', unsigned, '-o', signed_dir, '--allowResign'])
    produced = [f for f in os.listdir(signed_dir) if f.endswith('.apk')]
    final = os.path.join(work, 'WOTU_COCO69_Jeff.apk')
    shutil.move(os.path.join(signed_dir, produced[0]), final)

    # Must be signed like the installed Coco build, or Android refuses the update (uninstall = data loss).
    orig, new = apksig.fingerprints(apk), apksig.fingerprints(final)
    if not apksig.same_signer(orig, new):
        bad = final + '.WRONG-KEY'
        os.replace(final, bad)
        sys.exit(f'signing certificate differs from the input APK, it would not install as an update:\n'
                 f'  input : {orig}\n  output: {new}\n  (kept as {bad})')
    print('signing certificate matches the input APK:', apksig.pretty(new['v2'][0] if 'v2' in new else
                                                                     next(iter(new.values()))[0]))
    print('done ->', final)


if __name__ == '__main__':
    main()
