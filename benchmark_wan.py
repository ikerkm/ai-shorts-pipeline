"""
Benchmark de generación Wan 2.1 I2V — mide tiempos con distintas configuraciones.

Uso:
  python benchmark_wan.py

Configs probadas:
  A) Baseline  : 50 steps, sin optimizaciones
  B) CausVid   : 8 steps + CausVid LoRA
  C) CausVid+TC: 8 steps + CausVid + TeaCache
  D) CausVid+TC: 8 steps + CausVid + TeaCache + 49 frames (~3s)
"""
import sys
import json
import time
import uuid
import urllib.request
import urllib.parse
import websocket
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from config import COMFYUI_URL, OUTPUT_DIR

COMFYUI_WS = COMFYUI_URL.replace("http://", "ws://").replace("https://", "wss://")
BENCH_OUT = OUTPUT_DIR / "benchmark_wan"
BENCH_OUT.mkdir(parents=True, exist_ok=True)
COMFYUI_OUT = pathlib.Path(r"Z:\AI\ComfyUI\output")

# ── Imagen de prueba (si no existe, creamos una rápida con FFmpeg) ────────────
import subprocess
from config import FFMPEG

TEST_IMG = BENCH_OUT / "test_input.png"
if not TEST_IMG.exists():
    subprocess.run([
        FFMPEG, "-y", "-f", "lavfi",
        "-i", "color=c=0x112233:s=480x832",
        "-frames:v", "1", str(TEST_IMG)
    ], capture_output=True)
    print(f"Imagen de prueba creada: {TEST_IMG}")


def _build_workflow(
    image_filename: str,
    steps: int,
    num_frames: int,
    use_causvid: bool,
    use_teacache: bool,
    output_prefix: str,
    cfg: float = 5.0,
    fps: int = 16,
) -> dict:
    """
    Construye el workflow ComfyUI para Wan 2.1 I2V.

    Node map:
      1  UNETLoader
      2  CLIPLoader (T5/wan)
      3  VAELoader
      4  CLIPVisionLoader
      5  LoadImage
      6  CLIPVisionEncode
      7  CLIPTextEncode (positive)
      8  CLIPTextEncode (negative)
      9  WanImageToVideo
      10 KSampler
      11 VAEDecode
      12 VHS_VideoCombine
      20 LoraLoader    (si use_causvid)
      21 TeaCache      (si use_teacache)
    """
    # Fuentes del modelo e inputs para KSampler y CLIP
    model_src = ["1", 0]
    clip_src  = ["2", 0]

    wf = {
        "1": {
            "class_type": "UnetLoaderGGUF",
            "inputs": {
                "unet_name": "wan2.1-i2v-14b-480p-Q4_K_M.gguf",
            },
        },
        "2": {
            "class_type": "CLIPLoaderGGUF",
            "inputs": {
                "clip_name": "umt5-xxl-encoder-Q5_K_M.gguf",
                "type": "wan",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "wan_2.1_vae.safetensors"},
        },
        "4": {
            "class_type": "CLIPVisionLoader",
            "inputs": {"clip_name": "clip_vision_h.safetensors"},
        },
        "5": {
            "class_type": "LoadImage",
            "inputs": {"image": image_filename, "upload": "image"},
        },
        "6": {
            "class_type": "CLIPVisionEncode",
            "inputs": {
                "clip_vision": ["4", 0],
                "image": ["5", 0],
                "crop": "none",
            },
        },
    }

    # ── LoRA CausVid ───────────────────────────────────────────────────────────
    if use_causvid:
        wf["20"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["1", 0],
                "clip": ["2", 0],
                "lora_name": "Wan21_CausVid_14B_T2V_lora_rank32_v2.safetensors",
                "strength_model": 1.0,
                "strength_clip": 1.0,
            },
        }
        model_src = ["20", 0]
        clip_src  = ["20", 1]

    # ── TeaCache ───────────────────────────────────────────────────────────────
    if use_teacache:
        wf["21"] = {
            "class_type": "TeaCache",
            "inputs": {
                "model": model_src,
                "model_type": "wan2.1_i2v_480p_14B",
                "rel_l1_thresh": 0.3,
                "start_percent": 0.0,
                "end_percent": 1.0,
                "cache_device": "cuda",
            },
        }
        model_src = ["21", 0]

    # ── Texto, latent, sampler ─────────────────────────────────────────────────
    wf["7"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": clip_src,
            "text": "cinematic video, smooth camera motion, high quality",
        },
    }
    wf["8"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": clip_src,
            "text": "blurry, low quality, text, watermark, distorted",
        },
    }
    wf["9"] = {
        "class_type": "WanImageToVideo",
        "inputs": {
            "positive": ["7", 0],
            "negative": ["8", 0],
            "vae": ["3", 0],
            "width": 480,
            "height": 832,
            "length": num_frames,
            "batch_size": 1,
            "start_image": ["5", 0],
            "clip_vision_output": ["6", 0],
        },
    }
    wf["10"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": model_src,
            "positive": ["9", 0],
            "negative": ["9", 1],
            "latent_image": ["9", 2],
            "seed": 42,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": "euler_ancestral",
            "scheduler": "beta",
            "denoise": 1.0,
        },
    }
    wf["11"] = {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["10", 0],
            "vae": ["3", 0],
        },
    }
    wf["12"] = {
        "class_type": "SaveAnimatedWEBP",
        "inputs": {
            "images": ["11", 0],
            "filename_prefix": output_prefix,
            "fps": float(fps),
            "lossless": False,
            "quality": 85,
            "method": "default",
        },
    }

    return wf


def _upload_image(image_path: pathlib.Path) -> str:
    """Sube imagen a ComfyUI y devuelve el filename."""
    with open(image_path, "rb") as f:
        data = f.read()
    boundary = "----FormBoundary" + uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{image_path.name}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{COMFYUI_URL}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["name"]


def _run_workflow(wf: dict, client_id: str) -> float:
    """Envía workflow y espera hasta que termine. Devuelve segundos."""
    prompt_data = json.dumps({"prompt": wf, "client_id": client_id}).encode()
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=prompt_data,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp_obj = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"ComfyUI 400: {body[:1500]}") from e
    with resp_obj as resp:
        prompt_id = json.loads(resp.read())["prompt_id"]

    ws = websocket.WebSocket()
    ws.connect(f"{COMFYUI_WS}/ws?clientId={client_id}")

    t0 = time.time()
    try:
        while True:
            raw = ws.recv()
            if isinstance(raw, bytes):
                continue  # preview frame binario, ignorar
            msg = json.loads(raw)
            if msg.get("type") == "executing":
                data = msg.get("data", {})
                if data.get("node") is None and data.get("prompt_id") == prompt_id:
                    break
    finally:
        ws.close()

    return time.time() - t0


def run_benchmark():
    client_id = uuid.uuid4().hex
    print(f"\n{'='*60}")
    print("  BENCHMARK WAN 2.1 I2V")
    print(f"{'='*60}\n")

    # Subir imagen de prueba
    print("Subiendo imagen de prueba a ComfyUI...", flush=True)
    img_name = _upload_image(TEST_IMG)
    print(f"  -> {img_name}\n")

    configs = [
        # (label,              steps, frames, causvid, teacache)
        ("A  Baseline 50s/17f", 50,   17,     False,   False),
        ("B  CausVid  8s/17f",   8,   17,     True,    False),
        ("C  +TeaCache 8s/17f",  8,   17,     True,    True),
        ("D  +TeaCache 8s/49f",  8,   49,     True,    True),
    ]

    results = []
    for label, steps, frames, causvid, tc in configs:
        fps = 16
        duration_s = frames / fps
        print(f"Config {label} | {frames} frames ({duration_s:.1f}s @ {fps}fps) ...", flush=True)

        prefix = f"bench_{label[0].lower()}_{steps}s_{frames}f"
        wf = _build_workflow(
            image_filename=img_name,
            steps=steps,
            num_frames=frames,
            use_causvid=causvid,
            use_teacache=tc,
            output_prefix=prefix,
        )

        elapsed = _run_workflow(wf, client_id)
        ratio = elapsed / duration_s
        results.append((label, steps, frames, duration_s, elapsed, ratio))
        print(f"  Tiempo: {elapsed:.1f}s  ({ratio:.1f}x realtime)", flush=True)

        # Convertir WEBP → MP4 para revisión visual
        webp_files = sorted(COMFYUI_OUT.glob(f"{prefix}*.webp"), key=lambda p: p.stat().st_mtime)
        if webp_files:
            webp = webp_files[-1]
            mp4 = BENCH_OUT / f"{prefix}.mp4"
            subprocess.run([
                FFMPEG, "-y", "-i", str(webp),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps), str(mp4)
            ], capture_output=True)
            print(f"  Video  : {mp4.name}\n", flush=True)
        else:
            print(f"  (WEBP no encontrado en {COMFYUI_OUT})\n", flush=True)

    # ── Resumen ────────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  RESULTADOS")
    print(f"{'='*60}")
    print(f"{'Config':<28} {'Steps':>5} {'Frames':>6} {'Dur':>5} {'Tiempo':>8} {'Factor':>8}")
    print("-" * 60)
    for label, steps, frames, dur, elapsed, ratio in results:
        print(f"  {label:<26} {steps:>5} {frames:>6} {dur:>4.1f}s {elapsed:>7.1f}s {ratio:>6.1f}x")

    # Extrapolación a 5 segundos (80 frames @ 16fps)
    print(f"\n{'='*60}")
    print("  EXTRAPOLACION a 5s (80 frames)")
    print(f"{'='*60}")
    for label, steps, frames, dur, elapsed, ratio in results:
        est = elapsed * (80 / frames)
        print(f"  {label:<26} => ~{est/60:.1f} min por clip de 5s")

    print()


if __name__ == "__main__":
    run_benchmark()
