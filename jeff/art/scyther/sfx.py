"""Synthesised sounds for Scyther (OGG Vorbis via ffmpeg).  Everything else he plays (hits, generic
whooshes, explosions) is the game's own audio, so he sits in the same soundscape as the roster.

  rip       reality tearing open (the signature of every cut)
  slash     the scythe's metallic shing
  spin      the double scythe twirling / the thrown buzzsaw
  bh        the black hole rumbling and drawing everything in
  collapse  implosion -> boom
  beam      the void lance
  shatter   the multiverse breaking like glass
  ko        the final K.O. boom with a cosmic tail
"""
import os, subprocess, sys, wave
import numpy as np
from scipy.signal import butter, lfilter

SR = 44100
rng = np.random.default_rng(11)


def t_(dur):
    return np.arange(int(SR * dur)) / SR


def bp(x, lo, hi):
    b, a = butter(2, [max(20, lo) / (SR / 2), min(hi, SR / 2 - 100) / (SR / 2)], btype='band')
    return lfilter(b, a, x)


def lp(x, cut):
    b, a = butter(2, cut / (SR / 2))
    return lfilter(b, a, x)


def env(t, a, d):
    return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / d)


def reverb(x, decay=0.35, n=6):
    y = x.copy()
    for i in range(1, n + 1):
        dly = int(SR * (0.029 * i + 0.011 * (i % 3)))
        y[dly:] += x[:-dly] * decay ** i
    return y


def rip(dur=0.75):
    t = t_(dur); n = len(t)
    noise = rng.standard_normal(n)
    # jagged tearing: noise gated by a fast random crackle envelope that sweeps down in pitch
    crackle = (rng.uniform(0, 1, n // 220 + 1) > 0.45).astype(float)
    crackle = np.repeat(crackle, 220)[:n]
    tear = bp(noise, 900, 6000) * crackle * env(t, 0.01, 0.22) * 1.3
    zip_ = bp(noise, 300, 2400) * np.exp(-t * 6) * 0.8
    f = 1800 * np.exp(-t * 5) + 300
    shimmer = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.18 * np.exp(-t * 3.5)
    shimmer += sum(np.sin(2 * np.pi * fr * t) for fr in (1320, 1760, 2637)) * 0.05 * np.exp(-t * 2.5)
    sub = np.sin(2 * np.pi * 60 * t) * 0.35 * np.exp(-t * 8)
    return reverb(tear + zip_ + shimmer + sub, 0.3)


def slash(dur=0.42):
    t = t_(dur); n = len(t)
    sw = bp(rng.standard_normal(n), 1500, 9000) * np.sin(np.pi * np.clip(t / 0.22, 0, 1)) ** 2 * 0.9
    ring = sum(np.sin(2 * np.pi * fr * t + rng.uniform(0, 6)) for fr in (3150, 4200, 5300)) * 0.09 * env(t, 0.03, 0.15)
    return reverb(sw + ring, 0.25)


def spin(dur=0.9):
    t = t_(dur); n = len(t)
    am = 0.5 + 0.5 * np.sin(2 * np.pi * 14 * t)
    w = bp(rng.standard_normal(n), 400, 3500) * am * np.sin(np.pi * t / dur) * 0.9
    hum = np.sin(2 * np.pi * 140 * t + 2 * np.sin(2 * np.pi * 14 * t)) * 0.2 * np.sin(np.pi * t / dur)
    return w + hum


def bh(dur=1.8):
    t = t_(dur); n = len(t)
    f = 38 + 30 * t / dur
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.8
    rumble = lp(rng.standard_normal(n), 180) * 2.2
    suck = bp(rng.standard_normal(n), 300, 2000) * (t / dur) ** 2 * 0.6
    crack = np.zeros(n)
    for _ in range(25):
        p = int(rng.uniform(0, n - 900)); m = int(rng.uniform(150, 800))
        crack[p:p + m] += bp(rng.standard_normal(m), 2000, 8000) * np.hanning(m) * rng.uniform(0.1, 0.35)
    x = (sub + rumble + suck + crack) * np.minimum(1, t / 0.15) * np.minimum(1, (dur - t) / 0.25)
    return np.tanh(x * 1.2)


def collapse(dur=1.6):
    t = t_(dur); n = len(t)
    k = int(SR * 0.45)
    inhale = np.zeros(n)
    tt = t[:k]
    inhale[:k] = bp(rng.standard_normal(k), 400, 5000) * (tt / tt[-1]) ** 3 * 1.2
    boom_t = t[k:] - t[k]
    boom = np.zeros(n)
    f = 80 * np.exp(-boom_t * 2.5) + 30
    boom[k:] = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-boom_t * 2.2) * 1.3
    boom[k:] += bp(rng.standard_normal(n - k), 100, 4000) * np.exp(-boom_t * 6) * 1.2
    return np.tanh(reverb(inhale + boom, 0.3) * 1.3)


def beam(dur=1.2):
    t = t_(dur); n = len(t)
    f = 120 + 380 * (1 - np.exp(-t * 5))
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = (np.sin(ph) + 0.5 * np.sin(2.01 * ph) + 0.3 * np.sign(np.sin(3 * ph))) * 0.35
    x += bp(rng.standard_normal(n), 2500, 9000) * 0.22 * np.exp(-t * 2.5)
    x += np.sin(2 * np.pi * 48 * t) * 0.35
    x = np.tanh(x * 1.6) * np.minimum(1, t / 0.02) * np.minimum(1, (dur - t) / 0.3)
    return x


def shatter(dur=2.2):
    t = t_(dur); n = len(t)
    out = np.zeros(n)
    k = int(SR * 0.06)
    out[:k] += bp(rng.standard_normal(k), 1500, 12000) * np.linspace(1, 0, k) * 2.0
    for _ in range(140):                                    # glass fragments
        p = int(rng.uniform(0, SR * 1.3)); m = int(rng.uniform(300, 2500))
        if p + m < n:
            tt = np.arange(m) / SR
            fr = rng.uniform(2500, 9000)
            out[p:p + m] += np.sin(2 * np.pi * fr * tt) * np.exp(-tt * rng.uniform(20, 60)) * rng.uniform(0.05, 0.25)
    boom = np.sin(2 * np.pi * (60 * np.exp(-t * 3) + 28) * t) * np.exp(-t * 2.5) * 0.9
    return np.tanh(reverb(out + boom, 0.4, 8) * 1.2)


def ko(dur=2.0):
    t = t_(dur); n = len(t)
    f = 70 * np.exp(-t * 2.2) + 30
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.0) * 1.3
    hit = bp(rng.standard_normal(n), 150, 5000) * np.exp(-t * 12) * 1.4
    tail = sum(np.sin(2 * np.pi * fr * t) for fr in (220, 330, 495, 660)) * 0.08 * np.exp(-t * 1.2)
    return np.tanh(reverb(boom + hit + tail, 0.45, 8) * 1.3)


SOUNDS = dict(rip=rip, slash=slash, spin=spin, bh=bh, collapse=collapse, beam=beam, shatter=shatter, ko=ko)


def write_ogg(x, path):
    x = x / max(1e-6, np.abs(x).max()) * 0.92
    pcm = (x * 32767).astype(np.int16)
    wav = path[:-4] + '.wav'
    with wave.open(wav, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', wav, '-c:a', 'libvorbis', '-q:a', '5', path], check=True)
    os.remove(wav)


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'out'
    os.makedirs(out, exist_ok=True)
    for name, fn in SOUNDS.items():
        write_ogg(fn(), os.path.join(out, f'scyther_{name}.ogg'))
    print('sfx ok')
