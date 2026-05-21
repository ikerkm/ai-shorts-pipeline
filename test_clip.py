"""
Test end-to-end: imagen Flux → video Wan 2.2 → RTX upscale + RIFE
Genera un solo clip y muestra métricas del resultado.

Uso:
    PYTHONUTF8=1 python test_clip.py
"""
import json
import random
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import FFMPEG, FFPROBE, OUTPUT_DIR
from modules.image_generator import generate_image
from modules.video_generator import generate_wan_video

OUTPUT_DIR.mkdir(exist_ok=True)
OUT_IMAGE = OUTPUT_DIR / "test_clip_image.png"
OUT_VIDEO = OUTPUT_DIR / f"test_clip_{int(__import__('time').time())}.mp4"

IMAGE_PROMPT  = "Julius Caesar standing in the Roman Senate hall, senators in togas surrounding him, marble columns, torchlight casting warm shadows, wide establishing shot, cinematic, photorealistic"
VIDEO_PROMPT  = "senators slowly shifting in background, torch flames gently flickering on columns, gradual push-in toward Caesar, consistent stable lighting, no light variation"
DURATION_S    = 5.0   # duración del clip a generar


def probe(path: Path) -> dict:
    r = subprocess.run(
        [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_streams", str(path)],
        capture_output=True, text=True,
    )
    try:
        vs = next(s for s in json.loads(r.stdout)["streams"] if s["codec_type"] == "video")
        return {
            "fps":      vs.get("r_frame_rate"),
            "duration": vs.get("duration"),
            "frames":   vs.get("nb_frames"),
            "width":    vs.get("width"),
            "height":   vs.get("height"),
            "codec":    vs.get("codec_name"),
        }
    except Exception as e:
        return {"error": str(e), "raw": r.stdout[:300]}


def main():
    seed = random.randint(1, 2**31)
    t0 = time.time()

    print(f"\n{'='*60}")
    print(f"TEST CLIP  seed={seed}")
    print(f"{'='*60}\n")

    # ── 1. Imagen Flux ──────────────────────────────────────────
    if OUT_IMAGE.exists():
        print(f"[1/3] Imagen existente reutilizada: {OUT_IMAGE.name}")
        t_img = 0.0
    else:
        print("[1/3] Generando imagen Flux Dev fp8...")
        t1 = time.time()
        generate_image(
            prompt=IMAGE_PROMPT,
            negative="blurry, low quality, text, watermark",
            seed=seed,
            output_path=OUT_IMAGE,
        )
        t_img = time.time() - t1
        print(f"      OK  {OUT_IMAGE.name}  ({OUT_IMAGE.stat().st_size//1024}KB)  [{t_img:.0f}s]")

    # ── 2. Wan 2.2 + RTX upscale + RIFE ────────────────────────
    print(f"\n[2/3] Generando video (Wan 2.2 + RTX + RIFE, {DURATION_S}s)...")
    t2 = time.time()
    generate_wan_video(
        image_path=OUT_IMAGE,
        video_prompt=VIDEO_PROMPT,
        seed=seed,
        output_path=OUT_VIDEO,
        duration_s=DURATION_S,
    )
    t_vid = time.time() - t2
    print(f"      OK  {OUT_VIDEO.name}  ({OUT_VIDEO.stat().st_size//1024}KB)  [{t_vid:.0f}s]")

    # ── 3. Probe del resultado ──────────────────────────────────
    print(f"\n[3/3] Analizando resultado...")
    info = probe(OUT_VIDEO)
    if "error" in info:
        print(f"      ERROR probe: {info}")
    else:
        dur = float(info["duration"]) if info["duration"] else 0
        print(f"      Resolución : {info['width']}x{info['height']}")
        print(f"      FPS        : {info['fps']}")
        print(f"      Duración   : {dur:.3f}s  (target={DURATION_S}s)")
        print(f"      Frames     : {info['frames']}")
        print(f"      Codec      : {info['codec']}")
        ok = (info['width'] == 1080 and info['height'] == 1920
              and abs(dur - DURATION_S) < 0.2)
        print(f"      Estado     : {'✓ OK' if ok else '⚠ revisar'}")

    t_total = time.time() - t0
    print(f"\n{'='*60}")
    print(f"  Imagen : {t_img:.0f}s")
    print(f"  Video  : {t_vid:.0f}s")
    print(f"  Total  : {t_total:.0f}s")
    print(f"  Output : {OUT_VIDEO}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
