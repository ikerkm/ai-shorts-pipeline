import asyncio
import base64
import json
import os
import re
import subprocess
import sys
import time
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))
import edge_tts
import requests as _req
from pathlib import Path
from config import TTS_VOICE, TTS_RATE, FFPROBE, FFMPEG


# ── Kokoro ────────────────────────────────────────────────────────────────────

_kokoro_pipeline = None
_kokoro_lang = None

def release_kokoro():
    """Mueve el modelo Kokoro a CPU y libera caché VRAM antes de Wan/Flux."""
    global _kokoro_pipeline
    if _kokoro_pipeline is not None:
        try:
            import torch
            _kokoro_pipeline.model.to('cpu')
            torch.cuda.empty_cache()
        except Exception:
            pass


def _get_kokoro_pipeline(lang_code: str = 'e'):
    global _kokoro_pipeline, _kokoro_lang
    if _kokoro_pipeline is None or _kokoro_lang != lang_code:
        from kokoro import KPipeline
        _kokoro_pipeline = KPipeline(lang_code=lang_code)
        _kokoro_lang = lang_code
    return _kokoro_pipeline


def _kokoro_tts(text: str, voice: str, speed: float, output_path: Path) -> list[dict]:
    import numpy as np
    import soundfile as sf

    lang_code = voice[0]  # 'e' for Spanish (em_alex, ef_dora), 'a' for English, etc.
    pipeline = _get_kokoro_pipeline(lang_code)
    samples = [audio for _, _, audio in pipeline(text, voice=voice, speed=speed)]
    audio = np.concatenate(samples)

    wav_path = output_path.with_suffix('.wav')
    sf.write(str(wav_path), audio, 24000)

    # Convert WAV → MP3 via FFmpeg
    subprocess.run(
        [FFMPEG, '-y', '-i', str(wav_path), '-b:a', '192k', str(output_path)],
        capture_output=True, check=True
    )
    wav_path.unlink(missing_ok=True)

    duration_ms = int(len(audio) / 24000 * 1000)
    return _estimate_word_timings(text, duration_ms)


# ── ElevenLabs ───────────────────────────────────────────────────────────────

def _el_chars_to_words(chars, starts, ends) -> list[dict]:
    """Convierte timestamps de caracteres (ElevenLabs) a nivel de palabra."""
    words = []
    i = 0
    while i < len(chars):
        if chars[i] in (' ', '\n'):
            i += 1
            continue
        j = i
        while j < len(chars) and chars[j] not in (' ', '\n'):
            j += 1
        word = ''.join(chars[i:j])
        words.append({
            'word': word,
            'start_ms': int(starts[i] * 1000),
            'duration_ms': int((ends[j - 1] - starts[i]) * 1000),
        })
        i = j
    return words


def _elevenlabs_tts(text: str, voice_id: str, api_key: str, output_path: Path) -> list[dict]:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
    resp = _req.post(url,
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.80},
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    output_path.write_bytes(base64.b64decode(data["audio_base64"]))
    al = data["alignment"]
    return _el_chars_to_words(al["characters"],
                              al["character_start_times_seconds"],
                              al["character_end_times_seconds"])


# ── Timing estimation ────────────────────────────────────────────────────────

def _estimate_word_timings(text: str, duration_ms: int) -> list[dict]:
    """Proportional timing by character length when TTS gives no word events."""
    words = text.split()
    if not words:
        return []
    clean_len = [max(len(re.sub(r'[^\w]', '', w)), 1) for w in words]
    total = sum(clean_len)
    timings, elapsed = [], 0
    for word, cl in zip(words, clean_len):
        w_dur = max(int(cl / total * duration_ms), 80)
        timings.append({"word": word, "start_ms": elapsed, "duration_ms": w_dur})
        elapsed += w_dur
    return timings


# ── edge-tts ─────────────────────────────────────────────────────────────────

async def _stream_tts(text: str, output_path: Path, voice: str, rate: str) -> list[dict]:
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    word_timings = []
    audio_chunks = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            word_timings.append({
                "word": chunk["text"],
                "start_ms": chunk["offset"] // 10000,
                "duration_ms": chunk["duration"] // 10000,
            })

    output_path.write_bytes(b"".join(audio_chunks))
    return word_timings


# ── Punto de entrada ─────────────────────────────────────────────────────────

def generate_audio(text: str, output_path: Path,
                   voice: str = None, rate: str = None,
                   elevenlabs_voice_id: str = None,
                   kokoro_voice: str = None, kokoro_speed: float = 0.92) -> tuple[Path, list[dict]]:
    # 1. ElevenLabs (máxima calidad, requiere API key)
    el_key = os.getenv('ELEVENLABS_API_KEY', '').strip()
    if el_key and elevenlabs_voice_id:
        try:
            timings = _elevenlabs_tts(text, elevenlabs_voice_id, el_key, output_path)
            return output_path, timings
        except Exception as e:
            print(f"    [ElevenLabs] Error, usando Kokoro: {e}")

    # 2. Kokoro local
    if kokoro_voice:
        try:
            timings = _kokoro_tts(text, kokoro_voice, kokoro_speed, output_path)
            return output_path, timings
        except Exception as e:
            print(f"    [Kokoro] Error, usando edge-tts: {e}")

    # 3. edge-tts (fallback)
    v = voice or TTS_VOICE
    r = rate or TTS_RATE
    for attempt in range(4):
        try:
            timings = asyncio.run(_stream_tts(text, output_path, v, r))
            break
        except Exception as e:
            if attempt == 3:
                raise
            wait = 5 * (2 ** attempt)
            print(f"    [TTS] error (intento {attempt+1}/4), reintentando en {wait}s: {e}")
            time.sleep(wait)
    if not timings:
        duration_ms = int(get_audio_duration(output_path) * 1000)
        timings = _estimate_word_timings(text, duration_ms)
    return output_path, timings


def get_audio_duration(audio_path: Path) -> float:
    result = subprocess.run(
        [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_streams", str(audio_path)],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    for stream in data.get("streams", []):
        if "duration" in stream:
            return float(stream["duration"])
    return 4.0
