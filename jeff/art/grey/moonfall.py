"""MOONFALL - Grey's ultimate: realistic renders for the Earth-Moon collision and the lava world.

Everything is rendered physically-inspired in numpy (no hand-painted pixels):
* earth          - sphere with domain-warped continents, biomes by latitude/elevation, oceans with
                   a sun glint, a cloud deck, a soft terminator with a twilight band, city lights on
                   the night side and Rayleigh-blue limb scattering (in and outside the disc).
* earth_melt     - the crust wave sweeping the planet from the impact, 5 frames: inside the front the
                   crust is broken into plates, every crack glowing on a blackbody ramp, a white-hot
                   impact basin, ash lit from below; at the front incandescent upheaved crust, just
                   ahead a dark curtain of ejecta; the halo turns orange where the limb has melted.
* earth_top      - the top of the same planet at 4.3x the detail: the horizon as the camera clears
                   the atmosphere (lines up exactly with `earth` drawn at the same size).
* glow           - a soft radial bloom sprite.
* moon           - Lommel-Seeliger reflectance (the real Moon's flat, crisp-terminator look), maria,
                   a power-law crater field (bowls, rims, central peaks, ejecta, rays), earthshine.
                   Frame 1: the same Moon breaking up at the Roche limit (fissures on the Earth side).
* stars          - magnitude-distributed stars coloured by temperature, a dusty Milky Way band.
* plume          - the incandescent silicate-vapour plume, 10 frames of a turbulent expanding cloud,
                   cooling from white-hot to smoke.
* rocks          - lit moon-rock debris.
* lava_sky / lava_far / lava_mid / lava_crust - the destroyed world afterwards (the strips tile).

All bodies share one sun direction, so the shots composite consistently.
"""
import math
import numpy as np
from PIL import Image

SUN = np.array([-0.55, -0.42, 0.72], np.float32)          # view space: x right, y down, z to the viewer
SUN /= np.linalg.norm(SUN)

# --------------------------------------------------------------------------------------------
# noise: vectorised 3D gradient noise + fBm
# --------------------------------------------------------------------------------------------
_RNG = np.random.default_rng(20261125)
_PERM = np.concatenate([_RNG.permutation(256)] * 2).astype(np.int64)
_GRAD = np.array([[1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0], [1, 0, 1], [-1, 0, 1], [1, 0, -1], [-1, 0, -1],
                  [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1]], np.float32)


def perlin(x, y, z):
    xi, yi, zi = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64), np.floor(z).astype(np.int64)
    xf, yf, zf = (x - xi).astype(np.float32), (y - yi).astype(np.float32), (z - zi).astype(np.float32)
    xi &= 255; yi &= 255; zi &= 255
    fade = lambda t: t * t * t * (t * (t * 6 - 15) + 10)
    u, v, w = fade(xf), fade(yf), fade(zf)

    def g(i, j, k, dx, dy, dz):
        h = _PERM[_PERM[_PERM[(xi + i) & 255] + ((yi + j) & 255)] + ((zi + k) & 255)] % 12
        gv = _GRAD[h]
        return gv[..., 0] * dx + gv[..., 1] * dy + gv[..., 2] * dz

    n000 = g(0, 0, 0, xf, yf, zf); n100 = g(1, 0, 0, xf - 1, yf, zf)
    n010 = g(0, 1, 0, xf, yf - 1, zf); n110 = g(1, 1, 0, xf - 1, yf - 1, zf)
    n001 = g(0, 0, 1, xf, yf, zf - 1); n101 = g(1, 0, 1, xf - 1, yf, zf - 1)
    n011 = g(0, 1, 1, xf, yf - 1, zf - 1); n111 = g(1, 1, 1, xf - 1, yf - 1, zf - 1)
    x00 = n000 + u * (n100 - n000); x10 = n010 + u * (n110 - n010)
    x01 = n001 + u * (n101 - n001); x11 = n011 + u * (n111 - n011)
    y0 = x00 + v * (x10 - x00); y1 = x01 + v * (x11 - x01)
    return y0 + w * (y1 - y0)


def fbm(x, y, z, octaves=6, lac=2.0, gain=0.5, ridged=False):
    tot = np.zeros(np.shape(x), np.float32); amp, f, norm = 1.0, 1.0, 0.0
    for o in range(octaves):
        n = perlin(x * f + o * 17.3, y * f - o * 9.1, z * f + o * 5.7)
        if ridged:
            n = 1 - np.abs(n) * 1.6
        tot += n * amp; norm += amp; amp *= gain; f *= lac
    return tot / norm


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def tonemap(c, exposure=1.0):
    c = 1 - np.exp(-np.maximum(c, 0) * exposure)
    return np.power(np.clip(c, 0, 1), 1 / 2.2)


def to_img(rgb, alpha):
    a = np.dstack([np.clip(rgb, 0, 1) * 255, np.clip(alpha, 0, 1)[..., None] * 255]).astype(np.uint8)
    return Image.fromarray(a, 'RGBA')


def sphere(D, r, crop=None):
    """unit-sphere normals for a disc of radius r px centred in a D x D image (or a crop x0,y0,w,h of it)."""
    x0, y0, w, h = crop if crop else (0, 0, D, D)
    yy, xx = np.mgrid[y0:y0 + h, x0:x0 + w].astype(np.float32) + 0.5
    nx, ny = (xx - D / 2) / r, (yy - D / 2) / r
    rr = nx * nx + ny * ny
    nz = np.sqrt(np.clip(1 - rr, 0, 1))
    edge = np.clip((1 - np.sqrt(rr)) * r + 0.5, 0, 1)        # analytic anti-aliased rim
    return nx, ny, nz, rr, edge


def rot(nx, ny, nz, tilt=0.41, spin=2.1):
    """view space -> planet-fixed coordinates (axial tilt, then spin)."""
    c, s = math.cos(tilt), math.sin(tilt)
    x1, y1 = c * nx - s * ny, s * nx + c * ny
    c2, s2 = math.cos(spin), math.sin(spin)
    return c2 * x1 + s2 * nz, y1, -s2 * x1 + c2 * nz


def blackbody(t):
    """0 = cold -> dark red -> orange -> yellow -> white-hot (approximate Planck colours)."""
    t = np.clip(t, 0, None)[..., None]
    stops = np.array([0.0, 0.25, 0.55, 0.9, 1.3, 1.8, 2.4], np.float32)
    cols = np.array([[0, 0, 0], [0.30, 0.02, 0.0], [0.85, 0.12, 0.01], [1.0, 0.40, 0.05],
                     [1.0, 0.70, 0.25], [1.0, 0.92, 0.65], [1.0, 1.0, 0.95]], np.float32)
    out = np.zeros(t.shape[:-1] + (3,), np.float32)
    tt = t[..., 0]
    for i in range(len(stops) - 1):
        m = (tt >= stops[i]) & (tt < stops[i + 1])
        u = ((tt - stops[i]) / (stops[i + 1] - stops[i]))[..., None]
        out = np.where(m[..., None], cols[i] + (cols[i + 1] - cols[i]) * u, out)
    out = np.where((tt >= stops[-1])[..., None], cols[-1], out)
    return out


# --------------------------------------------------------------------------------------------
# Earth
# --------------------------------------------------------------------------------------------
EARTH_D, EARTH_R = 512, 236          # disc radius 236 px, the rest is atmosphere glow


def _earth_fields(D=EARTH_D, R=EARTH_R, crop=None):
    nx, ny, nz, rr, edge = sphere(D, R, crop)
    inside = rr <= 1.0
    px, py, pz = rot(nx, ny, nz)
    wx = fbm(px * 1.3, py * 1.3, pz * 1.3, 4) * 0.45
    wy = fbm(px * 1.3 + 7, py * 1.3, pz * 1.3, 4) * 0.45
    wz = fbm(px * 1.3, py * 1.3 + 3, pz * 1.3, 4) * 0.45
    h = fbm(px * 1.6 + wx, py * 1.6 + wy, pz * 1.6 + wz, 7)
    return dict(nx=nx, ny=ny, nz=nz, rr=rr, edge=edge, inside=inside, px=px, py=py, pz=pz, h=h, R=R)


_SEA = {}


def _sea_level():
    """the sea level is fixed once from the 512 px render, so every resolution has the same coasts."""
    if 'sea' not in _SEA:
        F = _earth_fields()
        hin = F['h'][F['inside']]
        _SEA['sea'], _SEA['lo'], _SEA['hi'] = np.percentile(hin, 69), hin.min(), hin.max()   # ~31 % land
    return _SEA['sea'], _SEA['lo'], _SEA['hi']


def _earth_rgb(F):
    nx, ny, nz, inside, px, py, pz, h, R = (F[k] for k in ('nx', 'ny', 'nz', 'inside', 'px', 'py', 'pz', 'h', 'R'))
    sea, lo, hi = _sea_level()
    land = smooth(sea - 0.004, sea + 0.004, h)
    elev = np.clip((h - sea) / (hi - sea + 1e-6), 0, 1)
    depth = np.clip((sea - h) / (sea - lo + 1e-6), 0, 1)
    lat = np.abs(py)                                         # planet y is the spin axis
    dry = fbm(px * 2.2 + 11, py * 2.2, pz * 2.2, 4)
    # oceans: shallow turquoise shelves -> deep navy
    shelf = 1 - smooth(0.0, 0.07, depth)
    ocean = (np.array([0.035, 0.13, 0.21]) * shelf[..., None]
             + np.array([0.008, 0.028, 0.085]) * (1 - shelf)[..., None])
    # land biomes
    green = np.array([0.10, 0.22, 0.06]); forest = np.array([0.05, 0.14, 0.04])
    desert = np.array([0.56, 0.44, 0.27]); rock = np.array([0.33, 0.29, 0.24]); snow = np.array([0.88, 0.9, 0.93])
    veg = green + (forest - green) * smooth(0.0, 0.5, fbm(px * 4, py * 4, pz * 4, 4))[..., None]
    desert_w = smooth(-0.05, 0.3, dry) * smooth(0.10, 0.20, lat) * (1 - smooth(0.42, 0.58, lat))
    col_land = veg + (desert - veg) * desert_w[..., None]
    col_land = col_land + (rock - col_land) * smooth(0.45, 0.7, elev)[..., None]
    col_land = col_land + (snow - col_land) * smooth(0.78, 0.9, elev)[..., None]
    ice = smooth(0.80, 0.86, lat + 0.06 * fbm(px * 6, py * 6, pz * 6, 3))
    alb = ocean + (col_land - ocean) * land[..., None]
    alb = alb + (snow - alb) * ice[..., None]
    # clouds: a warped deck, storm tracks at mid latitudes, few over the deserts
    cx, cy, cz = px * 2 + wxy(px, py, pz), py * 2, pz * 2
    c = fbm(cx * 1.6, cy * 2.4, cz * 1.6, 6)
    band = 0.55 + 0.25 * np.cos(lat * 7.5) - 0.25 * desert_w * land
    cloud = smooth(0.02, 0.36, c * band + 0.06) * 0.92
    # lighting
    ndl = nx * SUN[0] + ny * SUN[1] + nz * SUN[2]
    day = smooth(-0.10, 0.20, ndl)
    diff = np.clip(ndl, 0, 1) ** 0.85
    hy_, hx_ = np.gradient(np.where(inside, h, 0))                  # hillshade the relief (per Earth radius)
    relief = np.clip(1 - (hx_ * SUN[0] + hy_ * SUN[1]) * 95 * (R / EARTH_R) * land, 0.55, 1.45)
    col = alb * (0.025 + 1.15 * diff)[..., None] * relief[..., None]
    col = col + (np.array([0.97, 0.97, 0.98]) * (0.025 + 1.2 * diff)[..., None] - col) * cloud[..., None]
    hv = SUN + np.array([0, 0, 1], np.float32); hv /= np.linalg.norm(hv)
    ndh = np.clip(nx * hv[0] + ny * hv[1] + nz * hv[2], 0, 1)
    waves = 0.55 + 0.45 * smooth(-0.2, 0.5, fbm(px * 22, py * 22, pz * 22, 3))
    spec = ndh ** 38 * 0.32 * waves * (1 - land) * (1 - cloud) ** 2 * day
    col = col + spec[..., None] * np.array([1.0, 0.95, 0.85])
    twi = np.exp(-((ndl - 0.03) / 0.09) ** 2)                # sunset band along the terminator
    col = col * (1 + twi[..., None] * np.array([0.45, 0.05, -0.25]))
    # city lights on the night side
    lights = (smooth(0.62, 0.8, fbm(px * 38, py * 38, pz * 38, 2)) * smooth(0.05, 0.35, fbm(px * 5, py * 5, pz * 5, 3))
              * land * (1 - ice) * (1 - smooth(0.0, 0.2, ndl)) * (1 - cloud * 0.7))
    col = col + lights[..., None] * np.array([1.0, 0.72, 0.32]) * 0.9
    # Rayleigh scattering: the limb turns blue on the day side
    fres = (1 - nz) ** 2.4
    sky = np.array([0.30, 0.52, 1.0])
    col = col * (1 - fres * 0.5 * day)[..., None] + sky * (fres * 0.85 * day)[..., None]
    col = col + np.array([0.012, 0.025, 0.06]) * day[..., None]
    return tonemap(col, 1.35)


def wxy(px, py, pz):
    return fbm(px * 3 + 5, py * 3, pz * 3, 3) * 0.6


def _glow_lit(F):
    """how sunlit the atmosphere above each rim point is (outside the disc)."""
    nx, ny, rr = F['nx'], F['ny'], F['rr']
    l2 = math.hypot(SUN[0], SUN[1])
    dot2 = (nx * SUN[0] + ny * SUN[1]) / (np.sqrt(rr) + 1e-6) / l2
    return smooth(-0.55, 0.65, dot2) * 0.9 + 0.1


def _compose(F, rgb, gcol, glow):
    """the disc over its atmosphere: gcol (3 or HxWx3) and glow (HxW, the halo's brightness outside the rim)."""
    rr, edge, inside, R = F['rr'], F['edge'], F['inside'], F['R']
    d = (np.sqrt(rr) - 1) * R                                 # px outside the rim
    halo = np.where(rr > 1, np.exp(-np.maximum(d, 0) / (5.0 * R / EARTH_R)) * glow, 0)
    disc = np.where(inside, edge, 0)
    alpha = disc + halo * (1 - disc)
    out = rgb * disc[..., None] + np.clip(gcol, 0, 1) * (1 - disc[..., None])
    return to_img(out, alpha)


def earth(k=0, n=1):
    F = _earth_fields()
    return _compose(F, _earth_rgb(F), np.array([0.35, 0.6, 1.0]), _glow_lit(F))


IMPACT_N = np.array([0.66, -0.50, 0.56], np.float32)          # where the Moon hits (upper right, visible)
IMPACT_N /= np.linalg.norm(IMPACT_N)


def _impact_angle(F):
    nx, ny, nz = F['nx'], F['ny'], F['nz']
    return np.arccos(np.clip(nx * IMPACT_N[0] + ny * IMPACT_N[1] + nz * IMPACT_N[2], -1, 1))


def _molten_rgb(F):
    nx, ny, nz, px, py, pz = (F[k] for k in ('nx', 'ny', 'nz', 'px', 'py', 'pz'))
    ang = _impact_angle(F)
    # crust plates (Voronoi borders on the sphere) + a finer crack net (ridged noise)
    rng = np.random.default_rng(77)
    seeds = rng.normal(size=(110, 3)); seeds /= np.linalg.norm(seeds, axis=1, keepdims=True)
    wq = 0.16
    qx = px + wq * fbm(px * 3, py * 3, pz * 3, 4); qy = py + wq * fbm(px * 3 + 9, py * 3, pz * 3, 4)
    qz = pz + wq * fbm(px * 3, py * 3 + 5, pz * 3, 4)
    P = np.stack([qx, qy, qz], -1).reshape(-1, 3)
    d1 = np.full(P.shape[0], 9.0, np.float32); d2 = np.full(P.shape[0], 9.0, np.float32)
    for s_ in seeds:
        d = np.sum((P - s_) ** 2, axis=1)
        nd2 = np.minimum(d2, np.maximum(d1, d)); d1 = np.minimum(d1, d); d2 = nd2
    border = (np.sqrt(d2) - np.sqrt(d1)).reshape(px.shape)
    width = 0.010 + 0.022 * smooth(-0.3, 0.6, fbm(px * 5, py * 5, pz * 5, 3))
    plates = 1 - smooth(0.0, 1.0, border / width)
    fine = smooth(0.80, 0.97, fbm(px * 7, py * 7, pz * 7, 4, ridged=True))
    edge_n = 0.22 * fbm(px * 3, py * 3, pz * 3, 4)
    basin = np.exp(-((ang + edge_n) / 0.62) ** 2)             # the molten impact basin
    near = np.exp(-((ang) / 1.35) ** 2)
    T = basin * 2.4 + plates * (0.32 + 1.15 * near) + fine * (0.08 + 0.55 * near) * (1 - plates)
    T = T + 0.25 * basin * fbm(px * 10, py * 10, pz * 10, 3)
    emit = blackbody(T)
    # dark basalt crust lit by the sun
    ndl = nx * SUN[0] + ny * SUN[1] + nz * SUN[2]
    diff = np.clip(ndl, 0, 1) ** 0.85
    crust = np.array([0.030, 0.024, 0.021]) * (1 + 0.5 * fbm(px * 9, py * 9, pz * 9, 3))[..., None]
    col = crust * (0.03 + 1.1 * diff)[..., None] + emit * 1.25
    # ash clouds, lit from below by the glow
    ash = smooth(0.05, 0.5, fbm(px * 2.6 + 3, py * 3.4, pz * 2.6, 5)) * 0.55 * (1 - basin * 0.7)
    ash_col = np.array([0.045, 0.038, 0.034]) * (0.1 + diff)[..., None] + emit * 0.28
    col = col * (1 - ash[..., None]) + ash_col * ash[..., None]
    fres = (1 - nz) ** 2.2
    col = col + np.array([0.9, 0.3, 0.06]) * (fres * 0.45 * (0.25 + 0.75 * near))[..., None]
    return col, ang, near


MELT = [0.35, 0.85, 1.45, 2.2, 3.5]                           # angular radius of the melt (rad) per frame


def earth_melt(k=0, n=len(MELT)):
    """the crust wave racing round the globe from the impact: frame k has melted out to MELT[k] radians.
    Inside: the molten world. At the front: upheaved, incandescent crust. Just ahead: the dark curtain of
    ejecta and smoke it throws up. Outside: the planet as it was."""
    F = _earth_fields()
    day = _earth_rgb(F)
    col, ang, near = _molten_rgb(F)
    th = MELT[k]
    px, py, pz = F['px'], F['py'], F['pz']
    rag = 0.10 * fbm(px * 4 + 2, py * 4, pz * 4, 4) * min(1.0, th / 0.6)   # a ragged front
    a = ang + rag
    inside = smooth(th + 0.03, th - 0.06, a)
    front = np.exp(-((a - th + 0.015) / 0.045) ** 2)
    storm = np.where(a < th, np.exp(-(th - a) / 0.22), 0)    # the firestorm just behind it
    col = col + blackbody(front * 2.3 + storm * 0.9) * 1.3 * (front + storm * 0.6)[..., None]
    molten = tonemap(col, 1.25)
    curtain = np.exp(-((a - th - 0.06) / 0.05) ** 2) * (th < 3.2)
    day = day * (1 - 0.45 * curtain)[..., None] + np.array([0.07, 0.05, 0.04]) * (0.45 * curtain)[..., None]
    rgb = day * (1 - inside[..., None]) + molten * inside[..., None]
    # the halo: blue where the limb is untouched, orange where it has melted
    nx, ny = F['nx'], F['ny']
    rim_n = np.sqrt(F['rr']) + 1e-6
    rim_ang = np.arccos(np.clip((nx * IMPACT_N[0] + ny * IMPACT_N[1]) / rim_n, -1, 1))
    hot_rim = smooth(th + 0.05, th - 0.2, rim_ang)
    lit = _glow_lit(F)
    gcol = np.array([0.35, 0.6, 1.0]) * (1 - hot_rim[..., None]) + np.array([1.0, 0.42, 0.10]) * hot_rim[..., None]
    glow = lit * (1 - hot_rim) + 1.35 * np.maximum(lit, smooth(-0.2, 0.9, (nx * IMPACT_N[0] + ny * IMPACT_N[1]) / rim_n)) * hot_rim
    return _compose(F, rgb, gcol, glow)


TOP_R, TOP_M, TOP_W, TOP_H = 1024, 96, 1664, 472             # the horizon crop: a 1024 px radius Earth


def earth_top(k=0, n=1):
    """the top of the planet at 4.3x the detail (radius 1024 px): the horizon as the camera clears the
    atmosphere. Same planet, same sun as `earth`, so the two line up exactly when drawn at the same size."""
    D = 2 * (TOP_R + TOP_M)
    crop = (D // 2 - TOP_W // 2, 0, TOP_W, TOP_H)
    F = _earth_fields(D, TOP_R, crop)
    im = _compose(F, _earth_rgb(F), np.array([0.35, 0.6, 1.0]), _glow_lit(F))
    a = np.asarray(im).copy()                                 # the halo fades out before the crop's top edge
    a[..., 3] = (a[..., 3] * smooth(0, 40, np.arange(TOP_H, dtype=np.float32) + 0.5)[:, None]).astype(np.uint8)
    return Image.fromarray(a, 'RGBA')


# --------------------------------------------------------------------------------------------
# Moon
# --------------------------------------------------------------------------------------------
MOON_D, MOON_R = 256, 124
# The Moon sprite is drawn rotated by MOON_ROT degrees so its local +x points away from the Earth: then a
# tidal stretch is just an x-scale. It is lit with the sun turned into that local frame, so on screen the
# light still comes from SUN, like every other body.
MOON_ROT = math.degrees(math.atan2(-IMPACT_N[1], IMPACT_N[0]))
_cr, _sr = math.cos(math.radians(MOON_ROT)), math.sin(math.radians(MOON_ROT))
SUN_L = np.array([_cr * SUN[0] - _sr * SUN[1], _sr * SUN[0] + _cr * SUN[1], SUN[2]], np.float32)
_EN = -IMPACT_N                                               # towards the Earth, in screen space ...
EARTH_L = np.array([_cr * _EN[0] - _sr * _EN[1], _sr * _EN[0] + _cr * _EN[1], _EN[2]], np.float32)   # ... and local


def _moon_base(seed=5):
    nx, ny, nz, rr, edge = sphere(MOON_D, MOON_R)
    inside = rr <= 1.0
    px, py, pz = rot(nx, ny, nz, tilt=0.1, spin=0.7)
    rng = np.random.default_rng(seed)
    H = np.zeros(nx.shape, np.float32)
    alb = 0.74 + 0.05 * fbm(px * 6, py * 6, pz * 6, 4)
    maria = smooth(0.0, 0.14, fbm(px * 1.5 + 4, py * 1.5, pz * 1.5, 5))
    alb = alb * (1 - 0.56 * maria)
    # crater field: power-law radii, uniform on the sphere; profiles on the sphere (exact foreshortening)
    N = 650
    v = rng.normal(size=(N, 3)); v /= np.linalg.norm(v, axis=1, keepdims=True)
    R = np.clip(0.012 * (1 - rng.random(N)) ** (-1 / 1.55), 0.012, 0.32)   # angular radius (radians)
    young = rng.random(N) < 0.025
    # rotate crater centres into view space (inverse of rot is not needed: generate in view space)
    for i in range(N):
        c = v[i]
        if c[2] < -0.15:
            continue
        cxp, cyp = MOON_D / 2 + c[0] * MOON_R, MOON_D / 2 + c[1] * MOON_R
        span = (R[i] * 3.2) * MOON_R + 3
        x0, x1 = int(max(0, cxp - span)), int(min(MOON_D, cxp + span + 1))
        y0, y1 = int(max(0, cyp - span)), int(min(MOON_D, cyp + span + 1))
        if x1 <= x0 or y1 <= y0:
            continue
        sx, sy, sz = nx[y0:y1, x0:x1], ny[y0:y1, x0:x1], nz[y0:y1, x0:x1]
        a = np.arccos(np.clip(sx * c[0] + sy * c[1] + sz * c[2], -1, 1))
        s = a / R[i]
        depth = R[i] * MOON_R * 0.22
        prof = np.where(s < 1, -(1 - s * s), 0) * depth
        prof += 0.16 * depth * np.exp(-((s - 1) / 0.13) ** 2)
        prof += 0.05 * depth * np.where(s > 1, np.exp(-(s - 1) / 0.7), 0)
        if R[i] > 0.09:
            prof += 0.22 * depth * np.exp(-(s / 0.16) ** 2)
        H[y0:y1, x0:x1] += prof * (rr[y0:y1, x0:x1] <= 1)
        ej = np.where(s > 0.9, np.exp(-(s - 0.9) / 0.9), 0) * 0.08
        if young[i]:
            th = np.arctan2(sy - c[1], sx - c[0])
            rays = np.clip(np.cos(th * 9 + i) * 0.5 + np.cos(th * 23 + 2 * i) * 0.5, 0, 1) ** 3
            ej = ej + rays * np.where(s > 0.8, np.exp(-(s - 0.8) / 4.5), 0) * 0.35
        alb[y0:y1, x0:x1] += ej
    H += 0.6 * fbm(px * 30, py * 30, pz * 30, 3)              # regolith bumps
    return nx, ny, nz, rr, edge, inside, px, py, pz, H, np.clip(alb, 0.2, 1.1)


def moon(k=0, n=2):
    nx, ny, nz, rr, edge, inside, px, py, pz, H, alb = _moon_base()
    Hm = np.where(inside, H, 0)
    gy, gx = np.gradient(Hm)
    rim = smooth(0.995, 0.9, np.sqrt(rr))                    # no slope across the disc edge
    gx, gy = gx * rim, gy * rim
    sxn, syn, szn = nx - gx * 1.15, ny - gy * 1.15, nz.copy()
    ln = np.sqrt(sxn ** 2 + syn ** 2 + szn ** 2) + 1e-6
    sxn, syn, szn = sxn / ln, syn / ln, szn / ln
    mu0 = np.clip(sxn * SUN_L[0] + syn * SUN_L[1] + szn * SUN_L[2], 0, 1)
    mu = np.clip(szn, 0.12, 1)
    ls = 2 * mu0 / (mu0 + mu + 1e-4) * smooth(0.0, 0.07, mu0)   # Lommel-Seeliger, no grazing blow-up
    col = alb[..., None] * ls[..., None] * np.array([0.82, 0.80, 0.77])
    col = col * (1 + 0.04 * np.array([0, 0.02, 0.05]))
    # earthshine: the night side facing the Earth, lit faintly blue by it
    night = 1 - smooth(-0.02, 0.1, nx * SUN_L[0] + ny * SUN_L[1] + nz * SUN_L[2])
    ne = np.clip(nx * EARTH_L[0] + ny * EARTH_L[1] + nz * EARTH_L[2], 0, 1)
    earthshine = night * (0.012 + 0.07 * ne)
    col = col + earthshine[..., None] * np.array([0.45, 0.6, 1.0]) * alb[..., None]
    if k == 1:                                                # tidal breakup at the Roche limit
        rng = np.random.default_rng(9)
        seeds = rng.normal(size=(11, 3)); seeds /= np.linalg.norm(seeds, axis=1, keepdims=True)
        qx = nx + 0.13 * fbm(nx * 4, ny * 4, nz * 4, 4); qy = ny + 0.13 * fbm(nx * 4 + 5, ny * 4, nz * 4, 4)
        P = np.stack([qx, qy, nz], -1).reshape(-1, 3)
        d1 = np.full(P.shape[0], 9.0, np.float32); d2 = np.full(P.shape[0], 9.0, np.float32)
        for s in seeds:
            d = np.sum((P - s) ** 2, axis=1)
            nd2 = np.minimum(d2, np.maximum(d1, d)); d1 = np.minimum(d1, d); d2 = nd2
        border = (np.sqrt(d2) - np.sqrt(d1)).reshape(nx.shape)
        earthward = smooth(-0.4, 0.9, -nx)                    # the side facing Earth (local -x)
        w = (0.006 + 0.032 * earthward) * (0.5 + 0.9 * smooth(-0.3, 0.5, fbm(nx * 6, ny * 6, nz * 6, 3)))
        crack = 1 - smooth(0.0, 1.0, border / w)
        lip = (1 - smooth(0.0, 1.0, border / (w * 1.9))) - crack    # shadowed lips beside each gap
        col = col * (1 - crack[..., None] * 0.85) * (1 - lip[..., None] * 0.3)
        deep = crack * smooth(0.5, 1.0, earthward) * smooth(0.6, 1.0, crack)
        col = col + blackbody(deep * 0.75) * 0.55
    rgb = tonemap(col * 1.25, 1.0)
    return to_img(rgb, np.where(inside, edge, 0))


# --------------------------------------------------------------------------------------------
# the sky, the plume, the debris
# --------------------------------------------------------------------------------------------
def stars(k=0, n=1, W=640, H=360):
    rng = np.random.default_rng(31)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    col = np.zeros((H, W, 3), np.float32) + np.array([0.006, 0.008, 0.016])
    band_c = (yy - (H * 0.78 - xx * 0.42)) / (H * 0.17)
    band = np.exp(-band_c ** 2)
    neb = 0.5 + 0.5 * fbm(xx / 90, yy / 90, 0.3, 5)
    dust = smooth(0.55, 0.85, fbm(xx / 55 + 9, yy / 55, 1.1, 5, ridged=True))
    mw = band * neb * (1 - 0.7 * dust * band)
    col = col + mw[..., None] * np.array([0.10, 0.10, 0.13]) + (band ** 3 * neb)[..., None] * np.array([0.06, 0.05, 0.04])
    temps = np.array([[0.70, 0.80, 1.0], [0.95, 0.96, 1.0], [1.0, 0.94, 0.80], [1.0, 0.80, 0.58], [1.0, 0.66, 0.48]])
    for i in range(2600):
        x, y = rng.random() * W, rng.random() * H
        if rng.random() < 0.45 * band_at(x, y, W, H):
            pass
        b = 0.025 + 0.975 * rng.random() ** 16
        c = temps[rng.choice(5, p=[0.18, 0.32, 0.28, 0.15, 0.07])]
        sig = 0.42 + 0.7 * b
        x0, x1, y0, y1 = int(max(0, x - 4)), int(min(W, x + 5)), int(max(0, y - 4)), int(min(H, y + 5))
        gx, gy = xx[y0:y1, x0:x1] - x, yy[y0:y1, x0:x1] - y
        g = np.exp(-(gx * gx + gy * gy) / (2 * sig * sig)) * b * 2.2
        if b > 0.9:                                           # diffraction spikes on the brightest
            g = g + b * 0.5 * (np.exp(-gy * gy * 6) * np.exp(-np.abs(gx) / 2.5) + np.exp(-gx * gx * 6) * np.exp(-np.abs(gy) / 2.5))
        col[y0:y1, x0:x1] += g[..., None] * c
    return to_img(tonemap(col, 1.4), np.ones((H, W)))


def band_at(x, y, W, H):
    return math.exp(-((y - (H * 0.78 - x * 0.42)) / (H * 0.17)) ** 2)


PLUME = 192


def plume(k, n=10):
    t = k / (n - 1)
    yy, xx = np.mgrid[0:PLUME, 0:PLUME].astype(np.float32) + 0.5
    bx, by = PLUME / 2, PLUME - 12
    R = 14 + 72 * (1 - (1 - t) ** 1.8)                       # fast at first, then slowing (stays in frame)
    dx, dy = (xx - bx) / R, (by - yy) / (R * 1.12)
    q = np.sqrt(dx * dx + np.maximum(dy, 0) ** 2 + np.minimum(dy, 0) ** 2 * 14)
    bill = fbm(xx / 13 + t * 2, yy / 13, t * 1.7, 5, ridged=True)          # cauliflower billows
    turb = 0.16 * fbm(xx / 30, yy / 30, t * 2.2, 4) + 0.10 * (bill - 0.3)
    dens = smooth(1.0, 0.78, q + turb)
    core = np.exp(-(q / (0.45 + 0.25 * t)) ** 2)
    T = (core * (2.8 - 1.7 * t) + 0.45 * (1 - q) * (1.6 - t) + 0.35 * fbm(xx / 11 + 5, yy / 11, t * 3, 3)
         + (1 - t) ** 1.5 * 1.1 * (1 - 0.5 * q))                # young vapour is incandescent right to its edge
    T = np.where(dens > 0, np.clip(T, 0, 2.8), 0)
    fire = blackbody(T)
    shade = 0.5 + 0.5 * smooth(-0.4, 0.6, bill)                 # billow tops lit, folds dark
    smoke = np.array([0.075, 0.05, 0.04]) * shade[..., None]
    hot = smooth(0.25, 1.0, T)[..., None]
    col = smoke * (1 - hot) + fire * hot
    alpha = dens * (0.82 + 0.18 * hot[..., 0]) * (1 - 0.35 * t * (1 - hot[..., 0]))
    alpha = alpha * smooth(PLUME - 1.0, by - 2.0, yy)            # fades out at its base (no straight edge)
    return to_img(tonemap(col * 1.6, 1.0), alpha)


def glow(k=0, n=1, S=64):
    """a soft radial glow: bloom round anything incandescent (drawn additively, tinted)."""
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32) + 0.5
    r = np.hypot(xx - S / 2, yy - S / 2) / (S / 2)
    a = 0.62 * np.exp(-(r / 0.28) ** 2) + 0.38 * np.exp(-(r / 0.62) ** 2)
    a = a * smooth(1.0, 0.86, r)
    return to_img(np.ones((S, S, 3)), a / a.max())


def rocks(k, n=8):
    S = 32
    rng = np.random.default_rng(400 + k)
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32) + 0.5
    dx, dy = xx - S / 2, yy - S / 2
    th = np.arctan2(dy, dx)
    r0 = 10.0 * (1 + 0.42 * fbm(np.cos(th) * 1.6 + k, np.sin(th) * 1.6, k * 0.7, 4))
    d = np.sqrt(dx * dx + dy * dy)
    edge = np.clip(r0 - d + 0.5, 0, 1)
    rn = np.clip(d / (r0 + 1e-3), 0, 1)
    nz = np.sqrt(np.clip(1 - rn ** 2, 0, 1)) + 0.2
    nx, ny = dx / (r0 + 1e-3), dy / (r0 + 1e-3)
    bump = fbm(xx / 4 + k * 3, yy / 4, k, 3)
    nx, ny = nx + 0.3 * bump, ny - 0.3 * bump
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    ndl = np.clip((nx * SUN[0] + ny * SUN[1] + nz * SUN[2]) / ln, 0, 1)
    alb = 0.30 + 0.10 * fbm(xx / 3, yy / 3, k + 9, 3) - 0.08 * (rng.random() < 0.5)
    col = alb[..., None] * (0.02 + ndl[..., None] ** 1.3 * 1.25) * np.array([0.80, 0.77, 0.73])
    return to_img(tonemap(col, 1.3), edge)


# --------------------------------------------------------------------------------------------
# the destroyed world
# --------------------------------------------------------------------------------------------
def _cyl(xx, W, R=3.0):
    a = xx / W * 2 * math.pi
    return np.cos(a) * R, np.sin(a) * R


def lava_sky(k=0, n=1, W=640, H=360):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    v = yy / H
    top, mid, low = np.array([0.010, 0.004, 0.004]), np.array([0.055, 0.014, 0.006]), np.array([0.42, 0.10, 0.02])
    col = top + (mid - top) * smooth(0.0, 0.65, v)[..., None] + (low - mid) * smooth(0.6, 1.0, v)[..., None]
    cx, cz = _cyl(xx, W, 2.2)
    deck = fbm(cx, yy / 26 + 3, cz, 6) + 0.35 * fbm(cx * 3, yy / 9, cz * 3, 3)
    clouds = smooth(0.0, 0.42, deck + 0.2 * (1 - v) - 0.1)
    under = smooth(0.2, 1.0, v)
    cloud_col = np.array([0.020, 0.013, 0.011]) + np.array([0.30, 0.075, 0.016]) * (under ** 1.5)[..., None]
    col = col * (1 - clouds[..., None] * 0.9) + cloud_col * (clouds[..., None] * 0.9)
    ex, ey, ea, eb = W * 0.5, H * 1.5, W * 1.0, H * 1.28       # the Moon's debris ring, arcing overhead
    rd = np.sqrt(((xx - ex) / ea) ** 2 + ((yy - ey) / eb) ** 2)
    grain = 0.25 + 0.75 * smooth(0.45, 0.95, fbm(xx / 2.5, yy / 2.5, 7.1, 2))
    ring = (np.exp(-((rd - 1) / 0.006) ** 2) * grain + np.exp(-((rd - 1) / 0.03) ** 2) * 0.25) * (1 - clouds * 0.85)
    col = col + ring[..., None] * np.array([0.55, 0.36, 0.22])
    rng = np.random.default_rng(12)
    for i in range(90):                                       # embers high in the air
        x, y = rng.random() * W, rng.random() * H * 0.95
        b = rng.random() ** 3
        x0, x1, y0, y1 = int(max(0, x - 2)), int(min(W, x + 3)), int(max(0, y - 2)), int(min(H, y + 3))
        g = np.exp(-((xx[y0:y1, x0:x1] - x) ** 2 + (yy[y0:y1, x0:x1] - y) ** 2) / 1.0) * b
        col[y0:y1, x0:x1] += g[..., None] * np.array([1.0, 0.45, 0.10]) * 0.5
    return to_img(tonemap(col, 1.6), np.ones((H, W)))


def _cyl_iso(xx, W, px_scale):
    R = W / (2 * math.pi * px_scale)                          # one noise unit = px_scale pixels, seamless in x
    a = xx / W * 2 * math.pi
    return np.cos(a) * R, np.sin(a) * R


def _terrain(W, H, base, amp, seed, haze, haze_col, n_rivers, octs=5):
    rng = np.random.default_rng(int(seed * 10))
    xs = np.arange(W, dtype=np.float32) + 0.5
    cx1, cz1 = _cyl_iso(xs, W, 160)
    prof = smooth(-0.6, 0.9, fbm(cx1 + seed, np.full_like(cx1, seed * 0.37), cz1, octs, gain=0.42)) * 0.55
    cx2, cz2 = _cyl_iso(xs, W, 22)
    prof += 0.06 * fbm(cx2, np.full_like(cx2, seed), cz2, 3)
    peaks = []
    for i in range(3):                                         # volcanic cones: rounded, ragged, cratered
        c0, wv, hv = rng.random() * W, 90 + rng.random() * 110, 0.8 + 0.25 * rng.random()
        d = np.minimum(np.abs(xs - c0), W - np.abs(xs - c0))
        u = np.clip(d / wv, 0, 1)
        cone = hv * (1 - u) ** 1.35 * (1 - 0.18 * np.exp(-(d / (wv * 0.09)) ** 2))
        cone *= 1 + 0.12 * fbm(cx2 + i * 3, np.full_like(cx2, i), cz2, 3)
        prof = np.maximum(prof, cone)
        peaks.append((c0, wv))
    top = base - amp * prof
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32) + 0.5
    below = yy - top[None, :]
    alpha = np.clip(below + 0.5, 0, 1)
    tx, tz = _cyl_iso(xx, W, 14)
    tex = fbm(tx + seed, yy / 14, tz, 5)
    tex2 = fbm(tx * 3 + seed, yy / 4.5, tz * 3, 3)
    rock = np.array([0.014, 0.009, 0.008]) * (0.55 + 0.7 * smooth(-0.6, 0.6, tex) + 0.25 * tex2)[..., None]
    rim = np.exp(-np.maximum(below, 0) / 6.0)
    rock = rock * (1 + 1.6 * rim)[..., None]                   # crests catch the red sky glow
    lava = np.zeros_like(yy)
    for i in range(n_rivers):                                  # flows: sinuous, cooling and crusting downstream
        c0, wv = peaks[i % len(peaks)] if rng.random() < 0.8 else (rng.random() * W, 120)
        side = 1 if rng.random() < 0.5 else -1
        x = c0 + side * wv * (0.02 + 0.1 * rng.random())
        y = top[int(x) % W] + 3
        dirx, ph = side * (0.35 + 0.3 * rng.random()), rng.random() * 6.28
        r = 0.8
        for step in range(int(H * 3)):
            if y > H - 2 or y < 0: break
            heat = math.exp(-step / 170.0) * (0.55 + 0.45 * (0.5 + 0.5 * math.sin(step * 0.21 + ph * 3)))
            y0, y1 = int(max(0, y - 2 * r - 1)), int(min(H, y + 2 * r + 2))
            x0, x1 = int(max(0, x - 2 * r - 1)), int(min(W, x + 2 * r + 2))
            if x1 > x0 and y1 > y0:
                gx, gy = xx[y0:y1, x0:x1] - x, yy[y0:y1, x0:x1] - y
                lava[y0:y1, x0:x1] = np.maximum(lava[y0:y1, x0:x1], heat * np.exp(-(gx * gx + gy * gy) / (2 * r * r)))
            dirx += (rng.random() - 0.5) * 0.22
            dirx = side * min(1.0, max(0.12, side * dirx))
            x += dirx + math.sin(step * 0.09 + ph) * 0.55
            y = max(y + 0.45 + 0.35 * rng.random(), top[int(x) % W] + 2.5)
            r = min(2.6, r + 0.01)
    pools = smooth(H - 22, H - 4, yy) * smooth(0.45, 0.85, fbm(tx * 0.6, yy / 30, tz * 0.6, 3))
    lava = np.maximum(lava, pools)
    T = lava * (1.9 + 0.4 * fbm(tx * 2, yy / 5, tz * 2, 2))
    bloom = np.zeros_like(lava)
    for sgm in (2.5, 7.0):                                     # the glow lights the rock around a flow
        k1 = np.exp(-(np.arange(-12, 13) ** 2) / (2 * sgm * sgm)); k1 /= k1.sum()
        g = np.apply_along_axis(lambda m: np.convolve(m, k1, 'same'), 0, lava)
        g = np.apply_along_axis(lambda m: np.convolve(m, k1, 'same'), 1, g)
        bloom += g * (0.5 if sgm < 3 else 0.35)
    col = rock + blackbody(T) * 1.35 + bloom[..., None] * np.array([0.55, 0.13, 0.02])
    col = col * (1 - haze) + np.array(haze_col) * haze
    return to_img(tonemap(col, 1.5), alpha)


def lava_far(k=0, n=1):
    return _terrain(1024, 200, 175, 120, 3.0, 0.22, [0.13, 0.034, 0.012], 7)


def lava_mid(k=0, n=1):
    return _terrain(1024, 140, 132, 80, 8.0, 0.05, [0.06, 0.016, 0.006], 9)


def lava_crust(k=0, n=1, W=256, H=48):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32) + 0.5
    cx, cz = _cyl(xx, W, 2.6)
    tx, tz = _cyl_iso(xx, W, 11)
    rock = np.array([0.018, 0.012, 0.010]) * (0.55 + 0.8 * smooth(-0.6, 0.6, fbm(tx, yy / 11, tz, 5)))[..., None]
    veins = smooth(0.86, 0.97, fbm(cx * 1.8, yy / 9, cz * 1.8, 4, ridged=True)) * smooth(40, 3, yy)
    topglow = np.exp(-yy / 2.2) * (0.5 + 0.5 * smooth(-0.3, 0.5, fbm(cx * 3, 0.5, cz * 3, 3)))
    col = rock + blackbody(veins * 2.1) * 1.2 + blackbody(topglow * 1.6) * 0.9
    col = col * (1 - 0.6 * smooth(30, 48, yy))[..., None]
    return to_img(tonemap(col, 1.5), np.ones((H, W)))


SPRITES = {   # name: (generator, frames, ox, oy)
    'earth': (earth, 1, EARTH_D // 2, EARTH_D // 2),
    'earth_melt': (earth_melt, len(MELT), EARTH_D // 2, EARTH_D // 2),
    'earth_top': (earth_top, 1, TOP_W // 2, TOP_R + TOP_M),
    'moon_big': (moon, 2, MOON_D // 2, MOON_D // 2),
    'stars': (stars, 1, 0, 0),
    'plume': (plume, 10, PLUME // 2, PLUME - 12),
    'rocks': (rocks, 8, 16, 16),
    'glow': (glow, 1, 32, 32),
    'lava_sky': (lava_sky, 1, 0, 0),
    'lava_far': (lava_far, 1, 0, 200),
    'lava_mid': (lava_mid, 1, 0, 140),
    'lava_crust': (lava_crust, 1, 0, 0),
}

if __name__ == '__main__':
    import sys, os, time
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp'
    only = sys.argv[2:]
    os.makedirs(out, exist_ok=True)
    print('MOON_ROT', MOON_ROT)
    for name, (fn, nfr, ox, oy) in SPRITES.items():
        if only and name not in only:
            continue
        t0 = time.time()
        frames = [fn(k, nfr) for k in range(nfr)]
        w, h = frames[0].size
        strip = Image.new('RGBA', (w * nfr, h))
        for i, f in enumerate(frames):
            strip.paste(f, (i * w, 0))
        strip.save(os.path.join(out, f'grey_{name}.png'))
        print(f'{name}: {strip.size} {time.time() - t0:.1f}s')
