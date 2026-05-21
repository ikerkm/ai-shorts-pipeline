"""
Test RIFE VFI interpolation: Wan 81f + RIFE x4 → smooth slow-motion fill.
Genera imagen, clip 9s con RIFE, extrae 6 frames para inspección visual.
"""
import sys, subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import FFMPEG
from modules.image_generator import generate_image
from modules.video_generator import generate_wan_video

OUT = Path(__file__).parent / "test_output" / "rife_test"
OUT.mkdir(parents=True, exist_ok=True)

PROMPT_IMG = (
    "ancient Mayan pyramid at golden hour, long shadows across stone steps, "
    "dense jungle in background, dramatic sky with light rays, photorealistic "
    "cinematic photography, natural balanced exposure, 9:16 vertical portrait"
)
PROMPT_VID = (
    "slow majestic zoom-out gradually revealing the full scale of the ancient "
    "Mayan pyramid surrounded by lush jungle at golden hour, cinematic and calm"
)
SEED = 42
DURATION = 9.0

print("=== Generando imagen ===")
img_path = OUT / "test_img.png"
generate_image(PROMPT_IMG, "", SEED, img_path)
print(f"Imagen: {img_path}")

print(f"\n=== Generando clip Wan+RIFE {DURATION}s ===")
clip_path = OUT / "clip_rife_9s.mp4"
generate_wan_video(img_path, PROMPT_VID, SEED, clip_path, DURATION)
print(f"\nClip listo: {clip_path}")

print("\nExtrayendo 6 frames para inspección...")
timestamps = [0.5, 1.5, 3.0, 5.0, 7.0, 8.5]
for t in timestamps:
    frame_out = OUT / f"frame_{t:.1f}s.png"
    subprocess.run([
        FFMPEG, "-y", "-ss", str(t), "-i", str(clip_path),
        "-frames:v", "1", "-q:v", "2", str(frame_out)
    ], capture_output=True)
    print(f"  t={t}s → {frame_out.name}")

print(f"\nListo. Abre los frames en: {OUT}")
print(f"Video: start {clip_path}")
