"""
Genera 15 tracks de música para anuncios absurdos.

Uso: python music_generator_ads.py
"""
import numpy as np
import wave as wv
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import FFMPEG, MUSIC_DIR

SR         = 44100
BPM_INFO   = 120
BPM_CORP   = 90
BPM_LUX    = 60
BEAT_INFO  = 60.0 / BPM_INFO   # 0.500 s
BEAT_CORP  = 60.0 / BPM_CORP   # 0.667 s
BEAT_LUX   = 60.0 / BPM_LUX    # 1.000 s

SEMITONES = {
    'C': 0, 'Db': 1, 'D': 2, 'Eb': 3, 'E': 4, 'F': 5,
    'Gb': 6, 'G': 7, 'Ab': 8, 'A': 9, 'Bb': 10, 'B': 11
}


def hz(note, octave):
    st = SEMITONES[note] + (octave + 1) * 12
    return 440.0 * (2.0 ** ((st - 69) / 12.0))


def synth_note(f, n_samples, att_s, rel_s, sustain, harmonics):
    t   = np.arange(n_samples) / SR
    sig = sum(h * np.sin(2 * np.pi * (i + 1) * f * t) for i, h in enumerate(harmonics))
    env = np.ones(n_samples) * sustain
    att = min(int(att_s * SR), n_samples // 2)
    rel = min(int(rel_s * SR), n_samples // 2)
    if att > 0: env[:att]              = np.linspace(0, 1,       att)
    if rel > 0: env[n_samples - rel:]  = np.linspace(sustain, 0, rel)
    return sig * env


def parse_seq(seq, beat):
    """
    seq items (always 3-tuples):
      ('C', 5, beats)                     — nota individual
      ([('C',3),('E',3),('G',3)], 0, beats) — acorde
      (None, 0, beats)                    — silencio
    Devuelve (events, phrase_dur_s).
    """
    events = []
    t = 0.0
    for note, octave, beats in seq:
        dur = beats * beat
        if note is not None:
            freqs = [hz(n, o) for n, o in note] if isinstance(note, list) else [hz(note, octave)]
            events.append((freqs, t, dur))
        t += dur
    return events, t


def render_looping(events, phrase_dur, total_dur, vol, att_s, rel_s, sustain, harmonics):
    """Renderiza eventos que se repiten en bucle hasta total_dur, con fade global."""
    total_n = int(total_dur * SR)
    out     = np.zeros(total_n)
    phrase_start = 0.0
    while phrase_start < total_dur:
        for freqs, start_in_phrase, dur in events:
            abs_start = phrase_start + start_in_phrase
            if abs_start >= total_dur:
                break
            s_smp = int(abs_start * SR)
            n_smp = min(int(dur * SR), total_n - s_smp)
            if n_smp > 0:
                for f in freqs:
                    out[s_smp:s_smp + n_smp] += synth_note(f, n_smp, att_s, rel_s, sustain, harmonics) * vol
        phrase_start += phrase_dur
    fi, fo = int(3.5 * SR), int(5.0 * SR)
    if fi < total_n: out[:fi]          *= np.linspace(0, 1, fi)
    if fo < total_n: out[total_n - fo:] *= np.linspace(1, 0, fo)
    return out


def add_reverb(sig, delays, decays):
    out = sig.copy()
    for d, dc in zip(delays, decays):
        n = int(d * SR)
        if n < len(sig):
            out[n:] += sig[:-n] * dc
    return out


def normalize(sig, peak=0.85):
    m = np.max(np.abs(sig))
    return sig * (peak / m) if m > 1e-9 else sig


def save_mp3(sig, name):
    sig     = normalize(sig)
    sig_i16 = (np.clip(sig, -1.0, 1.0) * 32767).astype(np.int16)
    wav     = MUSIC_DIR / f"{name}.wav"
    mp3     = MUSIC_DIR / f"{name}.mp3"
    with wv.open(str(wav), 'w') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR)
        f.writeframes(sig_i16.tobytes())
    subprocess.run([FFMPEG, "-y", "-i", str(wav), "-b:a", "192k", str(mp3)],
                   capture_output=True, check=True)
    wav.unlink()
    print(f"  [OK] {name}.mp3  ({mp3.stat().st_size // 1024} KB)")


# ─────────────────────────────────────────────────────────────────────────────
# INFOMERCIAL — 120 BPM, 3 capas, frase de 16 beats (8 s)
# Timbre piano staccato + bajo gordo + acordes en off-beat
# ─────────────────────────────────────────────────────────────────────────────
PIANO_H  = [1.0, 0.65, 0.22, 0.07, 0.02]
BASS_H   = [1.0, 0.80, 0.40, 0.15]
INFO_REV = dict(delays=(0.01, 0.03, 0.07), decays=(0.15, 0.08, 0.04))

# Cada bloque = (melodía_16beats, bajo_16beats, acordes_16beats)
# Progresión: I-V-IV-V-IV-I-V-V en la tonalidad correspondiente

INFO_TRACKS = [
    # ── Track 1: C mayor ──────────────────────────────────────────────────────
    (
        [('C',5,1),('E',5,1),('G',5,2),                       # bar 1: C E G—
         ('A',5,1),('G',5,1),('E',5,1),(None,0,1),            # bar 2: A G E _
         ('F',5,1),('A',5,1),('C',6,2),                       # bar 3: F A C—
         ('G',5,1.5),('E',5,0.5),('C',5,2)],                  # bar 4: G. E C—
        [('C',2,2),('G',2,2),('F',2,2),('G',2,2),
         ('F',2,2),('C',2,2),('G',2,2),('G',2,2)],
        [([('C',3),('E',3),('G',3)],0,1),(None,0,1),([('G',3),('B',3),('D',4)],0,1),(None,0,1),
         ([('F',3),('A',3),('C',4)],0,1),(None,0,1),([('G',3),('B',3),('D',4)],0,1),(None,0,1),
         ([('F',3),('A',3),('C',4)],0,1),(None,0,1),([('C',3),('E',3),('G',3)],0,1),(None,0,1),
         ([('G',3),('B',3),('D',4)],0,1),(None,0,1),([('G',3),('B',3),('D',4)],0,1),(None,0,1)],
    ),
    # ── Track 2: G mayor ──────────────────────────────────────────────────────
    (
        [('G',4,1),('B',4,1),('D',5,2),
         ('E',5,1),('D',5,1),('B',4,1),(None,0,1),
         ('C',5,1),('E',5,1),('G',5,2),
         ('A',5,1.5),('Gb',5,0.5),('G',5,2)],
        [('G',2,2),('D',2,2),('C',2,2),('D',2,2),
         ('C',2,2),('G',2,2),('D',2,2),('D',2,2)],
        [([('G',3),('B',3),('D',4)],0,1),(None,0,1),([('D',3),('Gb',3),('A',3)],0,1),(None,0,1),
         ([('C',4),('E',4),('G',4)],0,1),(None,0,1),([('D',3),('Gb',3),('A',3)],0,1),(None,0,1),
         ([('C',4),('E',4),('G',4)],0,1),(None,0,1),([('G',3),('B',3),('D',4)],0,1),(None,0,1),
         ([('D',3),('Gb',3),('A',3)],0,1),(None,0,1),([('D',3),('Gb',3),('A',3)],0,1),(None,0,1)],
    ),
    # ── Track 3: F mayor ──────────────────────────────────────────────────────
    (
        [('F',4,1),('A',4,1),('C',5,2),
         ('Bb',4,1),('A',4,1),('F',4,1),(None,0,1),
         ('G',4,1),('Bb',4,1),('D',5,2),
         ('C',5,1.5),('A',4,0.5),('F',4,2)],
        [('F',2,2),('C',2,2),('Bb',1,2),('C',2,2),
         ('Bb',1,2),('F',2,2),('C',2,2),('C',2,2)],
        [([('F',3),('A',3),('C',4)],0,1),(None,0,1),([('C',3),('E',3),('G',3)],0,1),(None,0,1),
         ([('Bb',2),('D',3),('F',3)],0,1),(None,0,1),([('C',3),('E',3),('G',3)],0,1),(None,0,1),
         ([('Bb',2),('D',3),('F',3)],0,1),(None,0,1),([('F',3),('A',3),('C',4)],0,1),(None,0,1),
         ([('C',3),('E',3),('G',3)],0,1),(None,0,1),([('C',3),('E',3),('G',3)],0,1),(None,0,1)],
    ),
    # ── Track 4: D mayor ──────────────────────────────────────────────────────
    (
        [('D',5,1),('Gb',5,1),('A',5,2),
         ('B',5,1),('A',5,1),('Gb',5,1),(None,0,1),
         ('G',5,1),('B',5,1),('D',6,2),
         ('A',5,1.5),('Gb',5,0.5),('D',5,2)],
        [('D',2,2),('A',2,2),('G',2,2),('A',2,2),
         ('G',2,2),('D',2,2),('A',2,2),('A',2,2)],
        [([('D',3),('Gb',3),('A',3)],0,1),(None,0,1),([('A',3),('Db',4),('E',4)],0,1),(None,0,1),
         ([('G',3),('B',3),('D',4)],0,1),(None,0,1),([('A',3),('Db',4),('E',4)],0,1),(None,0,1),
         ([('G',3),('B',3),('D',4)],0,1),(None,0,1),([('D',3),('Gb',3),('A',3)],0,1),(None,0,1),
         ([('A',3),('Db',4),('E',4)],0,1),(None,0,1),([('A',3),('Db',4),('E',4)],0,1),(None,0,1)],
    ),
    # ── Track 5: Bb mayor ─────────────────────────────────────────────────────
    (
        [('Bb',4,1),('D',5,1),('F',5,2),
         ('G',5,1),('F',5,1),('D',5,1),(None,0,1),
         ('Eb',5,1),('G',5,1),('Bb',5,2),
         ('F',5,1.5),('D',5,0.5),('Bb',4,2)],
        [('Bb',1,2),('F',2,2),('Eb',2,2),('F',2,2),
         ('Eb',2,2),('Bb',1,2),('F',2,2),('F',2,2)],
        [([('Bb',2),('D',3),('F',3)],0,1),(None,0,1),([('F',3),('A',3),('C',4)],0,1),(None,0,1),
         ([('Eb',3),('G',3),('Bb',3)],0,1),(None,0,1),([('F',3),('A',3),('C',4)],0,1),(None,0,1),
         ([('Eb',3),('G',3),('Bb',3)],0,1),(None,0,1),([('Bb',2),('D',3),('F',3)],0,1),(None,0,1),
         ([('F',3),('A',3),('C',4)],0,1),(None,0,1),([('F',3),('A',3),('C',4)],0,1),(None,0,1)],
    ),
]


def build_infomercial(mel_seq, bass_seq, chd_seq, total_dur=180):
    m_ev, m_pd = parse_seq(mel_seq,  BEAT_INFO)
    b_ev, b_pd = parse_seq(bass_seq, BEAT_INFO)
    c_ev, c_pd = parse_seq(chd_seq,  BEAT_INFO)
    mel  = render_looping(m_ev, m_pd, total_dur, 0.20, 0.015, 0.12, 0.25, PIANO_H)
    bas  = render_looping(b_ev, b_pd, total_dur, 0.16, 0.06,  0.45, 0.55, BASS_H)
    chd  = render_looping(c_ev, c_pd, total_dur, 0.10, 0.02,  0.18, 0.35, PIANO_H)
    return add_reverb(mel + bas + chd, **INFO_REV)


# ─────────────────────────────────────────────────────────────────────────────
# CORPORATE — 108 BPM, clean & forward-moving. Apple/LinkedIn/startup vibe.
# 3 capas: pad suave (4 beats/acorde) + bajo en negras + motivo melódico corto
# Frase: 16 beats (8.9 s). 4 acordes × 4 beats + bajo en cada beat.
# ─────────────────────────────────────────────────────────────────────────────
BPM_CORP  = 108
BEAT_CORP = 60.0 / BPM_CORP   # ~0.556 s

CORP_PAD_H  = [1.0, 0.40, 0.14, 0.04]   # pad suave, poco brillo
CORP_BASS_H = [1.0, 0.60, 0.25, 0.08]   # bajo limpio
CORP_MEL_H  = [1.0, 0.55, 0.20, 0.06]   # motivo un poco más brillante
CORP_REV    = dict(delays=(0.02, 0.06, 0.14), decays=(0.25, 0.14, 0.06))  # sala media, no funeral

# Cada track: (pad_16beats, bass_16beats, motivo_16beats)
# Progresiones mayores con movimiento: I→vi→IV→V  /  I→IV→vi→V
CORP_TRACKS = [
    # Track 1: C → Am → F → G  (I-vi-IV-V)
    (
        [([('C',2),('E',2),('G',2),('B',2)],0,4),([('A',2),('C',3),('E',3),('G',3)],0,4),
         ([('F',2),('A',2),('C',3),('E',3)],0,4),([('G',2),('B',2),('D',3),('Gb',3)],0,4)],
        [('C',2,1),('C',2,1),('A',2,1),('A',2,1),
         ('F',2,1),('F',2,1),('G',2,1),('G',2,1),
         ('C',2,1),('C',2,1),('A',2,1),('A',2,1),
         ('F',2,1),('F',2,1),('G',2,1),('G',2,1)],
        [('E',4,4),(None,0,2),('D',4,2),(None,0,2),('C',4,2),(None,0,2),('G',4,2)],
    ),
    # Track 2: G → Em → C → D
    (
        [([('G',2),('B',2),('D',3),('Gb',3)],0,4),([('E',2),('G',2),('B',2),('D',3)],0,4),
         ([('C',2),('E',2),('G',2),('B',2)],0,4),([('D',2),('Gb',2),('A',2),('C',3)],0,4)],
        [('G',2,1),('G',2,1),('E',2,1),('E',2,1),
         ('C',2,1),('C',2,1),('D',2,1),('D',2,1),
         ('G',2,1),('G',2,1),('E',2,1),('E',2,1),
         ('C',2,1),('C',2,1),('D',2,1),('D',2,1)],
        [('B',4,4),(None,0,2),('A',4,2),(None,0,2),('G',4,2),(None,0,2),('D',4,2)],
    ),
    # Track 3: F → Dm → Bb → C
    (
        [([('F',2),('A',2),('C',3),('E',3)],0,4),([('D',2),('F',2),('A',2),('C',3)],0,4),
         ([('Bb',1),('D',2),('F',2),('A',2)],0,4),([('C',2),('E',2),('G',2),('B',2)],0,4)],
        [('F',2,1),('F',2,1),('D',2,1),('D',2,1),
         ('Bb',1,1),('Bb',1,1),('C',2,1),('C',2,1),
         ('F',2,1),('F',2,1),('D',2,1),('D',2,1),
         ('Bb',1,1),('Bb',1,1),('C',2,1),('C',2,1)],
        [('A',4,4),(None,0,2),('G',4,2),(None,0,2),('F',4,2),(None,0,2),('C',4,2)],
    ),
    # Track 4: D → Bm → G → A
    (
        [([('D',2),('Gb',2),('A',2),('C',3)],0,4),([('B',1),('D',2),('Gb',2),('A',2)],0,4),
         ([('G',2),('B',2),('D',3),('Gb',3)],0,4),([('A',2),('Db',3),('E',3),('G',3)],0,4)],
        [('D',2,1),('D',2,1),('B',1,1),('B',1,1),
         ('G',2,1),('G',2,1),('A',2,1),('A',2,1),
         ('D',2,1),('D',2,1),('B',1,1),('B',1,1),
         ('G',2,1),('G',2,1),('A',2,1),('A',2,1)],
        [('Gb',4,4),(None,0,2),('E',4,2),(None,0,2),('D',4,2),(None,0,2),('A',3,2)],
    ),
    # Track 5: A → F#m → D → E
    (
        [([('A',2),('Db',3),('E',3),('Ab',3)],0,4),([('Gb',2),('A',2),('Db',3),('E',3)],0,4),
         ([('D',2),('Gb',2),('A',2),('C',3)],0,4),([('E',2),('Ab',2),('B',2),('D',3)],0,4)],
        [('A',2,1),('A',2,1),('Gb',2,1),('Gb',2,1),
         ('D',2,1),('D',2,1),('E',2,1),('E',2,1),
         ('A',2,1),('A',2,1),('Gb',2,1),('Gb',2,1),
         ('D',2,1),('D',2,1),('E',2,1),('E',2,1)],
        [('Db',5,4),(None,0,2),('B',4,2),(None,0,2),('A',4,2),(None,0,2),('E',4,2)],
    ),
]


def build_corporate(pad_seq, bass_seq, motif_seq, total_dur=180):
    p_ev, p_pd = parse_seq(pad_seq,   BEAT_CORP)
    b_ev, b_pd = parse_seq(bass_seq,  BEAT_CORP)
    m_ev, m_pd = parse_seq(motif_seq, BEAT_CORP)
    pad  = render_looping(p_ev, p_pd, total_dur, 0.10, 0.25, 1.8, 0.65, CORP_PAD_H)
    bas  = render_looping(b_ev, b_pd, total_dur, 0.12, 0.04, 0.35, 0.50, CORP_BASS_H)
    mot  = render_looping(m_ev, m_pd, total_dur, 0.07, 0.08, 1.2,  0.55, CORP_MEL_H)
    return add_reverb(pad + bas + mot, **CORP_REV)


# ─────────────────────────────────────────────────────────────────────────────
# LUXURY — acordes completos de piano de cola, tonalidad menor
# Ataque rápido (piano) + decay largo + sala grande.
# 4 acordes × 6 s solapados 1.5 s → cambio armónico cada ~4.5 s
# ─────────────────────────────────────────────────────────────────────────────
LUX_H   = [1.0, 0.70, 0.28, 0.10, 0.03]   # más 2º armónico → brillo de piano
LUX_REV = dict(delays=(0.04, 0.12, 0.30), decays=(0.45, 0.30, 0.14))  # sala grande

LUX_PROGRESSIONS = [
    # Am7 → Fmaj7 → Dm7 → E7  (i-VI-iv-V)
    [[('A',2),('C',3),('E',3),('G',3)],
     [('F',2),('A',2),('C',3),('E',3)],
     [('D',2),('F',2),('A',2),('C',3)],
     [('E',2),('Ab',2),('B',2),('D',3)]],
    # Dm7 → Am7 → G7 → Am7
    [[('D',2),('F',2),('A',2),('C',3)],
     [('A',2),('C',3),('E',3),('G',3)],
     [('G',2),('B',2),('D',3),('F',3)],
     [('A',2),('C',3),('E',3),('G',3)]],
    # Am → Fmaj7 → Cmaj7 → E7
    [[('A',2),('C',3),('E',3),('A',3)],
     [('F',2),('A',2),('C',3),('E',3)],
     [('C',2),('E',2),('G',2),('C',3)],
     [('E',2),('Ab',2),('B',2),('E',3)]],
    # Em7 → Am7 → Dm7 → G7
    [[('E',2),('G',2),('B',2),('D',3)],
     [('A',2),('C',3),('E',3),('G',3)],
     [('D',2),('F',2),('A',2),('C',3)],
     [('G',2),('B',2),('D',3),('F',3)]],
    # Am → G → Fmaj7 → E7  (cadencia andaluza)
    [[('A',2),('C',3),('E',3),('A',3)],
     [('G',2),('B',2),('D',3),('G',3)],
     [('F',2),('A',2),('C',3),('F',3)],
     [('E',2),('Ab',2),('B',2),('E',3)]],
]


def build_luxury(chords, total_dur=180):
    """Acordes completos de piano, ataque rápido, decay largo, sala grande."""
    total_n  = int(total_dur * SR)
    out      = np.zeros(total_n)
    note_dur = 6.0   # segundos por acorde
    step     = 4.5   # segundos entre cambios (solapamiento de 1.5 s)
    pos, idx = 0.0, 0
    while pos < total_dur:
        chord = chords[idx % len(chords)]
        s     = int(pos * SR)
        n_smp = min(int(note_dur * SR), total_n - s)
        if n_smp <= 0:
            break
        for note, octave in chord:
            out[s:s + n_smp] += synth_note(hz(note, octave), n_smp,
                                            0.025, 1.8, 0.22, LUX_H) * 0.13
        pos += step
        idx += 1
    fi, fo = int(3.5 * SR), int(5.0 * SR)
    if fi < total_n: out[:fi]           *= np.linspace(0, 1, fi)
    if fo < total_n: out[total_n - fo:] *= np.linspace(1, 0, fo)
    return add_reverb(out, **LUX_REV)


# ─────────────────────────────────────────────────────────────────────────────
# Generación
# ─────────────────────────────────────────────────────────────────────────────

print("Generando 15 tracks de musica para anuncios...")

print("\n  [AD_INFOMERCIAL] melodia + bajo + acordes (120 BPM)...")
for i, (mel, bas, chd) in enumerate(INFO_TRACKS):
    save_mp3(build_infomercial(mel, bas, chd), f"ad_infomercial_{i+1}")

print("\n  [AD_CORPORATE] pad + bajo + motivo (108 BPM)...")
for i, (pad, bass, motif) in enumerate(CORP_TRACKS):
    save_mp3(build_corporate(pad, bass, motif), f"ad_corporate_{i+1}")

print("\n  [AD_LUXURY] acordes piano menor, sala grande...")
for i, prog in enumerate(LUX_PROGRESSIONS):
    save_mp3(build_luxury(prog), f"ad_luxury_{i+1}")

print(f"\nTracks en: {MUSIC_DIR}")
