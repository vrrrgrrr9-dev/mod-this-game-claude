"""Synthesised sound effects for Jeff (bone cracks, ant swarm, star beam, KO boom).

Everything else Jeff plays (punch whooshes, hits, magic casts, explosions) is the game's own
audio, so he sounds like the rest of the roster. Output: OGG Vorbis via ffmpeg.
"""
import os, subprocess, sys, wave
import numpy as np

SR = 44100
rng = np.random.default_rng(7)


def env(n, a=0.002, d=0.1):
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / d)
    return e


def lowpass(x, cut):
    a = np.exp(-2 * np.pi * cut / SR)
    y = np.zeros_like(x); s = 0.0
    for i in range(len(x)):
        s = (1 - a) * x[i] + a * s; y[i] = s
    return y


def bandnoise(n, lo, hi):
    w = rng.standard_normal(n)
    return lowpass(w, hi) - lowpass(w, lo)


def snap(dur=0.32, pitch=1.0, crunch=6):
    n = int(SR * dur)
    out = np.zeros(n)
    # sharp crack transient
    k = int(SR * 0.05)
    out[:k] += bandnoise(k, 1800 * pitch, 9000) * env(k, 0.0005, 0.012) * 2.2
    # splintering crackles
    for i in range(crunch):
        p = int(SR * rng.uniform(0.004, 0.11))
        m = int(SR * rng.uniform(0.006, 0.02))
        if p + m < n:
            out[p:p + m] += bandnoise(m, 1200 * pitch, 7000) * env(m, 0.0003, 0.006) * rng.uniform(0.5, 1.2)
    # body thump
    t = np.arange(n) / SR
    out += np.sin(2 * np.pi * (95 * pitch) * t * (1 - 0.4 * t)) * env(n, 0.001, 0.07) * 0.9
    return out


def swarm(dur=1.3):
    n = int(SR * dur); t = np.arange(n) / SR
    out = np.zeros(n)
    for _ in range(900):                                   # thousands of tiny legs
        p = int(rng.uniform(0, n - 400)); m = int(rng.uniform(40, 160))
        out[p:p + m] += rng.standard_normal(m) * np.hanning(m) * rng.uniform(0.05, 0.22)
    out = out - lowpass(out, 900)
    sweep = bandnoise(n, 500, 2600) * 0.35 * np.sin(np.pi * t / dur) ** 0.7
    shimmer = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) for f in (880, 1320, 1760, 2217)) * 0.06
    shimmer *= (0.5 + 0.5 * np.sin(2 * np.pi * 9 * t)) * np.exp(-t * 1.2)
    out = out + sweep + shimmer
    out *= np.minimum(1, t / 0.05) * np.minimum(1, (dur - t) / 0.3)
    return out


def beam(dur=1.15):
    n = int(SR * dur); t = np.arange(n) / SR
    f = 180 + 520 * (1 - np.exp(-t * 6))
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) + 0.5 * np.sin(2 * ph + 0.3) + 0.25 * np.sign(np.sin(3 * ph))
    x *= 0.35
    x += bandnoise(n, 2500, 9000) * 0.25 * np.exp(-t * 3)
    x += np.sin(2 * np.pi * 55 * t) * 0.3 * np.exp(-t * 2.5)
    x = np.tanh(x * 1.8)
    x *= np.minimum(1, t / 0.02) * np.minimum(1, (dur - t) / 0.35)
    return x * 0.8


def ko(dur=1.6):
    n = int(SR * dur); t = np.arange(n) / SR
    f = 70 * np.exp(-t * 2.2) + 32
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.6) * 1.2
    hit = bandnoise(n, 150, 5000) * np.exp(-t * 14) * 1.4
    tail = bandnoise(n, 80, 1200) * np.exp(-t * 3.2) * 0.4
    crack = np.zeros(n); s = snap(0.3, 0.8, 10); crack[:len(s)] = s * 0.8
    return np.tanh((boom + hit + tail + crack) * 1.3)


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
    write_ogg(snap(0.32, 1.0, 6), os.path.join(out, 'jeff_crack1.ogg'))
    write_ogg(snap(0.36, 1.25, 9), os.path.join(out, 'jeff_crack2.ogg'))
    write_ogg(snap(0.45, 0.8, 14), os.path.join(out, 'jeff_crack3.ogg'))
    write_ogg(swarm(), os.path.join(out, 'jeff_swarm.ogg'))
    write_ogg(beam(), os.path.join(out, 'jeff_beam.ogg'))
    write_ogg(ko(), os.path.join(out, 'jeff_ko.ogg'))
    print('sfx ok')
