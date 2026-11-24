import subprocess
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))
from pathlib import Path
from config import FFMPEG, VIDEO_WIDTH, VIDEO_HEIGHT, FPS, MUSIC_DIR, COLOR_PRESETS

FFPROBE = str(Path(FFMPEG).with_name("ffprobe.exe")) if FFMPEG.lower().endswith(".exe") \
    else FFMPEG.replace("ffmpeg", "ffprobe")
_WIN_FONT_BOLD = r"C:\Windows\Fonts\arialbd.ttf"


def _run(cmd: list, label: str = ""):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error [{label}]:\n{result.stderr[-1500:]}")
    return result


def probe_duration(path: Path) -> float:
    """Duración en segundos de un archivo de vídeo/audio."""
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def make_cta_card(out_png: Path, handle: str = "") -> Path:
    """Genera (una sola vez) la tarjeta PNG transparente de 'Suscríbete' estilo YouTube."""
    if out_png.exists():
        return out_png
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1000, 300
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Caja roja redondeada
    box_w, box_h = 760, 150
    bx, by = (W - box_w) // 2, 20
    d.rounded_rectangle([bx, by, bx + box_w, by + box_h], radius=36, fill=(204, 0, 0, 235))
    # Triángulo play blanco
    tri_cx, tri_cy = bx + 90, by + box_h // 2
    d.polygon([(tri_cx - 26, tri_cy - 30), (tri_cx - 26, tri_cy + 30), (tri_cx + 34, tri_cy)],
              fill=(255, 255, 255, 255))
    try:
        f_big = ImageFont.truetype(_WIN_FONT_BOLD, 70)
        f_small = ImageFont.truetype(_WIN_FONT_BOLD, 40)
    except OSError:
        f_big = ImageFont.load_default(); f_small = ImageFont.load_default()
    txt = "SUSCRÍBETE"
    tb = d.textbbox((0, 0), txt, font=f_big)
    d.text((tri_cx + 60, by + (box_h - (tb[3] - tb[1])) // 2 - tb[1]), txt,
           font=f_big, fill=(255, 255, 255, 255))
    if handle:
        hb = d.textbbox((0, 0), handle, font=f_small)
        d.text(((W - (hb[2] - hb[0])) // 2, by + box_h + 18), handle,
               font=f_small, fill=(255, 255, 255, 230))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)
    return out_png


def add_subscribe_cta(video: Path, output: Path, cta_png: Path,
                      cta_dur: float = 2.5, total_dur: float = None) -> Path:
    """Superpone la tarjeta de suscripción en los últimos `cta_dur` segundos del vídeo.

    El audio se copia tal cual (la CTA es solo visual). Si `total_dur` no se pasa,
    se mide con ffprobe.
    """
    if total_dur is None:
        total_dur = probe_duration(video)
    start = max(0.0, total_dur - cta_dur)
    fc = (
        f"[1:v]format=rgba,fade=t=in:st={start:.2f}:d=0.3:alpha=1[cta];"
        f"[0:v][cta]overlay=(W-w)/2:H*0.44:enable='gte(t,{start:.2f})'[v]"
    )
    _run([
        FFMPEG, "-y",
        "-i", str(video),
        "-loop", "1", "-i", str(cta_png),
        "-filter_complex", fc,
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-c:a", "copy", "-t", f"{total_dur:.3f}",
        str(output),
    ], "subscribe_cta")
    return output


def append_outro_cta(master: Path, output: Path, cta_png: Path,
                     vo_mp3: Path = None, music_path: Path = None,
                     music_db: float = -21.0, min_dur: float = 2.5) -> Path:
    """Añade un cierre de suscripción DESPUÉS del master (no lo pisa).

    El master se mantiene limpio; el Short = master + cola de outro
    (último fotograma congelado + tarjeta 'Suscríbete' con fade-in + locución
    de la voz de la cuenta + música suave opcional). La pregunta de cierre del
    narrador queda intacta en el master y el compilatorio lo reusa sin repetir
    el 'suscríbete' ni hablado ni escrito.

    Si `vo_mp3` no existe, la cola muestra solo la tarjeta (cierre visual).
    """
    W, H = VIDEO_WIDTH, VIDEO_HEIGHT
    has_vo = bool(vo_mp3 and Path(vo_mp3).exists())
    has_mus = bool(music_path and Path(music_path).exists())
    dur = max((probe_duration(vo_mp3) + 1.0) if has_vo else min_dur, min_dur)

    work = output.parent
    last_frame = work / "_outro_lastframe.png"
    tail = work / "_outro_tail.mp4"

    # 1. Último fotograma REAL del master → seam invisible al concatenar la cola
    #    (la cola arranca exactamente donde acaba el master, sin salto hacia atrás).
    _run([
        FFMPEG, "-y", "-sseof", "-0.1", "-i", str(master),
        "-update", "1", "-frames:v", "1", str(last_frame),
    ], "outro_lastframe")

    # 2. Cola: fotograma congelado + tarjeta CTA (fade-in) + voz (+ música suave)
    cmd = [FFMPEG, "-y",
           "-loop", "1", "-t", f"{dur:.2f}", "-i", str(last_frame),
           "-loop", "1", "-i", str(cta_png)]
    idx, afil, mix = 2, [], []
    if has_vo:
        cmd += ["-i", str(vo_mp3)]
        afil.append(f"[{idx}:a]apad=whole_dur={dur:.2f}[voa]"); mix.append("[voa]"); idx += 1
    if has_mus:
        cmd += ["-stream_loop", "-1", "-i", str(music_path)]
        afil.append(f"[{idx}:a]volume={music_db}dB,atrim=0:{dur:.2f}[mus]"); mix.append("[mus]"); idx += 1

    # La cola NO es un freeze plano: el último fotograma se "asienta" hacia una
    # pantalla de cierre — se desenfoca y oscurece en SETTLE s (intencionado, no
    # abrupto) y de paso disuelve el subtítulo quemado residual del master. La
    # tarjeta de suscripción entra después, ya sobre el fondo asentado.
    settle = 0.5
    vfil = (
        f"[0:v]scale={W}:{H},fps={FPS},setsar=1,split=2[base][blursrc];"
        f"[blursrc]boxblur=22:2,eq=brightness=-0.18:saturation=0.85,"
        f"format=rgba,fade=t=in:st=0:d={settle}:alpha=1[blurfade];"
        f"[base][blurfade]overlay[bg];"
        f"[1:v]format=rgba,fade=t=in:st={settle + 0.05:.2f}:d=0.3:alpha=1[cta];"
        f"[bg][cta]overlay=(W-w)/2:H*0.44,"
        f"format=yuv420p,fade=t=out:st={max(0.0, dur-0.4):.2f}:d=0.4[v]"
    )
    parts = [vfil] + afil
    if mix:
        # afade=in en la cola suaviza el corte de audio master→outro (evita el click)
        if len(mix) > 1:
            parts.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,"
                         f"afade=t=in:d=0.3[a]")
        else:
            parts.append(f"{mix[0]}afade=t=in:d=0.3[a]")
        amap = ["-map", "[a]"]
    else:
        cmd += ["-f", "lavfi", "-t", f"{dur:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
        amap = ["-map", f"{idx}:a"]
    cmd += ["-filter_complex", ";".join(parts), "-map", "[v]"] + amap + [
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-t", f"{dur:.2f}", str(tail),
    ]
    _run(cmd, "outro_tail")

    # 3. Concat master + cola (reencode robusto, normaliza v/a de ambos)
    fc = (
        f"[0:v]scale={W}:{H},fps={FPS},setsar=1,format=yuv420p[v0];"
        f"[0:a]aresample=44100,aformat=channel_layouts=stereo[a0];"
        f"[1:v]scale={W}:{H},fps={FPS},setsar=1,format=yuv420p[v1];"
        f"[1:a]aresample=44100,aformat=channel_layouts=stereo[a1];"
        f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
    )
    _run([
        FFMPEG, "-y", "-i", str(master), "-i", str(tail),
        "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        str(output),
    ], "outro_concat")

    for tmp in (last_frame, tail):
        try:
            tmp.unlink()
        except OSError:
            pass
    return output


def create_scene_clip(image_path: Path, duration: float, output_path: Path, zoom_in: bool = True) -> Path:
    """Still image → video clip with Ken Burns zoom effect."""
    frames = int(duration * FPS)
    pad = duration + 0.5  # slight pad to avoid black frames

    if zoom_in:
        z_expr = "min(zoom+0.0007,1.35)"
    else:
        z_expr = "if(eq(on,1),1.35,max(zoom-0.0007,1.0))"

    zoompan = (
        f"zoompan=z='{z_expr}':d={frames}"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={FPS}"
    )
    fade_in = "fade=t=in:st=0:d=0.2"
    fade_out = f"fade=t=out:st={max(0, duration - 0.25):.3f}:d=0.25"

    _run([
        FFMPEG, "-y",
        "-loop", "1", "-t", str(pad), "-i", str(image_path),
        "-vf", f"scale={VIDEO_WIDTH*2}:{VIDEO_HEIGHT*2},{zoompan},{fade_in},{fade_out}",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-r", str(FPS), "-t", str(duration),
        str(output_path)
    ], "scene_clip")
    return output_path


def concat_videos(paths: list[Path], output_path: Path) -> Path:
    list_file = output_path.with_suffix(".txt")
    list_file.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in paths),
        encoding="utf-8"
    )
    _run([
        FFMPEG, "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file), "-c", "copy", str(output_path)
    ], "concat_video")
    list_file.unlink(missing_ok=True)
    return output_path


def concat_audios(paths: list[Path], output_path: Path) -> Path:
    list_file = output_path.with_suffix(".txt")
    list_file.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in paths),
        encoding="utf-8"
    )
    _run([
        FFMPEG, "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file), "-c", "copy", str(output_path)
    ], "concat_audio")
    list_file.unlink(missing_ok=True)
    return output_path


def merge_av(video: Path, audio: Path, output: Path) -> Path:
    _run([
        FFMPEG, "-y",
        "-i", str(video), "-i", str(audio),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
        str(output)
    ], "merge_av")
    return output


def mix_audio_with_music(narration: Path, music_file: str, output: Path,
                         music_db: float = -17) -> Path:
    music_path = MUSIC_DIR / music_file
    if not music_path.exists():
        raise FileNotFoundError(f"Musica no encontrada: {music_path}")
    _run([
        FFMPEG, "-y",
        "-i", str(narration),
        "-stream_loop", "-1", "-i", str(music_path),
        "-filter_complex",
        f"[1:a]volume={music_db}dB[bg];[0:a][bg]amix=inputs=2:duration=first:normalize=0[out]",
        "-map", "[out]",
        "-c:a", "libmp3lame", "-b:a", "192k",
        str(output)
    ], "mix_music")
    return output


def burn_subtitles(video: Path, ass_path: Path, output: Path,
                   color_preset: str = "") -> Path:
    import shutil
    work_dir = ass_path.parent
    tmp_sub = work_dir / "_subs.ass"
    shutil.copy(ass_path, tmp_sub)

    grade = COLOR_PRESETS.get(color_preset, "")
    # Grade se aplica ANTES de los subtítulos para que el texto quede limpio encima
    if grade:
        vf = f"{grade},ass=_subs.ass:original_size={VIDEO_WIDTH}x{VIDEO_HEIGHT}"
    else:
        vf = f"ass=_subs.ass:original_size={VIDEO_WIDTH}x{VIDEO_HEIGHT}"

    try:
        result = subprocess.run([
            FFMPEG, "-y", "-i", str(video.resolve()),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-c:a", "copy", str(output.resolve())
        ], capture_output=True, text=True, cwd=str(work_dir))
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg error [burn_subs]:\n{result.stderr[-1500:]}")
    finally:
        tmp_sub.unlink(missing_ok=True)
    return output
