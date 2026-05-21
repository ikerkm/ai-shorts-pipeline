"""
Test standalone de Wan 2.2 I2V con Lightning LoRA 4-step.

Arquitectura nueva vs v3.1:
  - 2 modelos GGUF (HighNoise + LowNoise) con KSamplerAdvanced 2 etapas
  - CLIPLoader fp8 safetensors (sin CLIPVision)
  - Lightning LoRA 4 steps (vs CausVid 8 steps)
  - VAEDecodeTiled (vs VAEDecode)

Uso:
    PYTHONUTF8=1 python test_wan22.py
"""
import json
import time
import uuid
import subprocess
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

COMFYUI_URL = "http://localhost:8188"
FFMPEG = r"C:\Users\ikerk\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"

# Modelos Wan 2.2
WAN22_UNET_HIGH = "Wan2.2-I2V-A14B-HighNoise-Q6_K.gguf"
WAN22_UNET_LOW  = "Wan2.2-I2V-A14B-LowNoise-Q6_K.gguf"
WAN22_CLIP      = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
WAN22_VAE       = "wan_2.1_vae.safetensors"
WAN22_LORA_HIGH = "Wan2.2-Lightning_I2V-A14B-4steps-lora_HIGH_fp16.safetensors"
WAN22_LORA_LOW  = "Wan2.2-Lightning_I2V-A14B-4steps-lora_LOW_fp16.safetensors"

WAN22_WIDTH  = 480
WAN22_HEIGHT = 832
WAN22_FPS    = 16
WAN22_FRAMES = 125  # 7.8s — el clip que el usuario confirma correcto en ComfyUI

# Imagen de prueba (ya en ComfyUI input)
TEST_IMAGE      = "pipeline_00099_.png"
TEST_PROMPT     = "slow camera push forward, stars twinkling, light rays expanding, cinematic motion, smooth movement"
TARGET_DURATION = 8.0   # segundos — simula una escena real del pipeline
OUTPUT_PATH     = Path(r"Z:\AI\pipeline\output\test_wan22.mp4")


def _build_workflow(image_filename: str, video_prompt: str, seed: int, num_frames: int) -> dict:
    return {
        # ── Modelos ──────────────────────────────────────────────────────────
        "1": {"class_type": "LoaderGGUF",
              "inputs": {"gguf_name": WAN22_UNET_HIGH}},
        "2": {"class_type": "LoaderGGUF",
              "inputs": {"gguf_name": WAN22_UNET_LOW}},
        "3": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": WAN22_CLIP, "type": "wan", "device": "cpu"}},
        "4": {"class_type": "VAELoader",
              "inputs": {"vae_name": WAN22_VAE}},

        # ── Imagen ───────────────────────────────────────────────────────────
        "5": {"class_type": "LoadImage",
              "inputs": {"image": image_filename, "upload": "image"}},

        # ── LoRA solo modelo (sin CLIP) ───────────────────────────────────────
        "6": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["1", 0],
                         "lora_name": WAN22_LORA_HIGH, "strength_model": 1.0}},
        "7": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["2", 0],
                         "lora_name": WAN22_LORA_LOW,  "strength_model": 1.0}},

        # ── Prompts ───────────────────────────────────────────────────────────
        "8": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["3", 0], "text": video_prompt}},
        "9": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["3", 0], "text": ""}},

        # ── Latente I2V ───────────────────────────────────────────────────────
        "10": {"class_type": "WanImageToVideo",
               "inputs": {
                   "positive":    ["8",  0],
                   "negative":    ["9",  0],
                   "vae":         ["4",  0],
                   "start_image": ["5",  0],
                   "width":       WAN22_WIDTH,
                   "height":      WAN22_HEIGHT,
                   "length":      num_frames,
                   "batch_size":  1,
               }},

        # ── Sampler etapa 1: HighNoise (steps 0→2) ───────────────────────────
        "11": {"class_type": "KSamplerAdvanced",
               "inputs": {
                   "model":                    ["6",  0],
                   "positive":                 ["10", 0],
                   "negative":                 ["10", 1],
                   "latent_image":             ["10", 2],
                   "add_noise":                "enable",
                   "noise_seed":               seed,
                   "steps":                    4,
                   "cfg":                      1.0,
                   "sampler_name":             "lcm",
                   "scheduler":               "simple",
                   "start_at_step":            0,
                   "end_at_step":              2,
                   "return_with_leftover_noise": "enable",
               }},

        # ── Sampler etapa 2: LowNoise (steps 2→fin) ──────────────────────────
        "12": {"class_type": "KSamplerAdvanced",
               "inputs": {
                   "model":                    ["7",  0],
                   "positive":                 ["10", 0],
                   "negative":                 ["10", 1],
                   "latent_image":             ["11", 0],
                   "add_noise":                "disable",
                   "noise_seed":               0,
                   "steps":                    4,
                   "cfg":                      1.0,
                   "sampler_name":             "lcm",
                   "scheduler":               "simple",
                   "start_at_step":            2,
                   "end_at_step":              10000,
                   "return_with_leftover_noise": "disable",
               }},

        # ── Decode tiled ─────────────────────────────────────────────────────
        "13": {"class_type": "VAEDecodeTiled",
               "inputs": {
                   "samples":          ["12", 0],
                   "vae":              ["4",  0],
                   "tile_size":        256,
                   "overlap":          64,
                   "temporal_size":    32,
                   "temporal_overlap": 8,
               }},

        # ── Salida MP4 via VHS ────────────────────────────────────────────────
        "14": {"class_type": "VHS_VideoCombine",
               "inputs": {
                   "images":          ["13", 0],
                   "frame_rate":      float(WAN22_FPS),
                   "loop_count":      0,
                   "filename_prefix": "wan22_test",
                   "format":          "video/h264-mp4",
                   "pingpong":        False,
                   "save_output":     True,
                   "pix_fmt":         "yuv420p",
                   "crf":             19,
                   "save_metadata":   True,
                   "trim_to_audio":   False,
               }},
    }


def _queue_prompt(workflow: dict) -> str:
    client_id = str(uuid.uuid4())
    data = json.dumps({"prompt": workflow, "client_id": client_id}).encode()
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt", data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ComfyUI error: {e.read().decode()[:800]}") from e
    return json.loads(resp.read())["prompt_id"]


def _wait_for_completion(prompt_id: str, timeout: int = 600) -> dict:
    start = time.time()
    while time.time() - start < timeout:
        history = json.loads(
            urllib.request.urlopen(f"{COMFYUI_URL}/history/{prompt_id}").read()
        )
        if prompt_id in history:
            entry = history[prompt_id]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                msgs = status.get("messages", [])
                err_msg = "unknown error"
                for m in msgs:
                    if isinstance(m, (list, tuple)) and m[0] == "execution_error":
                        err_msg = m[1].get("exception_message", err_msg)
                        break
                raise RuntimeError(f"Wan 2.2 error: {err_msg}")
            if status.get("completed"):
                return entry
        time.sleep(3)
    raise TimeoutError(f"Wan 2.2 job timed out after {timeout}s")


def _valid_wan_frames(n: int) -> int:
    """Redondea al valor válido más cercano para Wan (4k+1: 1,5,9,13,...)."""
    n = max(9, n)
    return ((n - 1) // 4) * 4 + 1


def main():
    num_frames = WAN22_FRAMES
    clip_duration = num_frames / WAN22_FPS

    print(f"\n{'='*60}")
    print(f"TEST WAN 2.2 I2V — diagnóstico PTS")
    print(f"  Clip: {num_frames} frames ({clip_duration:.1f}s)")
    print(f"  Fix:  setpts=PTS-STARTPTS para normalizar timestamps")
    print(f"{'='*60}\n")

    seed = int(time.time()) % 100000  # seed aleatorio para no usar caché
    t0 = time.time()

    print("[1/4] Enviando workflow a ComfyUI...")
    wf = _build_workflow(TEST_IMAGE, TEST_PROMPT, seed, num_frames)
    prompt_id = _queue_prompt(wf)
    print(f"      prompt_id: {prompt_id}")

    print("[2/4] Esperando generación Wan 2.2...")
    t_gen_start = time.time()
    result = _wait_for_completion(prompt_id, timeout=900)
    t_gen = time.time() - t_gen_start
    print(f"      Generación completada en {t_gen:.1f}s")

    print("[3/4] Obteniendo MP4 de ComfyUI (lectura directa de disco)...")
    outputs = result.get("outputs", {})
    mp4_filename = None
    for node_output in outputs.values():
        for key in ("gifs", "videos"):
            if key in node_output:
                mp4_filename = node_output[key][0]["filename"]
                break
        if mp4_filename:
            break

    if not mp4_filename:
        raise RuntimeError("Sin output VHS en history — revisa los logs")

    # Leer directamente del disco de ComfyUI para evitar posible corrupción del download HTTP
    src_path = Path(r"Z:\AI\ComfyUI\output") / mp4_filename
    mp4_tmp   = Path(r"Z:\AI\pipeline\output\test_wan22_raw.mp4")
    mp4_tmp.write_bytes(src_path.read_bytes())
    print(f"      Copiado: {src_path.name}  ({src_path.stat().st_size//1024}KB)")

    FFPROBE = FFMPEG.replace("ffmpeg.exe", "ffprobe.exe")

    # Probe de streams
    probe_s = subprocess.run(
        [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_streams", str(mp4_tmp)],
        capture_output=True, text=True,
    )
    try:
        vs = next(s for s in json.loads(probe_s.stdout)["streams"] if s["codec_type"] == "video")
        print(f"      Streams: fps={vs.get('r_frame_rate')}  dur={vs.get('duration')}s  frames={vs.get('nb_frames')}  start_pts={vs.get('start_pts')}")
    except Exception as e:
        print(f"      probe_streams error: {e}")

    # Probe de paquetes — primeros y últimos 3 PTS reales
    probe_p = subprocess.run(
        [FFPROBE, "-v", "quiet", "-print_format", "json",
         "-show_packets", "-select_streams", "v:0", str(mp4_tmp)],
        capture_output=True, text=True,
    )
    try:
        pkts = json.loads(probe_p.stdout)["packets"]
        pts_vals = [p.get("pts", p.get("dts", "?")) for p in pkts]
        print(f"      PTS primeros 5: {pts_vals[:5]}")
        print(f"      PTS últimos  5: {pts_vals[-5:]}")
        print(f"      Total paquetes: {len(pts_vals)}")
    except Exception as e:
        print(f"      probe_packets error: {e}")

    print("[4/4] FFmpeg: -r 16 en input para ignorar timing del contenedor → escala → MP4...")
    # -r 16 ANTES de -i fuerza fps constante al leer, ignorando stts/ctts del mp4
    # que VHS puede generar con timing incorrecto para players
    cmd = [
        FFMPEG, "-y",
        "-r", str(WAN22_FPS),
        "-i", str(mp4_tmp),
        "-vf", "scale=-2:1920:flags=lanczos,crop=1080:1920",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-r", "30",
        str(OUTPUT_PATH),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {proc.stderr[-600:]}")
    print(f"      Raw guardado en: {mp4_tmp}")

    t_total = time.time() - t0
    size_mb = OUTPUT_PATH.stat().st_size / 1024 / 1024

    print(f"\n{'='*60}")
    print(f"RESULTADO:")
    print(f"  Tiempo Wan 2.2: {t_gen:.1f}s")
    print(f"  Tiempo total:   {t_total:.1f}s")
    print(f"  Output final:   {OUTPUT_PATH} ({size_mb:.1f}MB)")
    print(f"  Raw MP4:        {mp4_tmp}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
