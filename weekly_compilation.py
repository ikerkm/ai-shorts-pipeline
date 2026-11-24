"""Compilatorio semanal: junta los MASTERS limpios (sin CTA por-clip) de los últimos
N días de una cuenta y produce un vídeo largo (formato no-Short) con:
  - intro de marca con título + rango de fechas
  - los clips de la semana concatenados
  - una única CTA de suscripción superpuesta al final

Formato por defecto: 16:9 (1920×1080) con fondo desenfocado (pillarbox) — para la
superficie de vídeo largo en escritorio/TV. Usar --vertical para 1080×1920.

Los masters los genera pipeline.py cuando la cuenta tiene "subscribe_cta": true
(se guardan en output/{cuenta}/masters/{epoch}_{topic}.mp4).

Uso:
  python weekly_compilation.py --account ciencia_espacial            # 16:9, últimos 7 días
  python weekly_compilation.py --account ciencia_espacial --days 7 --max 12
  python weekly_compilation.py --account ciencia_espacial --vertical
"""
import argparse
import random
import subprocess
import time
from datetime import datetime
from pathlib import Path

from config import (OUTPUT_DIR, ASSETS_DIR, MUSIC_DIR, FFMPEG,
                    VIDEO_WIDTH, VIDEO_HEIGHT, FPS, load_account)
from modules.video_assembler import make_cta_card, add_subscribe_cta, probe_duration, _WIN_FONT_BOLD
from modules.tts_generator import generate_audio

CTA_DUR = 4.0       # en formato largo la CTA puede durar algo más
XFADE_DUR = 0.5     # disolvencia entre clips (suaviza el corte)
CLIP_PAD = 0.9      # cola de silencio por clip → hueco entre la última y la primera palabra (gap ≈ CLIP_PAD - XFADE_DUR)
INTRO_TAIL = 1.0    # silencio/respiración tras la voz de intro
INTRO_MUSIC_DB = -20
DEFAULT_INTRO_LINE = "Esto es lo más alucinante que el universo nos enseñó esta semana."
LANDSCAPE = (1920, 1080)
PORTRAIT = (VIDEO_WIDTH, VIDEO_HEIGHT)


def _masters_dir(account: str) -> Path:
    sub = load_account(account).get("output_subdir", "") or account
    return OUTPUT_DIR / sub / "masters"


def gather_masters(account: str, days: int, max_clips: int) -> list[Path]:
    """Masters cuyo timestamp (epoch en el nombre) cae en la ventana de N días."""
    cutoff = time.time() - days * 86400
    out = []
    for p in sorted(_masters_dir(account).glob("*.mp4")):
        try:
            ts = int(p.stem.split("_", 1)[0])
        except (ValueError, IndexError):
            continue
        if ts >= cutoff:
            out.append((ts, p))
    out.sort()  # cronológico (domingo→sábado)
    paths = [p for _, p in out]
    return paths[-max_clips:] if max_clips else paths


def _extract_frame(video: Path, out_png: Path, t: float = 2.0) -> Path | None:
    r = subprocess.run([FFMPEG, "-y", "-ss", f"{t}", "-i", str(video),
                        "-frames:v", "1", str(out_png)], capture_output=True, text=True)
    return out_png if (r.returncode == 0 and out_png.exists()) else None


def _font(names: list[str], size: int):
    from PIL import ImageFont
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_title_card(out_png: Path, line1: str, line2: str, eyebrow: str = "",
                    handle: str = "", size=LANDSCAPE, bg_frame: Path = None) -> Path:
    """Tarjeta de título cinematográfica: fondo = fotograma de la semana desenfocado
    y oscurecido (o starfield procedural si no hay frame) + tipografía moderna con
    sombra, eyebrow con tracking y línea de acento."""
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
    W, H = size
    ACCENT = (95, 185, 255)

    # ── Fondo ──
    if bg_frame and Path(bg_frame).exists():
        bg = ImageOps.fit(Image.open(bg_frame).convert("RGB"), (W, H), method=Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(30))
        bg = Image.blend(bg, Image.new("RGB", (W, H), (4, 7, 18)), 0.60)
    else:
        import random as _r
        bg = Image.new("RGB", (W, H), (6, 9, 20))
        top = Image.new("RGB", (W, H), (16, 24, 52))
        mask = Image.linear_gradient("L").resize((W, H))
        bg = Image.composite(bg, top, mask)
        sd = ImageDraw.Draw(bg)
        for _ in range(450):
            x, y = _r.randint(0, W), _r.randint(0, H)
            b = _r.randint(60, 255); s = _r.choice([1, 1, 1, 2])
            sd.ellipse([x, y, x + s, y + s], fill=(b, b, min(255, b + 15)))
    # Vignette suave para que el texto resalte
    vig = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vig).ellipse([-W * 0.3, -H * 0.3, W * 1.3, H * 1.3], fill=90)
    bg = Image.composite(bg, Image.new("RGB", (W, H), (2, 4, 12)), vig)

    img = bg.convert("RGBA")
    d = ImageDraw.Draw(img)

    f_eyebrow = _font([r"C:\Windows\Fonts\bahnschrift.ttf", _WIN_FONT_BOLD], int(H * 0.030))
    f_title = _font([r"C:\Windows\Fonts\seguibl.ttf", r"C:\Windows\Fonts\segoeuib.ttf", _WIN_FONT_BOLD], int(H * 0.115))
    f_date = _font([r"C:\Windows\Fonts\segoeui.ttf", _WIN_FONT_BOLD], int(H * 0.040))
    f_handle = _font([r"C:\Windows\Fonts\segoeui.ttf", _WIN_FONT_BOLD], int(H * 0.026))

    def _spaced_w(text, font, sp):
        return sum(d.textlength(c, font=font) + sp for c in text) - sp if text else 0

    def _draw_spaced(x, y, text, font, fill, sp):
        for c in text:
            d.text((x, y), c, font=font, fill=fill)
            x += d.textlength(c, font=font) + sp

    title_lines = line1.split("\n")
    th = [d.textbbox((0, 0), ln, font=f_title) for ln in title_lines]
    title_h = sum((b[3] - b[1]) for b in th) + int(H * 0.012) * (len(title_lines) - 1)

    # Bloque centrado verticalmente
    block_h = int(H * 0.05) + title_h + int(H * 0.10)
    y = (H - block_h) // 2

    # Eyebrow + línea de acento
    if eyebrow:
        sp = int(H * 0.006)
        ew = _spaced_w(eyebrow, f_eyebrow, sp)
        _draw_spaced((W - ew) // 2, y, eyebrow, f_eyebrow, ACCENT, sp)
        ly = y + int(H * 0.052)
        d.line([(W - ew) // 2, ly, (W + ew) // 2, ly], fill=ACCENT, width=3)
        y = ly + int(H * 0.045)

    # Título con sombra suave
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ds = ImageDraw.Draw(shadow)
    ty = y
    for ln, b in zip(title_lines, th):
        x = (W - (b[2] - b[0])) // 2
        ds.text((x, ty), ln, font=f_title, fill=(0, 0, 0, 200))
        ty += (b[3] - b[1]) + int(H * 0.012)
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(img)
    ty = y
    for ln, b in zip(title_lines, th):
        x = (W - (b[2] - b[0])) // 2
        d.text((x, ty), ln, font=f_title, fill=(255, 255, 255, 255))
        ty += (b[3] - b[1]) + int(H * 0.012)
    y = ty + int(H * 0.03)

    # Fecha
    db = d.textbbox((0, 0), line2, font=f_date)
    d.text(((W - (db[2] - db[0])) // 2, y), line2, font=f_date, fill=(205, 215, 230, 255))

    # Handle abajo
    if handle:
        hb = d.textbbox((0, 0), handle, font=f_handle)
        d.text(((W - (hb[2] - hb[0])) // 2, int(H * 0.90)), handle, font=f_handle, fill=(150, 170, 200, 255))

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_png)
    return out_png


def ensure_intro_vo(profile: dict, out_mp3: Path) -> Path | None:
    """Genera (y cachea) la locución de intro con la voz de la cuenta. None si falla.
    Se cachea en assets/ → no gasta API cada semana; borra el archivo para regenerar."""
    if out_mp3.exists():
        return out_mp3
    line = profile.get("compilation_intro_line", DEFAULT_INTRO_LINE)
    try:
        generate_audio(
            line, out_mp3,
            elevenlabs_voice_id=profile.get("elevenlabs_voice_id") or None,
            kokoro_voice=profile.get("kokoro_voice") or None,
            kokoro_speed=float(profile.get("kokoro_speed", 0.92)),
        )
        return out_mp3 if out_mp3.exists() else None
    except Exception as e:
        print(f"  [intro] VO falló ({e}); intro sin voz")
        return None


def make_intro_clip(card_png: Path, out: Path, vo_mp3: Path = None,
                    music_path: Path = None, size=LANDSCAPE) -> Path:
    """Intro: tarjeta de título + voz del narrador (si hay) + música de fondo.
    La duración se ajusta a la voz + INTRO_TAIL."""
    W, H = size
    has_vo = bool(vo_mp3 and Path(vo_mp3).exists())
    has_mus = bool(music_path and Path(music_path).exists())
    dur = (probe_duration(vo_mp3) + INTRO_TAIL) if has_vo else 3.0

    cmd = [FFMPEG, "-y", "-loop", "1", "-t", f"{dur:.2f}", "-i", str(card_png)]
    idx, afil, mix = 1, [], []
    if has_vo:
        cmd += ["-i", str(vo_mp3)]
        afil.append(f"[{idx}:a]apad=whole_dur={dur:.2f}[voa]"); mix.append("[voa]"); idx += 1
    if has_mus:
        cmd += ["-stream_loop", "-1", "-i", str(music_path)]
        afil.append(f"[{idx}:a]volume={INTRO_MUSIC_DB}dB,atrim=0:{dur:.2f}[mus]"); mix.append("[mus]"); idx += 1

    vfil = (f"[0:v]scale={W}:{H},fps={FPS},format=yuv420p,setsar=1,"
            f"fade=t=in:st=0:d=0.4,fade=t=out:st={dur-0.4:.2f}:d=0.4[v]")
    parts = [vfil] + afil
    if mix:
        if len(mix) > 1:
            parts.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0[a]")
        else:
            parts.append(f"{mix[0]}anull[a]")
        amap = ["-map", "[a]"]
    else:
        cmd += ["-f", "lavfi", "-t", f"{dur:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
        amap = ["-map", f"{idx}:a"]

    cmd += ["-filter_complex", ";".join(parts), "-map", "[v]"] + amap + [
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart", "-t", f"{dur:.2f}", str(out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"make_intro_clip falló:\n{r.stderr[-1500:]}")
    return out


def concat_vertical(parts: list[Path], out: Path) -> Path:
    """Concatena clips ya verticales (mismas dimensiones) re-encodeando — robusto."""
    cmd = [FFMPEG, "-y"]
    for p in parts:
        cmd += ["-i", str(p)]
    n = len(parts)
    streams = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n))
    fc = f"{streams}concat=n={n}:v=1:a=1[v][a]"
    cmd += [
        "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "19",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"concat_vertical falló:\n{r.stderr[-1500:]}")
    return out


def concat_landscape(intro: Path, masters: list[Path], out: Path,
                     xfade_dur: float = XFADE_DUR) -> Path:
    """Intro (ya 16:9) + masters verticales convertidos a 16:9 con fondo desenfocado
    (pillarbox), encadenados con disolvencia (xfade) en vez de corte seco para suavizar
    las transiciones. Vídeo y audio se funden en paralelo. Una sola pasada."""
    W, H = LANDSCAPE
    inputs = [intro] + masters
    # A cada master se le añade CLIP_PAD de cola → la narración no se solapa en la disolvencia
    durs = [probe_duration(intro)] + [probe_duration(m) + CLIP_PAD for m in masters]
    cmd = [FFMPEG, "-y"]
    for p in inputs:
        cmd += ["-i", str(p)]

    parts = []
    # input 0 = intro (ya 16:9): normalizar
    parts.append(f"[0:v]scale={W}:{H},setsar=1,fps={FPS},format=yuv420p[cv0]")
    parts.append("[0:a]aresample=44100,aformat=channel_layouts=stereo[ca0]")
    # inputs 1..M = masters verticales → pillarbox 16:9
    for j in range(len(masters)):
        idx = j + 1
        parts.append(f"[{idx}:v]split=2[s{j}a][s{j}b]")
        parts.append(
            f"[s{j}a]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},boxblur=20:1[bg{j}]"
        )
        parts.append(f"[s{j}b]scale=-2:{H}[fg{j}]")
        parts.append(f"[bg{j}][fg{j}]overlay=(W-w)/2:0,setsar=1,fps={FPS},format=yuv420p,"
                     f"tpad=stop_mode=clone:stop_duration={CLIP_PAD}[cv{idx}]")
        parts.append(f"[{idx}:a]aresample=44100,aformat=channel_layouts=stereo,"
                     f"apad=pad_dur={CLIP_PAD}[ca{idx}]")

    # Cadena de xfade de vídeo: offset = duración acumulada hasta ese punto - solape
    prev_v = "[cv0]"
    cum = durs[0]
    for k in range(1, len(inputs)):
        off = max(0.0, cum - xfade_dur)
        lbl = f"[vx{k}]"
        parts.append(f"{prev_v}[cv{k}]xfade=transition=fade:duration={xfade_dur}:offset={off:.3f}{lbl}")
        cum = cum + durs[k] - xfade_dur
        prev_v = lbl
    # Cadena de acrossfade de audio (se solapa lo mismo → queda sincronizado con el vídeo)
    prev_a = "[ca0]"
    for k in range(1, len(inputs)):
        lbl = f"[ax{k}]"
        parts.append(f"{prev_a}[ca{k}]acrossfade=d={xfade_dur}:c1=tri:c2=tri{lbl}")
        prev_a = lbl

    fc = ";".join(parts)
    cmd += [
        "-filter_complex", fc, "-map", prev_v, "-map", prev_a,
        "-c:v", "libx264", "-preset", "fast", "-crf", "19",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"concat_landscape falló:\n{r.stderr[-1500:]}")
    return out


def build_compilation(account: str, days: int = 7, max_clips: int = 0,
                      landscape: bool = True) -> Path | None:
    profile = load_account(account)
    sub = profile.get("output_subdir", "") or account
    display = profile.get("display_name", account)
    handle = profile.get("youtube_channel_handle", "")
    size = LANDSCAPE if landscape else PORTRAIT

    masters = gather_masters(account, days, max_clips)
    if len(masters) < 2:
        print(f"  [compilatorio] solo {len(masters)} master(s) en los últimos {days} días — se necesita ≥2. Abortado.")
        return None

    fmt = "16:9" if landscape else "vertical"
    print(f"  [compilatorio] {len(masters)} clips de {display} (últimos {days} días) — {fmt}")
    comp_dir = OUTPUT_DIR / sub / "compilations"
    comp_dir.mkdir(parents=True, exist_ok=True)
    work = comp_dir / "_work"
    work.mkdir(exist_ok=True)

    d0 = datetime.fromtimestamp(int(masters[0].stem.split("_")[0]))
    d1 = datetime.fromtimestamp(int(masters[-1].stem.split("_")[0]))
    rango = f"{d0.strftime('%d')}–{d1.strftime('%d %b %Y')}"

    # 1) Intro: tarjeta cinematográfica (fondo = fotograma de la semana) + voz + música
    bg_src = _extract_frame(masters[len(masters) // 2], work / "bg.png", t=2.0)
    title_txt = profile.get("compilation_title", "EL ESPACIO\nESTA SEMANA")
    eyebrow = f"{display.upper()} · RESUMEN SEMANAL"
    card = make_title_card(work / "title.png",
                           line1=title_txt,
                           line2=f"Lo más alucinante · {rango}",
                           eyebrow=eyebrow, handle=handle,
                           size=size, bg_frame=bg_src)
    vo = ensure_intro_vo(profile, ASSETS_DIR / f"intro_vo_{sub or 'default'}.mp3")
    music_files = profile.get("music_files") or []
    music_path = (MUSIC_DIR / random.choice(music_files)) if music_files else None
    intro = make_intro_clip(card, work / "intro.mp4", vo_mp3=vo, music_path=music_path, size=size)

    # 2) Concat según formato
    body = work / "body.mp4"
    if landscape:
        concat_landscape(intro, masters, body)
    else:
        concat_vertical([intro] + masters, body)

    # 3) CTA de suscripción al final (H*0.44 es relativo a la altura de salida → vale en ambos formatos)
    stamp = datetime.now().strftime("%Y%m%d")
    final = comp_dir / f"recopilatorio_{stamp}.mp4"
    cta_png = make_cta_card(ASSETS_DIR / f"cta_{sub or 'default'}.png", handle)
    add_subscribe_cta(body, final, cta_png, cta_dur=CTA_DUR)

    for f in work.glob("*"):
        f.unlink(missing_ok=True)
    work.rmdir()

    dur = probe_duration(final)
    size_mb = final.stat().st_size / 1e6
    print(f"\n{'='*55}")
    print(f"  RECOPILATORIO LISTO ({fmt}): {final}")
    print(f"  {len(masters)} clips | {int(dur//60)}m{int(dur%60):02d}s | {size_mb:.1f} MB")
    print(f"{'='*55}")
    print(f"\n  Título sugerido YouTube: \"Lo más alucinante del espacio esta semana | {rango}\"")
    print(f"  (Subir como vídeo NORMAL — no Short. Duración >3min garantiza la superficie de vídeo largo.)")
    return final


def main():
    ap = argparse.ArgumentParser(description="Compilatorio semanal de masters")
    ap.add_argument("--account", required=True)
    ap.add_argument("--days", type=int, default=7, help="Ventana de días (default 7)")
    ap.add_argument("--max", type=int, default=0, help="Tope de clips (0 = todos)")
    ap.add_argument("--vertical", action="store_true", help="Salida vertical 1080×1920 (default: 16:9)")
    args = ap.parse_args()
    build_compilation(args.account, days=args.days, max_clips=args.max,
                      landscape=not args.vertical)


if __name__ == "__main__":
    main()
