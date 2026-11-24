"""Signer certificates of an APK, so a rebuild can be checked to install as an update.

Android only installs an APK over an existing app when both are signed with the same certificate
(otherwise the user has to uninstall first and loses the app's local data). This reads the
certificates from the APK Signature Scheme v2/v3 blocks (Android 7+) and from the v1 JAR signature
(META-INF/*.RSA|DSA|EC, used by Android 6) and returns their SHA-256 fingerprints.

usage: python apksig.py <a.apk> [<b.apk>]   (prints the fingerprints; with two APKs: exit 1 unless they match)
"""
import hashlib, struct, sys, zipfile

SCHEMES = {0x7109871a: 'v2', 0xf05368c0: 'v3', 0x1b93ad61: 'v3.1'}


def _lp(buf, off):
    n = struct.unpack_from('<I', buf, off)[0]
    return buf[off + 4:off + 4 + n], off + 4 + n


def _seq(buf):
    off, out = 0, []
    while off < len(buf):
        item, off = _lp(buf, off)
        out.append(item)
    return out


def _der(buf, off):
    """-> (tag, content start, content end) of the DER element at off."""
    tag, n = buf[off], buf[off + 1]
    off += 2
    if n & 0x80:
        k = n & 0x7f
        n = int.from_bytes(buf[off:off + k], 'big')
        off += k
    return tag, off, off + n


def _children(buf, start, end):
    out = []
    while start < end:
        tag, s, e = _der(buf, start)
        out.append((tag, start, s, e))
        start = e
    return out


def _pkcs7_certs(sig):
    """X.509 certificates (DER) inside a PKCS#7 SignedData blob (a v1 META-INF/*.RSA file)."""
    _, s, e = _der(sig, 0)                                  # ContentInfo
    ci = _children(sig, s, e)
    _, s, e = _der(sig, ci[1][2])                           # [0] EXPLICIT -> SignedData
    for tag, start, s2, e2 in _children(sig, s, e):
        if tag == 0xa0:                                     # certificates [0] IMPLICIT
            return [sig[st:en] for _, st, _, en in _children(sig, s2, e2)]
    return []


def fingerprints(path):
    """{'v1': [...], 'v2': [...], 'v3': [...]} -> SHA-256 hex digests of the signer certificates."""
    res = {}
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.startswith('META-INF/') and n.count('/') == 1 and n.upper().endswith(('.RSA', '.DSA', '.EC')):
                res.setdefault('v1', []).extend(hashlib.sha256(c).hexdigest() for c in _pkcs7_certs(z.read(n))[:1])
    data = open(path, 'rb').read()
    eocd = data.rfind(b'PK\x05\x06', max(0, len(data) - 65557))
    cd = struct.unpack_from('<I', data, eocd + 16)[0]
    if data[cd - 16:cd] != b'APK Sig Block 42':
        return res
    size = struct.unpack_from('<Q', data, cd - 24)[0]
    off, end = cd - size - 8 + 8, cd - 24
    while off < end:
        n, bid = struct.unpack_from('<QI', data, off)
        val = data[off + 12:off + 8 + n]
        off += 8 + n
        if bid not in SCHEMES:
            continue
        signers, _ = _lp(val, 0)
        for signer in _seq(signers):
            signed, _ = _lp(signer, 0)
            _digests, o = _lp(signed, 0)
            certs, _ = _lp(signed, o)
            res.setdefault(SCHEMES[bid], []).extend(hashlib.sha256(c).hexdigest() for c in _seq(certs)[:1])
    return res


def pretty(h):
    return ':'.join(h[i:i + 2] for i in range(0, len(h), 2)).upper()


def same_signer(orig, new):
    """True when every signature scheme in `new` is signed by the same certificate(s) as `orig`."""
    want = {h for v in orig.values() for h in v}
    got = {h for v in new.values() for h in v}
    return bool(got) and got == want


if __name__ == '__main__':
    fps = [fingerprints(p) for p in sys.argv[1:3]]
    for p, f in zip(sys.argv[1:3], fps):
        print(p)
        for k in sorted(f):
            for h in f[k]:
                print(f'  {k}: {pretty(h)}')
    if len(fps) == 2:
        ok = same_signer(fps[0], fps[1])
        print('same signing certificate' if ok else 'DIFFERENT signing certificate')
        sys.exit(0 if ok else 1)
