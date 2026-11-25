"""Grey's own sounds (the rest are the game's): digital glitch stutter, clone chirp, ice crack,
and the SYSTEM CRASH blast."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sfx import SR, env, lowpass, bandnoise, write_ogg   # ../sfx.py (Jeff's helpers)

rng = np.random.default_rng(1007)


def crush(x, bits=4, hold=6):
    """bit-crush + sample-and-hold: the "digital" texture."""
    q = 2 ** bits
    y = np.round(np.clip(x, -1, 1) * q) / q
    return np.repeat(y[::hold], hold)[:len(x)]


def glitch(dur=0.34):
    n = int(SR * dur); t = np.arange(n) / SR
    out = np.zeros(n)
    p = 0
    while p < n - 200:                                   # stuttering chunks of buzz and noise
        m = int(rng.uniform(0.012, 0.045) * SR)
        f = rng.choice([220, 330, 440, 880, 1760]) * rng.uniform(0.9, 1.1)
        seg = np.sign(np.sin(2 * np.pi * f * np.arange(m) / SR)) * 0.5 + rng.standard_normal(m) * 0.25
        out[p:p + m] += seg[:max(0, min(m, n - p))] * rng.uniform(0.4, 1.0)
        p += m + int(rng.uniform(0, 0.02) * SR)
    return crush(out * env(n, 0.001, dur * 0.45), 3, 5) * 0.8


def clone(dur=0.42):
    n = int(SR * dur); t = np.arange(n) / SR
    f = 300 + 2400 * (t / dur) ** 1.5                     # rising chirp, doubled
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = (np.sign(np.sin(ph)) * 0.35 + np.sin(ph * 2.01) * 0.3) * env(n, 0.005, dur * 0.5)
    return crush(x, 4, 3) * 0.9


def ice(dur=0.5):
    n = int(SR * dur); t = np.arange(n) / SR
    out = bandnoise(n, 3000, 12000) * env(n, 0.0005, 0.05) * 1.6
    for f in (2100, 3170, 4420, 5900):                   # glassy ringing
        out += np.sin(2 * np.pi * f * t) * env(n, 0.001, rng.uniform(0.1, 0.25)) * 0.22
    out += np.sin(2 * np.pi * 70 * t) * env(n, 0.001, 0.06) * 0.6
    return out


def crash(dur=1.8):
    n = int(SR * dur); t = np.arange(n) / SR
    boom = lowpass(rng.standard_normal(n), 300) * env(n, 0.002, 0.7) * 4
    sub = np.sin(2 * np.pi * (60 - 25 * t / dur) * t) * env(n, 0.002, 0.9) * 0.9
    dig = crush(bandnoise(n, 400, 6000) * env(n, 0.001, 0.35), 2, 9) * 0.9
    return np.tanh((boom + sub + dig) * 1.3) * 0.9


def build(out):
    write_ogg(glitch(), os.path.join(out, 'grey_glitch.ogg'))
    write_ogg(clone(), os.path.join(out, 'grey_clone.ogg'))
    write_ogg(ice(), os.path.join(out, 'grey_ice.ogg'))
    write_ogg(crash(), os.path.join(out, 'grey_crash.ogg'))
