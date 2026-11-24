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

try:
    from num2words import num2words as _num2words
    _HAS_NUM2WORDS = True
except ImportError:
    _HAS_NUM2WORDS = False


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

_TM_CHARS = str.maketrans({'™': '', '®': '', '©': '', '℠': ''})
_RE_THOUSANDS = re.compile(r'\b(\d{1,3}(?:\.\d{3})+)\b')

def _strip_thousand_dots(text: str) -> str:
    return _RE_THOUSANDS.sub(lambda m: m.group(0).replace('.', ''), text)

# Normalización de números y unidades para TTS en español
_NORM_RULES = [
    # Signo negativo delante de un número → "menos N" (el TTS lo enmudecía,
    # invirtiendo el sentido: "-63 grados" sonaba "63 grados"). Solo si NO va
    # precedido de alfanumérico, para no tocar rangos (5-10) ni palabras compuestas.
    (re.compile(r'(?<![A-Za-z0-9])[-−–]\s*(?=\d)'),  'menos '),
    # Coma decimal entre dígitos → "X coma Y"
    (re.compile(r'(\d),(\d)'),                      r'\1 coma \2'),
    # Velocidad compuesta (antes que km/m simples)
    (re.compile(r'\bkm/h\b', re.I),                 'kilómetros por hora'),
    (re.compile(r'\bkm/s\b', re.I),                 'kilómetros por segundo'),
    (re.compile(r'\bm/s\b',  re.I),                 'metros por segundo'),
    (re.compile(r'\bcm/s\b', re.I),                 'centímetros por segundo'),
    # Área y volumen (antes que km/m simples)
    (re.compile(r'\bkm²'),                           'kilómetros cuadrados'),
    (re.compile(r'\bkm2\b'),                         'kilómetros cuadrados'),
    (re.compile(r'\bkm³'),                           'kilómetros cúbicos'),
    (re.compile(r'\bm²'),                            'metros cuadrados'),
    (re.compile(r'\bm2\b'),                          'metros cuadrados'),
    (re.compile(r'\bm³'),                            'metros cúbicos'),
    (re.compile(r'\bcm²'),                           'centímetros cuadrados'),
    (re.compile(r'\bcm³'),                           'centímetros cúbicos'),
    # Distancia
    (re.compile(r'\bkm\b',  re.I),                  'kilómetros'),
    (re.compile(r'\bcm\b',  re.I),                  'centímetros'),
    (re.compile(r'\bmm\b',  re.I),                  'milímetros'),
    (re.compile(r'\bnm\b'),                          'nanómetros'),
    (re.compile(r'\bAU\b'),                          'unidades astronómicas'),
    (re.compile(r'\bua\b'),                          'unidades astronómicas'),
    (re.compile(r'\bly\b'),                          'años luz'),
    (re.compile(r'\baños-luz\b'),                    'años luz'),
    # Masa
    (re.compile(r'\bkg\b',  re.I),                  'kilogramos'),
    (re.compile(r'\bmg\b',  re.I),                  'miligramos'),
    # Tiempo
    (re.compile(r'\bms\b'),                          'milisegundos'),
    # Temperatura
    (re.compile(r'°C\b'),                            ' grados Celsius'),
    (re.compile(r'°F\b'),                            ' grados Fahrenheit'),
    (re.compile(r'°'),                               ' grados'),
    # Frecuencia
    (re.compile(r'\bGHz\b'),                         'gigahercios'),
    (re.compile(r'\bMHz\b'),                         'megahercios'),
    (re.compile(r'\bkHz\b'),                         'kilohercios'),
    (re.compile(r'\bHz\b'),                          'hercios'),
    # Potencia / energía
    (re.compile(r'\bGW\b'),                          'gigavatios'),
    (re.compile(r'\bMW\b'),                          'megavatios'),
    (re.compile(r'\bkW\b'),                          'kilovatios'),
    (re.compile(r'\bkWh\b'),                         'kilovatios hora'),
    # Superíndices y símbolos matemáticos
    (re.compile(r'²'),                               ' al cuadrado'),
    (re.compile(r'³'),                               ' al cubo'),
    (re.compile(r'×'),                               ' por '),
]

def _spell_integers(text: str) -> str:
    """Convierte enteros sueltos a palabras en español (6500 -> seis mil quinientos).

    Evita que el TTS (sobre todo ElevenLabs) lea mal cifras de 4+ dígitos.
    Se aplica DESPUÉS de _strip_thousand_dots (sin puntos de millar) y de la regla
    de decimales (que ya separó 'X coma Y'), así que cada \\d+ es un entero limpio.
    """
    if not _HAS_NUM2WORDS:
        return text

    def repl(m: re.Match) -> str:
        s = m.group(0)
        try:
            n = int(s)
        except ValueError:
            return s
        if n > 10 ** 15:  # cifras astronómicas: dejar en dígitos (num2words se dispara)
            return s
        try:
            return _num2words(n, lang='es')
        except Exception:
            return s

    return re.sub(r'\d+', repl, text)


def _normalize_for_tts(text: str) -> str:
    for pattern, replacement in _NORM_RULES:
        text = pattern.sub(replacement, text)
    text = _spell_integers(text)
    return re.sub(r' {2,}', ' ', text).strip()

def generate_audio(text: str, output_path: Path,
                   voice: str = None, rate: str = None,
                   elevenlabs_voice_id: str = None,
                   kokoro_voice: str = None, kokoro_speed: float = 0.92) -> tuple[Path, list[dict]]:
    # Símbolos de marca se leen como "marca comercial" en TTS — eliminar
    text = text.translate(_TM_CHARS)
    # Separadores de miles españoles (4.000 → 4000) para evitar "cuatro punto cero cero cero"
    text = _strip_thousand_dots(text)
    # Números decimales y unidades (km/h → kilómetros por hora, 3,4 → 3 coma 4, etc.)
    text = _normalize_for_tts(text)
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
