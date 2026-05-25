"""
Uso:
  python pipeline.py "tema del video"
  python pipeline.py "tema del video" --style informativo --scenes 5
  python pipeline.py "tema del video" --account ciencia_espacial
  python pipeline.py "tema del video" --account misterio_historia --scenes 6
  python pipeline.py "tema del video" --account datos_curiosos --test
"""
import math
import re
import subprocess
import sys
import json
import time
import shutil
import random
import argparse
from pathlib import Path

# Force UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))
from config import BASE_DIR, TEMP_DIR, OUTPUT_DIR, FFMPEG, VIDEO_WIDTH, VIDEO_HEIGHT, load_account
from modules.script_generator import generate_script, generate_ad_script, generate_what_if_script
from modules.product_generator import generate_product
from modules.image_generator import generate_image
from modules.image_generator_ads import generate_product_hero, generate_scene_from_hero
from modules.tts_generator import generate_audio, get_audio_duration, release_kokoro
from modules.subtitle_generator import generate_ass
from modules.video_assembler import (
    create_scene_clip, concat_videos, concat_audios, merge_av,
    mix_audio_with_music, burn_subtitles
)
from modules.video_generator import generate_wan_video

ZOOM_CYCLE = [True, False, True, False, True, False, True, False]


def _placeholder_image(output_path: Path, color: str = "0x0a0a1a"):
    """Imagen sólida instantánea para modo --test (sin ComfyUI)."""
    subprocess.run([
        FFMPEG, "-y",
        "-f", "lavfi", "-i", f"color=c={color}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}",
        "-frames:v", "1", str(output_path)
    ], capture_output=True)


_ANGLE_SWAPS = [
    ("aerial view", "ground-level wide shot"),
    ("ground-level wide shot", "extreme close-up"),
    ("wide establishing shot", "medium close-up shot"),
    ("medium close-up shot", "wide establishing shot"),
    ("wide shot", "intimate close-up shot"),
    ("close-up", "wide establishing shot"),
    ("from above", "low angle looking up"),
    ("low angle", "high aerial overview"),
    ("overhead", "ground-level perspective"),
]

def _vary_image_prompt(prompt: str) -> str:
    """Devuelve una variante del prompt con ángulo de cámara diferente."""
    for old, new in _ANGLE_SWAPS:
        if old.lower() in prompt.lower():
            return re.sub(re.escape(old), new, prompt, flags=re.IGNORECASE)
    return "Different perspective, closer detail — " + prompt


def run(topic: str, style: str = None, num_scenes: int = None,
        profile: dict = None, test_mode: bool = False,
        script_file: Path = None, script_type: str = None) -> Path:
    p = profile or {}

    # Profile defaults, then function args, then hardcoded fallback
    effective_style = style or p.get("default_style", "informativo")
    effective_scenes = num_scenes or p.get("default_scenes", 5)
    effective_scenes = max(3, min(8, effective_scenes))
    if test_mode:
        effective_scenes = 1

    tts_voice = p.get("tts_voice")
    tts_rate = p.get("tts_rate")
    visual_style_prefix = p.get("visual_style_prefix", "")
    system_prompt_extra = p.get("system_prompt_extra", "")
    account_name = p.get("display_name", "")
    music_files          = p.get("music_files") or ([p["music_file"]] if p.get("music_file") else [])
    music_volume_db      = float(p.get("music_volume_db", -17))
    lora_name            = p.get("lora_name") or None
    lora_strength        = float(p.get("lora_strength", 0.8))
    color_preset         = p.get("color_preset", "none")
    elevenlabs_voice_id  = p.get("elevenlabs_voice_id", "") or None
    kokoro_voice         = p.get("kokoro_voice", "") or None
    kokoro_speed         = float(p.get("kokoro_speed", 0.92))

    out_subdir = p.get("output_subdir", "")
    output_dir = OUTPUT_DIR / out_subdir if out_subdir else OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_topic = "".join(c if c.isascii() and (c.isalnum() or c == '_') else '_' for c in topic[:25].replace(' ', '_'))
    job_id = f"{int(time.time())}_{safe_topic}"
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(parents=True)

    print(f"\n{'='*55}")
    print(f"  PIPELINE SHORTS: {topic}")
    if account_name:
        print(f"  Cuenta  : {account_name}")
    print(f"  Estilo  : {effective_style}  |  Escenas: {effective_scenes}", end="")
    if test_mode:
        print("  [MODO TEST]")
    else:
        print()
    print(f"{'='*55}")

    # ── 0. Producto (solo cuenta anuncios) ────────────────────
    product = None
    cached_script = None
    ad_style_hint = p.get("ad_style_hint") or None
    account_key = p.get("output_subdir", "")
    if p.get("account_type") == "anuncios":
        # --script-file: carga directa sin mover a processed (modo prueba)
        if script_file:
            cached_data   = json.loads(Path(script_file).read_text(encoding="utf-8"))
            product       = cached_data["product"]
            cached_script = cached_data["script"]
            effective_scenes = len(cached_script["scenes"])
            print(f"\n[0/5] Guion cargado (sin consumir): {Path(script_file).name}")
        else:
            # Intentar cargar desde cola pending (pre-generados por script_batch_generator)
            pending_dir   = BASE_DIR / "scripts" / account_key / "pending"
            processed_dir = BASE_DIR / "scripts" / account_key / "processed"
            pending_files = sorted(pending_dir.glob("*.json")) if pending_dir.exists() else []
            if pending_files:
                cached_data   = json.loads(pending_files[0].read_text(encoding="utf-8"))
                product       = cached_data["product"]
                cached_script = cached_data["script"]
                effective_scenes = len(cached_script["scenes"])
                processed_dir.mkdir(parents=True, exist_ok=True)
                pending_files[0].rename(processed_dir / pending_files[0].name)
                print(f"\n[0/5] Guion cacheado: {pending_files[0].name}")
            else:
                print("\n[0/5] Generando concepto de producto...")
                product = generate_product(topic, style_hint=ad_style_hint)
        # Overrides dinámicos basados en el brief del producto
        kokoro_speed = float(product.get("tts_speed", kokoro_speed))
        _style_to_preset = {
            "upbeat": "upbeat", "space": "space", "mystery": "mystery",
            "ad_corporate": "none", "ad_infomercial": "upbeat", "ad_luxury": "mystery",
        }
        color_preset = _style_to_preset.get(product.get("music_style", ""), color_preset)
        _music_map = {
            "upbeat":          p.get("music_upbeat",          music_files),
            "space":           p.get("music_space",           music_files),
            "mystery":         p.get("music_mystery",         music_files),
            "ad_corporate":    p.get("music_ad_corporate",    music_files),
            "ad_infomercial":  p.get("music_ad_infomercial",  music_files),
            "ad_luxury":       p.get("music_ad_luxury",       music_files),
        }
        music_files = _music_map.get(product.get("music_style", ""), music_files)
        visual_style_prefix = ""  # los image_prompts del ad llevan su propio estilo

    # ── 1. Script ─────────────────────────────────────────────
    if cached_script is not None:
        # anuncios: guión cargado de pending/ en el paso 0
        script = cached_script
        print(f"\n[1/5] Guion cargado del cache")
    elif product:
        print("\n[1/5] Generando guion con Claude Opus...")
        script = generate_ad_script(product, effective_scenes)
    else:
        # Auto-selección what_if según ratio del perfil (ej: 20% para ciencia_espacial)
        if script_type is None:
            what_if_ratio = float(p.get("what_if_ratio", 0))
            if what_if_ratio > 0 and random.random() < what_if_ratio:
                script_type = "what_if"

        if script_type == "what_if":
            # Cola what_if separada: scripts/{cuenta}/what_if/pending/
            _pending   = BASE_DIR / "scripts" / account_key / "what_if" / "pending"
            _processed = BASE_DIR / "scripts" / account_key / "what_if" / "processed"
            _pfiles    = sorted(_pending.glob("*.json")) if _pending.exists() else []
            if _pfiles:
                _data  = json.loads(_pfiles[0].read_text(encoding="utf-8"))
                script = _data["script"]
                _processed.mkdir(parents=True, exist_ok=True)
                _pfiles[0].rename(_processed / _pfiles[0].name)
                print(f"\n[1/5] Guion what_if cargado del cache: {_pfiles[0].name}")
            else:
                print("\n[1/5] Generando guion hipotetico (what_if) con Claude Sonnet...")
                script = generate_what_if_script(topic, effective_scenes)
        else:
            # cuentas regulares: comprobar pending/ antes de llamar a Claude
            _pending  = BASE_DIR / "scripts" / account_key / "pending"
            _processed = BASE_DIR / "scripts" / account_key / "processed"
            _pfiles   = sorted(_pending.glob("*.json")) if _pending.exists() else []
            if _pfiles:
                _data  = json.loads(_pfiles[0].read_text(encoding="utf-8"))
                script = _data["script"]
                _processed.mkdir(parents=True, exist_ok=True)
                _pfiles[0].rename(_processed / _pfiles[0].name)
                print(f"\n[1/5] Guion cargado del cache: {_pfiles[0].name}")
            else:
                print("\n[1/5] Generando guion con Claude Sonnet...")
                script = generate_script(topic, effective_style, effective_scenes, system_prompt_extra)
    print(f"  Titulo : {script['title']}")
    print(f"  Escenas: {len(script['scenes'])}")
    (job_dir / "script.json").write_text(
        json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ── 2a. Imágenes (ComfyUI/Flux — GPU exclusivo, sin Kokoro activo) ────────
    print("\n[2/5] Generando imagenes...")
    img_paths = []

    # Anuncios: generar hero image primero, luego img2img por escena
    hero_path = None
    if product and not test_mode:
        print(f"\n  [HERO] Generando imagen base del producto...")
        hero_path = job_dir / "product_hero.png"
        generate_product_hero(
            visual_anchor=product["visual_anchor"],
            visual_style=product["visual_style"],
            seed=random.randint(1, 2**31),
            output_path=hero_path,
        )

    for i, scene in enumerate(script["scenes"]):
        scene_type = scene.get("scene_type", "product")
        print(f"\n  Escena {i+1}/{len(script['scenes'])} [{scene_type}]: {scene['narration'][:45]}...")
        img_path = job_dir / f"scene_{i:02d}.png"

        if test_mode:
            _placeholder_image(img_path)
            print(f"    [IMG] placeholder (modo test)")
        elif hero_path and scene_type not in ("problem", "testimonial"):
            # Escenas de producto y CTA: img2img desde hero para coherencia visual
            generate_scene_from_hero(
                scene_prompt=scene["image_prompt"],
                negative=scene.get("image_negative", "blurry, low quality, text, watermark"),
                hero_path=hero_path,
                seed=random.randint(1, 2**31),
                output_path=img_path,
            )
        else:
            # Problema y testimonio: text2img libre (persona o entorno sin restricción del hero)
            generate_image(
                prompt=scene["image_prompt"],
                negative=scene.get("image_negative", "blurry, low quality, text, watermark"),
                seed=random.randint(1, 2**31),
                output_path=img_path,
                style_prefix=visual_style_prefix,
                lora_name=lora_name,
                lora_strength=lora_strength,
            )
        img_paths.append(img_path)

    # ── 2b. Audio (TTS — después de liberar GPU de Flux) ──────────────────────
    print("\n  Generando audio TTS...")
    scenes_data = []
    for i, scene in enumerate(script["scenes"]):
        audio_path = job_dir / f"audio_{i:02d}.mp3"
        scene_kokoro_voice = scene.get("voice") or kokoro_voice
        _, word_timings = generate_audio(scene["narration"], audio_path,
                                         voice=tts_voice, rate=tts_rate,
                                         elevenlabs_voice_id=elevenlabs_voice_id,
                                         kokoro_voice=scene_kokoro_voice,
                                         kokoro_speed=kokoro_speed)
        duration = get_audio_duration(audio_path)
        print(f"    [TTS {i+1}] {duration:.1f}s")

        scenes_data.append({
            "narration": scene["narration"],
            "img_path": img_paths[i],
            "audio_path": audio_path,
            "duration": duration,
            "word_timings": word_timings,
            "zoom_in": ZOOM_CYCLE[i % len(ZOOM_CYCLE)],
            "use_wan": bool(scene.get("use_wan", False)),
            "video_prompt": scene.get("video_prompt", "slow gentle camera push-in, smooth motion"),
            "image_prompt": scene.get("image_prompt", ""),
            "image_negative": scene.get("image_negative", "blurry, low quality, text, watermark"),
        })

    # Pre-pass: generar imágenes variantes para escenas largas (audio > 7.5s → 2 clips Wan)
    WAN_MAX_S = 7.5
    if not test_mode and not product:
        for i, sd in enumerate(scenes_data):
            if sd["duration"] > WAN_MAX_S:
                n_splits = math.ceil(sd["duration"] / WAN_MAX_S)
                print(f"  [SPLIT] Escena {i+1}: {sd['duration']:.1f}s → {n_splits} clips, generando {n_splits-1} imagen(es) variante(s)...")
                sd["img_paths_split"] = [sd["img_path"]]
                for j in range(1, n_splits):
                    img_var = job_dir / f"scene_{i:02d}_{j}.png"
                    generate_image(
                        prompt=_vary_image_prompt(sd["image_prompt"]),
                        negative=sd["image_negative"],
                        seed=random.randint(1, 2**31),
                        output_path=img_var,
                        style_prefix=visual_style_prefix,
                        lora_name=lora_name,
                        lora_strength=lora_strength,
                    )
                    sd["img_paths_split"].append(img_var)

    # Liberar Kokoro de VRAM antes de que arranque Wan
    release_kokoro()

    # ── 3. Scene clips (Wan I2V, Ken Burns solo si falla) ─────
    print(f"\n[3/5] Creando clips Wan I2V...")
    clips = []
    subtitle_scenes = []
    offset_ms = 0

    for i, sd in enumerate(scenes_data):
        clip = job_dir / f"clip_{i:02d}.mp4"
        if test_mode:
            create_scene_clip(sd["img_path"], sd["duration"], clip, sd["zoom_in"])
            print(f"  Clip {i+1} [KB/test] OK")
        elif "img_paths_split" in sd:
            # Escena larga: N sub-clips con imágenes variantes, sin loops
            img_list = sd["img_paths_split"]
            n = len(img_list)
            sub_dur = sd["duration"] / n
            sub_clips = []
            ok = True
            for j, img_p in enumerate(img_list):
                sub = job_dir / f"clip_{i:02d}_{j}.mp4"
                try:
                    generate_wan_video(
                        image_path=img_p,
                        video_prompt=sd["video_prompt"],
                        seed=random.randint(1, 2**31),
                        output_path=sub,
                        duration_s=sub_dur,
                    )
                except Exception as e:
                    print(f"  Clip {i+1}.{j} [WAN] FALLO ({e}) — usando Ken Burns")
                    create_scene_clip(img_p, sub_dur, sub, sd["zoom_in"])
                    ok = False
                sub_clips.append(sub)
            concat_videos(sub_clips, clip)
            print(f"  Clip {i+1} [WAN×{n}] {'OK' if ok else 'parcial KB'}")
        else:
            try:
                generate_wan_video(
                    image_path=sd["img_path"],
                    video_prompt=sd["video_prompt"],
                    seed=random.randint(1, 2**31),
                    output_path=clip,
                    duration_s=sd["duration"],
                )
                print(f"  Clip {i+1} [WAN] OK")
            except Exception as e:
                print(f"  Clip {i+1} [WAN] FALLO ({e}) — usando Ken Burns")
                create_scene_clip(sd["img_path"], sd["duration"], clip, sd["zoom_in"])
        clips.append(clip)

        subtitle_scenes.append({
            "narration": sd["narration"],
            "word_timings": sd["word_timings"],
            "time_offset_ms": offset_ms,
            "duration_ms": int(sd["duration"] * 1000),
        })
        offset_ms += int(sd["duration"] * 1000)

    # ── 4. Assemble ────────────────────────────────────────────
    print("\n[4/5] Ensamblando video y audio...")
    raw_video = job_dir / "video_raw.mp4"
    full_audio = job_dir / "audio_full.mp3"
    video_av   = job_dir / "video_av.mp4"

    concat_videos(clips, raw_video)
    concat_audios([sd["audio_path"] for sd in scenes_data], full_audio)

    if music_files and not test_mode:
        music_file = random.choice(music_files)
        print(f"  Mezclando musica: {music_file}")
        audio_mixed = job_dir / "audio_mixed.mp3"
        mix_audio_with_music(full_audio, music_file, audio_mixed, music_db=music_volume_db)
        merge_av(raw_video, audio_mixed, video_av)
    else:
        merge_av(raw_video, full_audio, video_av)

    # ── 5. Subtitles + titulo ──────────────────────────────────
    print("\n[5/5] Quemando subtitulos estilo TikTok...")
    ass_path = job_dir / "subtitles.ass"
    generate_ass(subtitle_scenes, ass_path, title=script["title"])

    final = output_dir / f"{job_id}.mp4"
    burn_subtitles(video_av, ass_path, final, color_preset=color_preset)

    shutil.rmtree(job_dir)

    size_mb = final.stat().st_size / 1024 / 1024
    print(f"\n{'='*55}")
    print(f"  VIDEO LISTO: {final}")
    print(f"  Tamano: {size_mb:.1f} MB")
    print(f"{'='*55}\n")

    return final


def main():
    parser = argparse.ArgumentParser(description="Generador automatico de Shorts/TikToks")
    parser.add_argument("topic", help="Tema del video")
    parser.add_argument("--account", default=None,
                        help="Perfil de cuenta (ej: ciencia_espacial, datos_curiosos, misterio_historia)")
    parser.add_argument("--style", default=None,
                        choices=["informativo", "storytelling", "top5", "misterio", "motivacional"],
                        help="Estilo narrativo (sobreescribe el del perfil)")
    parser.add_argument("--scenes", type=int, default=None,
                        help="Numero de escenas 3-8 (sobreescribe el del perfil)")
    parser.add_argument("--test", action="store_true",
                        help="Modo test: 1 escena, imagen placeholder, sin musica (~20s)")
    parser.add_argument("--ad-style", default=None,
                        choices=["ad_corporate", "ad_infomercial", "ad_luxury"],
                        help="Fuerza un estilo visual/musical para anuncios_absurdos")
    parser.add_argument("--script-file", default=None,
                        help="Ruta a un JSON de guion pre-generado; lo usa sin moverlo a processed/")
    parser.add_argument("--script-type", default=None,
                        choices=["what_if"],
                        help="Tipo de guion especial (what_if: hipotesis aplicadas a la Tierra)")
    args = parser.parse_args()

    profile = load_account(args.account) if args.account else {}
    if args.ad_style:
        profile["ad_style_hint"] = args.ad_style
    run(args.topic, style=args.style, num_scenes=args.scenes, profile=profile,
        test_mode=args.test, script_file=args.script_file, script_type=args.script_type)


if __name__ == "__main__":
    main()
