"""Synthesize the 30 s royalty-free BGM used by the QDash demo.

108 BPM, C major (C - Am - F - G). Bright plucked arpeggio, soft detuned pad,
sub bass, and a steady kick/clap/hat groove that enters at 4 s (first feature
scene) and leaves at 26 s (outro). Fades are baked in.

Usage:
  uv run --with numpy --with scipy python3 scripts/make_bgm.py public/bgm.wav
  ffmpeg -y -i public/bgm.wav -c:a aac -b:a 192k public/bgm.m4a
"""
from __future__ import annotations

import sys
import wave

import numpy as np
from scipy.signal import butter, sosfilt

SR = 44100
DURATION = 30.0
PERC_START = 4.0
PERC_END = 26.0


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def lp(x, cutoff, order=2):
    sos = butter(order, min(cutoff, SR / 2 - 100) / (SR / 2), btype="low", output="sos")
    return sosfilt(sos, x, axis=0)


def hp(x, cutoff, order=2):
    sos = butter(order, cutoff / (SR / 2), btype="high", output="sos")
    return sosfilt(sos, x, axis=0)


def adsr(n, a, d, s, r):
    env = np.full(n, s, dtype=float)
    ai, di, ri = int(a * SR), int(d * SR), int(r * SR)
    if ai:
        env[:ai] = np.linspace(0, 1, ai)
    if di:
        env[ai : ai + di] = np.linspace(1, s, di)[: max(0, n - ai)]
    if ri and ri < n:
        env[-ri:] *= np.linspace(1, 0, ri)
    return env


def stereo(sig, pan):
    return np.stack([sig * (1 - pan), sig * pan], axis=1)


def pluck(freq, n, bright=0.6, decay=7.0):
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * freq * t) + 0.5 * np.sin(2 * np.pi * freq * 2 * t)
    tone += 0.25 * np.sign(np.sin(2 * np.pi * freq * t)) * bright
    return lp(tone, 1500 + 5000 * bright) * np.exp(-t * decay)


def pad(freq, n, cutoff=1400):
    t = np.arange(n) / SR
    out = np.zeros((n, 2))
    for i, det in enumerate((-0.007, -0.0025, 0.0025, 0.007)):
        phase = (t * freq * (1 + det) + i * 0.31) % 1.0
        out += stereo(2 * phase - 1, 0.2 + 0.6 * (i / 3))
    return lp(out / 4, cutoff)


def kick(n, punch=1.0):
    t = np.arange(n) / SR
    f = (110 + 60 * punch) * np.exp(-t * 26) + 46
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7)
    click = np.random.default_rng(1).standard_normal(n) * np.exp(-t * 350) * 0.35 * punch
    return np.tanh(1.3 * (body + click))


def clap(n, rng):
    t = np.arange(n) / SR
    env = np.zeros(n)
    for k, off in enumerate((0.0, 0.011, 0.022)):
        i = int(off * SR)
        env[i:] += np.exp(-(t[: n - i]) * 95) * (0.8 - 0.2 * k)
    env += np.exp(-t * 16) * 0.5
    return hp(rng.standard_normal(n) * env, 1000)


def hat(n, rng, decay=70.0, cutoff=7000):
    t = np.arange(n) / SR
    return hp(rng.standard_normal(n) * np.exp(-t * decay), cutoff) * 0.6


def brush(n, rng):
    t = np.arange(n) / SR
    return lp(hp(rng.standard_normal(n) * np.exp(-t * 30), 2500), 6000) * 0.5


def add(buf, start_s, sig, gain):
    i = int(start_s * SR)
    j = min(len(buf), i + len(sig))
    if i >= len(buf):
        return
    seg = sig[: j - i]
    if buf.ndim == 2 and seg.ndim == 1:
        seg = stereo(seg, 0.5)
    buf[i:j] += seg * gain


def pingpong(x, delay_s, fb=0.42, reps=4, damp=4000):
    d = int(delay_s * SR)
    wet = np.zeros_like(x)
    f = x.copy()
    for _ in range(reps):
        f = np.concatenate([np.zeros((d, 2)), f[:-d]]) * fb
        f = f[:, ::-1]
        wet += f
    return lp(wet, damp)


def reverb(x, wet=0.4):
    acc = np.zeros_like(x)
    for d_s in (0.079, 0.121, 0.187, 0.257):
        d = int(d_s * SR)
        f = x.copy()
        for _ in range(5):
            f = lp(np.concatenate([np.zeros((d, 2)), f[:-d]]) * 0.5, 3000)
            acc += f
    return x + acc * (wet / 4)


def finish(mix, out_path, fade_in=0.5, fade_out=3.5, peak=0.85):
    mix = hp(mix, 28)
    mix = mix[: int(DURATION * SR)]
    fi, fo = int(fade_in * SR), int(fade_out * SR)
    mix[:fi] *= np.linspace(0, 1, fi)[:, None]
    mix[-fo:] *= (np.linspace(1, 0, fo) ** 1.3)[:, None]
    mix = mix / (np.max(np.abs(mix)) + 1e-9) * peak
    pcm = (mix * 32767).astype(np.int16)
    with wave.open(out_path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"wrote {out_path}")


# --------------------------------------------------------------------------- track


def corporate(out_path):
    bpm, rng = 108, np.random.default_rng(11)
    beat, bar = 60 / bpm, 240 / bpm
    chords = [[60, 64, 67, 71], [57, 60, 64, 67], [53, 57, 60, 64], [55, 59, 62, 67]]  # C Am F G
    n_total = int(DURATION * SR) + SR * 4
    plk, pd, bass, perc = (np.zeros((n_total, 2)), np.zeros((n_total, 2)), np.zeros(n_total), np.zeros(n_total))
    for b in range(int(DURATION / bar) + 1):
        t0 = b * bar
        ch = chords[b % 4]
        env = adsr(int((bar + 1.0) * SR), 0.4, 0.3, 0.9, 1.0)
        ps = sum(pad(hz(m), len(env), 1600) for m in ch)
        add(pd, t0, ps * env[:, None], 0.16)
        notes = [m + 12 for m in ch] + [ch[0] + 24, ch[2] + 24]
        pattern = [0, 2, 1, 3, 4, 2, 5, 1]
        for s in range(8):
            if t0 < PERC_START and s % 2:
                continue
            f = hz(notes[pattern[s]])
            add(plk, t0 + s * beat / 2, stereo(pluck(f, int(0.6 * SR), 0.7, 8), 0.3 if s % 2 == 0 else 0.7), 0.34)
        root = hz(ch[0] - 24)
        for e in range(8):
            ts = t0 + e * beat / 2
            n = int(beat / 2 * 0.9 * SR)
            t = np.arange(n) / SR
            g = 0.5 if ts < PERC_START else (1.0 if e % 2 == 0 else 0.6)
            add(bass, ts, lp(np.sin(2 * np.pi * root * t) + 0.2 * np.sin(2 * np.pi * root * 2 * t), 500) * adsr(n, 0.005, 0.2, 0.6, 0.1), 0.42 * g)
        for q in range(4):
            ts = t0 + q * beat
            if not (PERC_START <= ts < PERC_END):
                continue
            add(perc, ts, kick(int(0.3 * SR), 0.8), 0.8)
            if q in (1, 3):
                add(perc, ts, clap(int(0.22 * SR), rng), 0.3)
            for s in (0.5,):
                add(perc, ts + s * beat, hat(int(0.12 * SR), rng, 22, 6500), 0.22)
            for s in (0.25, 0.75):
                add(perc, ts + s * beat, hat(int(0.05 * SR), rng, 80, 8000), 0.12)
    tonal = plk + pd + pingpong(plk, beat * 0.75, 0.35) * 0.5
    mix = reverb(tonal, 0.3) + stereo(bass, 0.5) + stereo(perc, 0.5)
    finish(mix, out_path)


if __name__ == "__main__":
    corporate(sys.argv[1] if len(sys.argv) > 1 else "public/bgm.wav")
