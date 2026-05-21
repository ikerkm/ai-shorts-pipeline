import subprocess
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))
from pathlib import Path
from config import FFMPEG, VIDEO_WIDTH, VIDEO_HEIGHT, FPS, MUSIC_DIR, COLOR_PRESETS


def _run(cmd: list, label: str = ""):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error [{label}]:\n{result.stderr[-1500:]}")
    return result


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
