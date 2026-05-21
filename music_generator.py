"""
Genera 5 variaciones de música ambient por estilo (space, upbeat, mystery).
Uso: python music_generator.py
"""
import numpy as np
import wave as wv
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import FFMPEG, MUSIC_DIR

SR = 44100

SEMITONES = {
    'C': 0, 'Db': 1, 'D': 2, 'Eb': 3, 'E': 4, 'F': 5,
    'Gb': 6, 'G': 7, 'Ab': 8, 'A': 9, 'Bb': 10, 'B': 11
}


def hz(note, octave):
    st = SEMITONES[note] + (octave + 1) * 12
    return 440.0 * (2.0 ** ((st - 69) / 12.0))


def pad_tone(f, n_samples, att_s=1.8, rel_s=2.5, sustain=0.75):
    t = np.arange(n_samples) / SR
    sig = (np.sin(2 * np.pi * f * t)
           + 0.45 * np.sin(2 * np.pi * 2 * f * t)
           + 0.20 * np.sin(2 * np.pi * 3 * f * t)
           + 0.08 * np.sin(2 * np.pi * 4 * f * t)
           + 0.04 * np.sin(2 * np.pi * 5 * f * t))
    env = np.ones(n_samples) * sustain
    att = min(int(att_s * SR), n_samples // 3)
    rel = min(int(rel_s * SR), n_samples // 3)
    env[:att] = np.linspace(0, 1, att)
    env[n_samples - rel:] = np.linspace(sustain, 0, rel)
    return sig * env


def build_track(chords, chord_dur, total_dur, vol_per_note=0.12, overlap_s=3.0):
    total_n = int(total_dur * SR)
    out = np.zeros(total_n)
    step = max(chord_dur - overlap_s, 1.0)
    pos, i = 0, 0
    while pos < total_n:
        chord = chords[i % len(chords)]
        n_samples = min(int(chord_dur * SR), total_n - pos)
        if n_samples <= 0:
            break
        for note, octave in chord:
            out[pos:pos + n_samples] += pad_tone(hz(note, octave), n_samples) * vol_per_note
        pos += int(step * SR)
        i += 1
    fi, fo = int(3.5 * SR), int(5.0 * SR)
    if fi < total_n:
        out[:fi] *= np.linspace(0, 1, fi)
    if fo < total_n:
        out[total_n - fo:] *= np.linspace(1, 0, fo)
    return out


def add_reverb(sig, delays=(0.03, 0.08, 0.18, 0.38), decays=(0.42, 0.32, 0.22, 0.12)):
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
    sig = normalize(sig)
    sig_i16 = (np.clip(sig, -1.0, 1.0) * 32767).astype(np.int16)
    wav_path = MUSIC_DIR / f"{name}.wav"
    mp3_path = MUSIC_DIR / f"{name}.mp3"
    with wv.open(str(wav_path), 'w') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(sig_i16.tobytes())
    subprocess.run(
        [FFMPEG, "-y", "-i", str(wav_path), "-b:a", "192k", str(mp3_path)],
        capture_output=True, check=True
    )
    wav_path.unlink()
    print(f"  [OK] {name}.mp3  ({mp3_path.stat().st_size // 1024} KB)")


# ── Definiciones de tracks ───────────────────────────────────────────────────

TRACKS = {
    # SPACE — dreamy, cosmic
    "ambient_space_1": dict(
        chords=[[('A',2),('C',3),('E',3),('A',3)],[('F',2),('A',2),('C',3),('F',3)],
                [('C',3),('E',3),('G',3),('C',4)],[('E',2),('G',2),('B',2),('E',3)]],
        chord_dur=9.0, total_dur=180, vol=0.11, overlap=3.5,
        reverb_d=(0.04,0.10,0.22,0.45), reverb_dc=(0.45,0.34,0.22,0.12),
    ),
    "ambient_space_2": dict(
        chords=[[('D',2),('F',2),('A',2),('D',3)],[('Bb',1),('D',2),('F',2),('Bb',2)],
                [('F',2),('A',2),('C',3),('F',3)],[('C',2),('E',2),('G',2),('C',3)]],
        chord_dur=10.0, total_dur=180, vol=0.10, overlap=4.0,
        reverb_d=(0.05,0.12,0.25,0.50), reverb_dc=(0.48,0.36,0.24,0.13),
    ),
    "ambient_space_3": dict(
        chords=[[('E',2),('G',2),('B',2),('E',3)],[('C',3),('E',3),('G',3),('C',4)],
                [('G',2),('B',2),('D',3),('G',3)],[('D',3),('F',3),('A',3),('D',4)]],
        chord_dur=8.5, total_dur=180, vol=0.11, overlap=3.2,
        reverb_d=(0.04,0.09,0.20,0.42), reverb_dc=(0.44,0.33,0.21,0.11),
    ),
    "ambient_space_4": dict(
        chords=[[('C',2),('Eb',2),('G',2),('C',3)],[('Ab',1),('C',2),('Eb',2),('Ab',2)],
                [('Eb',2),('G',2),('Bb',2),('Eb',3)],[('Bb',1),('D',2),('F',2),('Bb',2)]],
        chord_dur=11.0, total_dur=180, vol=0.09, overlap=4.5,
        reverb_d=(0.06,0.14,0.30,0.55), reverb_dc=(0.50,0.38,0.26,0.14),
    ),
    "ambient_space_5": dict(
        chords=[[('F',2),('A',2),('C',3),('F',3)],[('A',2),('C',3),('E',3),('A',3)],
                [('D',2),('F',2),('A',2),('D',3)],[('C',3),('E',3),('G',3),('C',4)]],
        chord_dur=9.5, total_dur=180, vol=0.10, overlap=3.8,
        reverb_d=(0.04,0.11,0.23,0.47), reverb_dc=(0.46,0.35,0.23,0.12),
    ),

    # UPBEAT — bright, curious
    "ambient_upbeat_1": dict(
        chords=[[('C',3),('E',3),('G',3),('C',4)],[('G',2),('B',2),('D',3),('G',3)],
                [('A',2),('C',3),('E',3),('A',3)],[('F',2),('A',2),('C',3),('F',3)]],
        chord_dur=6.5, total_dur=180, vol=0.13, overlap=2.5,
        reverb_d=(0.02,0.06,0.14), reverb_dc=(0.38,0.26,0.15),
    ),
    "ambient_upbeat_2": dict(
        chords=[[('D',3),('F',3),('A',3),('D',4)],[('A',2),('C',3),('E',3),('A',3)],
                [('B',2),('D',3),('F',3),('B',3)],[('G',2),('B',2),('D',3),('G',3)]],
        chord_dur=6.0, total_dur=180, vol=0.13, overlap=2.2,
        reverb_d=(0.02,0.05,0.12), reverb_dc=(0.36,0.24,0.13),
    ),
    "ambient_upbeat_3": dict(
        chords=[[('G',2),('B',2),('D',3),('G',3)],[('E',2),('G',2),('B',2),('E',3)],
                [('C',3),('E',3),('G',3),('C',4)],[('D',3),('F',3),('A',3),('D',4)]],
        chord_dur=7.0, total_dur=180, vol=0.12, overlap=2.8,
        reverb_d=(0.02,0.07,0.15), reverb_dc=(0.40,0.28,0.16),
    ),
    "ambient_upbeat_4": dict(
        chords=[[('E',2),('Ab',2),('B',2),('E',3)],[('B',2),('Eb',3),('F',3),('B',3)],
                [('C',3),('E',3),('Ab',3),('C',4)],[('A',2),('C',3),('E',3),('A',3)]],
        chord_dur=5.5, total_dur=180, vol=0.14, overlap=2.0,
        reverb_d=(0.02,0.05,0.11), reverb_dc=(0.35,0.23,0.12),
    ),
    "ambient_upbeat_5": dict(
        chords=[[('Bb',2),('D',3),('F',3),('Bb',3)],[('F',2),('A',2),('C',3),('F',3)],
                [('G',2),('Bb',2),('D',3),('G',3)],[('Eb',2),('G',2),('Bb',2),('Eb',3)]],
        chord_dur=6.8, total_dur=180, vol=0.13, overlap=2.6,
        reverb_d=(0.02,0.06,0.13), reverb_dc=(0.37,0.25,0.14),
    ),

    # MYSTERY — dark, tense
    "ambient_mystery_1": dict(
        chords=[[('D',2),('F',2),('A',2),('D',3)],[('Bb',1),('D',2),('F',2),('Bb',2)],
                [('G',2),('Bb',2),('D',3),('G',3)],[('A',2),('C',3),('E',3),('G',3)]],
        chord_dur=11.0, total_dur=180, vol=0.10, overlap=4.0,
        reverb_d=(0.06,0.14,0.30,0.55), reverb_dc=(0.52,0.40,0.28,0.16),
    ),
    "ambient_mystery_2": dict(
        chords=[[('E',2),('G',2),('B',2),('E',3)],[('C',3),('E',3),('G',3),('C',4)],
                [('A',2),('C',3),('E',3),('A',3)],[('B',2),('D',3),('F',3),('Ab',3)]],
        chord_dur=12.0, total_dur=180, vol=0.09, overlap=4.5,
        reverb_d=(0.07,0.16,0.33,0.58), reverb_dc=(0.54,0.42,0.30,0.17),
    ),
    "ambient_mystery_3": dict(
        chords=[[('C',2),('Eb',2),('G',2),('C',3)],[('Ab',1),('C',2),('Eb',2),('Ab',2)],
                [('F',2),('Ab',2),('C',3),('F',3)],[('G',2),('B',2),('D',3),('F',3)]],
        chord_dur=10.5, total_dur=180, vol=0.10, overlap=4.2,
        reverb_d=(0.06,0.15,0.32,0.56), reverb_dc=(0.53,0.41,0.29,0.16),
    ),
    "ambient_mystery_4": dict(
        chords=[[('A',2),('C',3),('E',3),('A',3)],[('E',2),('Ab',2),('B',2),('E',3)],
                [('F',2),('A',2),('C',3),('F',3)],[('D',2),('F',2),('A',2),('C',3)]],
        chord_dur=11.5, total_dur=180, vol=0.09, overlap=4.3,
        reverb_d=(0.06,0.15,0.31,0.57), reverb_dc=(0.53,0.41,0.28,0.15),
    ),
    "ambient_mystery_5": dict(
        chords=[[('B',2),('D',3),('F',3),('B',3)],[('G',2),('B',2),('D',3),('G',3)],
                [('E',2),('G',2),('B',2),('E',3)],[('F',2),('Ab',2),('C',3),('Eb',3)]],
        chord_dur=10.0, total_dur=180, vol=0.10, overlap=3.8,
        reverb_d=(0.06,0.13,0.28,0.52), reverb_dc=(0.51,0.39,0.27,0.15),
    ),
}


print("Generando 15 tracks de música ambient (5 x estilo)...")
for name, p in TRACKS.items():
    sig = build_track(p['chords'], p['chord_dur'], p['total_dur'],
                      vol_per_note=p['vol'], overlap_s=p['overlap'])
    sig = add_reverb(sig, delays=p['reverb_d'], decays=p['reverb_dc'])
    save_mp3(sig, name)

print(f"\nTracks en: {MUSIC_DIR}")
