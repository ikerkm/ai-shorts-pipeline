"""
Wan 2.2 I2V video generator — 2-stage pipeline.

Stage 1 (ComfyUI): Wan 2.2 Lightning 4-step → raw 480×832 @16fps H264
Stage 2 (ComfyUI): VHS_LoadVideo(format=Wan) → RTXVideoSuperResolution →
                   RIFE VFI ×2 → LayerFilter Sharp → 1080×1920 @32fps H264
Stage 3 (FFmpeg):  fps=30 + trim to duration_s + ping-pong loop if needed

No Pillow dependency. FFmpeg only used for final fps/duration fix.
"""
import json
import shutil
import time
import uuid
import subprocess
import urllib.request
import urllib.error
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    COMFYUI_URL, FFMPEG,
    WAN_UNET_HIGH, WAN_UNET_LOW, WAN_CLIP, WAN_VAE,
    WAN_LORA_HIGH, WAN_LORA_LOW,
    WAN_FPS, WAN_WIDTH, WAN_HEIGHT, WAN_CLIP_FRAMES,
    VIDEO_WIDTH, VIDEO_HEIGHT,
    COMFYUI_OUTPUT_DIR, COMFYUI_INPUT_DIR,
)

_RIFE_MULTIPLIER = 2
_UPSCALED_FPS    = WAN_FPS * _RIFE_MULTIPLIER  # 32fps after RIFE ×2


# ── Upload helpers ─────────────────────────────────────────────────────────────

def _upload_image(image_path: Path) -> str:
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


def _copy_to_input(src_path: Path) -> str:
    """Copy a file to ComfyUI input folder with a unique name. Returns filename."""
    unique_name = f"_pipe_{uuid.uuid4().hex[:8]}_{src_path.name}"
    shutil.copy2(src_path, COMFYUI_INPUT_DIR / unique_name)
    return unique_name


# ── Workflow builders ──────────────────────────────────────────────────────────

def _valid_wan_frames(n: int) -> int:
    """Round to nearest valid Wan frame count (4k+1: 1,5,9,13,...)."""
    n = max(9, n)
    return ((n - 1) // 4) * 4 + 1


def _build_wan_workflow(image_filename: str, video_prompt: str, seed: int, num_frames: int) -> dict:
    """Stage 1: Wan 2.2 Lightning 4-step → raw 480×832 @16fps MP4."""
    return {
        "1": {"class_type": "LoaderGGUF",
              "inputs": {"gguf_name": WAN_UNET_HIGH}},
        "2": {"class_type": "LoaderGGUF",
              "inputs": {"gguf_name": WAN_UNET_LOW}},
        "3": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": WAN_CLIP, "type": "wan", "device": "cpu"}},
        "4": {"class_type": "VAELoader",
              "inputs": {"vae_name": WAN_VAE}},
        "5": {"class_type": "LoadImage",
              "inputs": {"image": image_filename, "upload": "image"}},
        "6": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["1", 0], "lora_name": WAN_LORA_HIGH, "strength_model": 1.0}},
        "7": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["2", 0], "lora_name": WAN_LORA_LOW,  "strength_model": 1.0}},
        "8": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["3", 0], "text": video_prompt}},
        "9": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["3", 0], "text": "flickering, flashing, strobing, light variation, inconsistent lighting, brightness variation, pulsing light, unstable exposure, flickering flames, pulsing torches, candle flicker, fire animation, oscillating light source"}},
        "10": {"class_type": "WanImageToVideo",
               "inputs": {
                   "positive":    ["8",  0],
                   "negative":    ["9",  0],
                   "vae":         ["4",  0],
                   "start_image": ["5",  0],
                   "width":       WAN_WIDTH,
                   "height":      WAN_HEIGHT,
                   "length":      num_frames,
                   "batch_size":  1,
               }},
        "11": {"class_type": "KSamplerAdvanced",
               "inputs": {
                   "model":                     ["6",  0],
                   "positive":                  ["10", 0],
                   "negative":                  ["10", 1],
                   "latent_image":              ["10", 2],
                   "add_noise":                 "enable",
                   "noise_seed":                seed,
                   "steps":                     4,
                   "cfg":                       1.0,
                   "sampler_name":              "lcm",
                   "scheduler":                 "simple",
                   "start_at_step":             0,
                   "end_at_step":               2,
                   "return_with_leftover_noise": "enable",
               }},
        "12": {"class_type": "KSamplerAdvanced",
               "inputs": {
                   "model":                     ["7",  0],
                   "positive":                  ["10", 0],
                   "negative":                  ["10", 1],
                   "latent_image":              ["11", 0],
                   "add_noise":                 "disable",
                   "noise_seed":                0,
                   "steps":                     4,
                   "cfg":                       1.0,
                   "sampler_name":              "lcm",
                   "scheduler":                 "simple",
                   "start_at_step":             2,
                   "end_at_step":               10000,
                   "return_with_leftover_noise": "disable",
               }},
        "13": {"class_type": "VAEDecodeTiled",
               "inputs": {
                   "samples":          ["12", 0],
                   "vae":              ["4",  0],
                   "tile_size":        256,
                   "overlap":          128,
                   "temporal_size":    32,
                   "temporal_overlap": 16,
               }},
        "14": {"class_type": "VHS_VideoCombine",
               "inputs": {
                   "images":          ["13", 0],
                   "frame_rate":      float(WAN_FPS),
                   "loop_count":      0,
                   "filename_prefix": "wan_raw",
                   "format":          "video/h264-mp4",
                   "pingpong":        False,
                   "save_output":     True,
                   "pix_fmt":         "yuv420p",
                   "crf":             19,
                   "save_metadata":   False,
                   "trim_to_audio":   False,
               }},
    }


def _build_upscaler_workflow(video_filename: str) -> dict:
    """Stage 2: RTX upscale + RIFE ×2 → 1080×1920 @32fps.

    VHS_LoadVideo format='Wan' correctly decodes Wan VHS B-frame timing.
    """
    return {
        "1": {"class_type": "VHS_LoadVideo",
              "inputs": {
                  "video":              video_filename,
                  "force_rate":         0.0,
                  "custom_width":       0,
                  "custom_height":      0,
                  "frame_load_cap":     0,
                  "skip_first_frames":  0,
                  "select_every_nth":   1,
                  "format":             "Wan",
              }},
        # RTX: 480×832 → 1080×1920
        "2": {"class_type": "RTXVideoSuperResolution",
              "inputs": {
                  "images":             ["1", 0],
                  "resize_type":        "target dimensions",
                  "resize_type.width":  VIDEO_WIDTH,    # 1080
                  "resize_type.height": VIDEO_HEIGHT,   # 1920
                  "quality":            "ULTRA",
              }},
        # RIFE ×2: 16fps → 32fps
        "3": {"class_type": "RIFE VFI",
              "inputs": {
                  "frames":                     ["2", 0],
                  "ckpt_name":                  "rife49.pth",
                  "clear_cache_after_n_frames":  10,
                  "multiplier":                  _RIFE_MULTIPLIER,
                  "fast_mode":                   False,
                  "ensemble":                    True,
                  "scale_factor":                1,
                  "dtype":                       "float32",
                  "torch_compile":               False,
                  "batch_size":                  1,
              }},
        # Sharpening pass
        "4": {"class_type": "LayerFilter: Sharp & Soft",
              "inputs": {
                  "images":  ["3", 0],
                  "enhance": "sharp",
              }},
        # Final output: 1080×1920 @32fps H264
        "5": {"class_type": "VHS_VideoCombine",
              "inputs": {
                  "images":          ["4", 0],
                  "frame_rate":      float(_UPSCALED_FPS),
                  "loop_count":      0,
                  "filename_prefix": "wan_up",
                  "format":          "video/h264-mp4",
                  "pingpong":        False,
                  "save_output":     True,
                  "pix_fmt":         "yuv420p",
                  "crf":             19,
                  "save_metadata":   False,
                  "trim_to_audio":   False,
              }},
    }


# ── ComfyUI API helpers ────────────────────────────────────────────────────────

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
        raise RuntimeError(f"ComfyUI error: {e.read().decode()[:500]}") from e
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
                raise RuntimeError(f"ComfyUI error: {err_msg}")
            if status.get("completed"):
                return entry
        time.sleep(3)
    raise TimeoutError(f"ComfyUI job timed out after {timeout}s")


def _get_vhs_output(result: dict) -> Path:
    """Extract the saved MP4 path from a VHS_VideoCombine history entry."""
    outputs = result.get("outputs", {})
    for node_output in outputs.values():
        for key in ("gifs", "videos"):
            if key in node_output:
                vid = node_output[key][0]
                subfolder = vid.get("subfolder", "")
                rel = Path(subfolder) / vid["filename"] if subfolder else vid["filename"]
                src = COMFYUI_OUTPUT_DIR / rel
                if src.exists():
                    return src
    raise RuntimeError("No VHS output found in ComfyUI history")


# ── Post-processing ────────────────────────────────────────────────────────────

def _ffmpeg_trim(src: Path, duration_s: float, output: Path):
    """Re-encode fixing VHS broken stts/ctts.

    VHS_VideoCombine genera MP4 con timestamps incorrectos que los players no
    reproducen bien. setpts=N/FPS/TB regenera PTS desde el contador de frames
    (N=0,1,2,...) ignorando completamente los PTS del input. -map_metadata -1
    elimina cualquier edit list rota que VHS pueda haber escrito.
    """
    cmd = [
        FFMPEG, "-y",
        "-stream_loop", "-1",
        "-r", str(_UPSCALED_FPS),
        "-i", str(src),
        "-vf", f"setpts=N/{_UPSCALED_FPS}/TB",
        "-avoid_negative_ts", "make_zero",
        "-map_metadata", "-1",
        "-map_chapters", "-1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-t", str(duration_s),
        str(output),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {proc.stderr[-400:]}")


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_wan_video(
    image_path: Path,
    video_prompt: str,
    seed: int,
    output_path: Path,
    duration_s: float,
) -> Path:
    """
    Generate Wan 2.2 I2V clip from image_path, saved as 1080×1920 @30fps MP4.

    - Stage 1: Wan 2.2 Lightning 4-step → raw 480×832 @16fps (up to 7.8s)
    - Stage 2: RTX ULTRA upscale → RIFE ×2 → 1080×1920 @32fps
    - Stage 3: FFmpeg fps=30 + trim to duration_s + ping-pong if needed
    """
    gen_frames = _valid_wan_frames(min(WAN_CLIP_FRAMES, int(duration_s * WAN_FPS) + 4))
    wan_duration = gen_frames / WAN_FPS

    print(f"    [WAN] {gen_frames}f ({wan_duration:.1f}s → {duration_s:.1f}s clip)")

    # Stage 1 — Wan 2.2 generation
    img_name = _upload_image(image_path)
    wf = _build_wan_workflow(img_name, video_prompt, seed, gen_frames)
    pid = _queue_prompt(wf)
    result = _wait_for_completion(pid, timeout=600)
    raw_src = _get_vhs_output(result)

    print(f"    [UP]  RTX ULTRA + RIFE ×{_RIFE_MULTIPLIER} → 1080×1920 @{_UPSCALED_FPS}fps")

    # Stage 2 — RTX upscale + RIFE (copy raw to input so VHS_LoadVideo can find it)
    vid_name = _copy_to_input(raw_src)
    try:
        up_wf = _build_upscaler_workflow(vid_name)
        up_pid = _queue_prompt(up_wf)
        up_result = _wait_for_completion(up_pid, timeout=300)
        up_src = _get_vhs_output(up_result)
    finally:
        (COMFYUI_INPUT_DIR / vid_name).unlink(missing_ok=True)

    # Stage 3 — trim a duration_s exacto (stream copy, sin re-encode)
    _ffmpeg_trim(up_src, duration_s, output_path)

    return output_path
