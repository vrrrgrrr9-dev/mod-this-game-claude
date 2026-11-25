"""The user's save-recovery fix in the Coco mod's Java code (classes5.dex), applied on every build.

com.coco.transfer.SaveStore.recover() threw IOException("The save recovery copy is missing.") when
the recovery copy was gone. The fix (from the user's WOTU_COCO69_v6_fixed APK) calls
SaveStore.removeTree(v0) instead, then jumps past the throw. It is the same 15 bytes of
Dalvik code, patched in place. The DEX header's SHA-1 signature and adler32 checksum are
recomputed afterwards.
"""
import hashlib, struct, sys, zlib

DEX = 'classes5.dex'
OLD = bytes.fromhex('2200a7001a01220270204a02100027')   # new-instance IOException / const-string / <init> / throw
NEW = bytes.fromhex('7110a0010000280500000000000000')   # invoke-static removeTree(v0) / goto +5 / nop


def patch(d):
    """returns the patched dex, or None when the code is not there exactly once (other base APK)."""
    if d.count(OLD) != 1:
        return None
    d = bytearray(d.replace(OLD, NEW))
    d[12:32] = hashlib.sha1(bytes(d[32:])).digest()
    struct.pack_into('<I', d, 8, zlib.adler32(bytes(d[12:])) & 0xffffffff)
    return bytes(d)


if __name__ == '__main__':
    src, dst = sys.argv[1:3]
    out = patch(open(src, 'rb').read())
    if out is None:
        sys.exit('save-recovery code not found exactly once: left as is')
    open(dst, 'wb').write(out)
    print('save-recovery fix applied')
