"""
Generación de imágenes para anuncios con coherencia de producto.

Flujo en dos fases:
  1. generate_product_hero()  → imagen limpia del producto (text2img normal)
  2. generate_scene_from_hero() → cada escena img2img desde la hero (denoise=0.65)

El img2img preserva ~35% de la estructura original (forma, colores, proporciones del
producto) mientras permite que el prompt de escena cambie el contexto.
Usa solo nodos core de ComfyUI — no requiere plugins adicionales.
"""
import json
import shutil
import time
import uuid
import urllib.request
import urllib.parse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    COMFYUI_URL, VIDEO_WIDTH, VIDEO_HEIGHT,
    FLUX_STEPS, FLUX_CFG, FLUX_MODEL, FLUX_CLIP1, FLUX_CLIP2, FLUX_VAE,
    IMAGE_STYLE_SUFFIX, COMFYUI_INPUT_DIR,
)

HERO_DENOISE   = 1.0   # hero: text2img puro
SCENE_DENOISE  = 0.65  # escenas: preserva ~35% de la estructura del hero

HERO_STYLE_SUFFIX = (
    ", isolated product, centered composition, commercial product photography hero shot, "
    "studio lighting, no people, no context, just the product, "
    "9:16 vertical portrait format, no text overlay, no watermark"
)


# ── Upload helpers (duplicados de video_generator para evitar imports cruzados) ──

def _upload_hero_to_comfyui(image_path: Path) -> str:
    """Sube imagen al endpoint /upload/image de ComfyUI. Devuelve el nombre interno."""
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


# ── Workflow builders ─────────────────────────────────────────────────────────

def _build_hero_workflow(prompt: str, seed: int, width: int, height: int) -> dict:
    """Text2img normal — misma arquitectura que image_generator.py pero sin LoRA."""
    return {
        "1": {"class_type": "UnetLoaderGGUF",    "inputs": {"unet_name": FLUX_MODEL}},
        "2": {"class_type": "DualCLIPLoaderGGUF", "inputs": {
            "clip_name1": FLUX_CLIP1, "clip_name2": FLUX_CLIP2, "type": "flux",
        }},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": FLUX_VAE}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {
            "text": prompt + HERO_STYLE_SUFFIX, "clip": ["2", 0],
        }},
        "5": {"class_type": "FluxGuidance", "inputs": {
            "conditioning": ["4", 0], "guidance": FLUX_CFG,
        }},
        "6": {"class_type": "RandomNoise",    "inputs": {"noise_seed": seed}},
        "7": {"class_type": "BasicScheduler", "inputs": {
            "model": ["1", 0], "scheduler": "normal",
            "steps": FLUX_STEPS, "denoise": HERO_DENOISE,
        }},
        "8": {"class_type": "KSamplerSelect",      "inputs": {"sampler_name": "euler"}},
        "9": {"class_type": "EmptySD3LatentImage",  "inputs": {
            "width": width, "height": height, "batch_size": 1,
        }},
        "10": {"class_type": "BasicGuider", "inputs": {
            "model": ["1", 0], "conditioning": ["5", 0],
        }},
        "11": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["6", 0], "guider": ["10", 0],
            "sampler": ["8", 0], "sigmas": ["7", 0], "latent_image": ["9", 0],
        }},
        "12": {"class_type": "VAEDecode",  "inputs": {"samples": ["11", 0], "vae": ["3", 0]}},
        "13": {"class_type": "SaveImage",  "inputs": {"images": ["12", 0], "filename_prefix": "pipeline_hero"}},
    }


def _build_img2img_workflow(scene_prompt: str, hero_image_name: str,
                            seed: int, denoise: float,
                            width: int, height: int) -> dict:
    """
    Img2img desde la imagen hero del producto.
    LoadImage → VAEEncode reemplaza EmptySD3LatentImage.
    BasicScheduler con denoise < 1.0 preserva estructura del hero.
    """
    return {
        "1": {"class_type": "UnetLoaderGGUF",    "inputs": {"unet_name": FLUX_MODEL}},
        "2": {"class_type": "DualCLIPLoaderGGUF", "inputs": {
            "clip_name1": FLUX_CLIP1, "clip_name2": FLUX_CLIP2, "type": "flux",
        }},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": FLUX_VAE}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {
            "text": scene_prompt + IMAGE_STYLE_SUFFIX, "clip": ["2", 0],
        }},
        "5": {"class_type": "FluxGuidance", "inputs": {
            "conditioning": ["4", 0], "guidance": FLUX_CFG,
        }},
        "6": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "7": {"class_type": "BasicScheduler", "inputs": {
            "model": ["1", 0], "scheduler": "normal",
            "steps": FLUX_STEPS, "denoise": denoise,
        }},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        # img2img: carga hero → codifica a latent → usa como punto de partida
        "9":  {"class_type": "LoadImage",  "inputs": {"image": hero_image_name}},
        "10": {"class_type": "VAEEncode",  "inputs": {"pixels": ["9", 0], "vae": ["3", 0]}},
        "11": {"class_type": "BasicGuider", "inputs": {
            "model": ["1", 0], "conditioning": ["5", 0],
        }},
        "12": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise":        ["6",  0],
            "guider":       ["11", 0],
            "sampler":      ["8",  0],
            "sigmas":       ["7",  0],
            "latent_image": ["10", 0],  # hero latent como init
        }},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["3", 0]}},
        "14": {"class_type": "SaveImage", "inputs": {
            "images": ["13", 0], "filename_prefix": "pipeline_ad",
        }},
    }


# ── ComfyUI helpers ───────────────────────────────────────────────────────────

def _queue_prompt(workflow: dict) -> str:
    client_id = str(uuid.uuid4())
    data = json.dumps({"prompt": workflow, "client_id": client_id}).encode()
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt", data=data,
        headers={"Content-Type": "application/json"}
    )
    return json.loads(urllib.request.urlopen(req).read())["prompt_id"]


def _wait_for_completion(prompt_id: str, timeout: int = 1800) -> dict:
    start = time.time()
    while time.time() - start < timeout:
        history = json.loads(
            urllib.request.urlopen(f"{COMFYUI_URL}/history/{prompt_id}").read()
        )
        if prompt_id in history:
            entry = history[prompt_id]
            if entry.get("status", {}).get("completed"):
                return entry
        time.sleep(2)
    raise TimeoutError(f"ComfyUI job timed out after {timeout}s")


def _download_image(filename: str, subfolder: str, output_path: Path) -> Path:
    params = urllib.parse.urlencode({
        "filename": filename, "subfolder": subfolder, "type": "output"
    })
    output_path.write_bytes(
        urllib.request.urlopen(f"{COMFYUI_URL}/view?{params}").read()
    )
    return output_path


def _run_workflow_and_save(workflow: dict, output_path: Path) -> Path:
    pid = _queue_prompt(workflow)
    result = _wait_for_completion(pid)
    for node_output in result.get("outputs", {}).values():
        if "images" in node_output:
            img = node_output["images"][0]
            return _download_image(img["filename"], img.get("subfolder", ""), output_path)
    raise RuntimeError(f"No image output from ComfyUI for prompt_id={pid}")


# ── API pública ───────────────────────────────────────────────────────────────

def generate_product_hero(visual_anchor: str, visual_style: str,
                          seed: int, output_path: Path,
                          width: int = VIDEO_WIDTH,
                          height: int = VIDEO_HEIGHT) -> Path:
    """
    Genera la imagen hero del producto con fondo coherente al estilo visual.
    El fondo se deriva del visual_style para que img2img no herede siempre blanco.
    """
    hero_prompt = (
        f"{visual_anchor}, "
        f"{visual_style}, "
        "product hero shot, centered, isolated, no people"
    )
    print(f"    [HERO] {hero_prompt[:80]}...")
    wf = _build_hero_workflow(hero_prompt, seed, width, height)
    return _run_workflow_and_save(wf, output_path)


def generate_scene_from_hero(scene_prompt: str, negative: str,
                             hero_path: Path, seed: int,
                             output_path: Path,
                             denoise: float = SCENE_DENOISE,
                             width: int = VIDEO_WIDTH,
                             height: int = VIDEO_HEIGHT) -> Path:
    """
    Genera imagen de escena usando img2img desde la hero image del producto.
    denoise=0.65 preserva ~35% de la estructura → producto coherente entre escenas.
    """
    # Sube la hero image a ComfyUI para que LoadImage pueda acceder a ella
    hero_name = _upload_hero_to_comfyui(hero_path)
    print(f"    [IMG2IMG denoise={denoise}] {scene_prompt[:70]}...")
    wf = _build_img2img_workflow(scene_prompt, hero_name, seed, denoise, width, height)
    return _run_workflow_and_save(wf, output_path)
