import json
import time
import uuid
import urllib.request
import urllib.parse
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))
from pathlib import Path
from config import COMFYUI_URL, VIDEO_WIDTH, VIDEO_HEIGHT, FLUX_STEPS, FLUX_CFG
from config import FLUX_MODEL, FLUX_CLIP1, FLUX_CLIP2, FLUX_VAE, IMAGE_STYLE_SUFFIX


def _build_workflow(prompt: str, seed: int, width: int, height: int,
                    lora_name: str = None, lora_strength: float = 0.8) -> dict:
    model_src = ["1", 0]

    workflow = {
        "1": {"class_type": "UnetLoaderGGUF",    "inputs": {"unet_name": FLUX_MODEL}},
        "2": {"class_type": "DualCLIPLoaderGGUF", "inputs": {
            "clip_name1": FLUX_CLIP1, "clip_name2": FLUX_CLIP2, "type": "flux",
        }},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": FLUX_VAE}},
    }

    if lora_name:
        workflow["10"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": ["1", 0],
            "lora_name": lora_name,
            "strength_model": lora_strength,
        }}
        model_src = ["10", 0]

    workflow.update({
        # Prompt → FluxGuidance (Flux no usa negative prompt)
        "4": {"class_type": "CLIPTextEncode", "inputs": {
            "text": prompt + IMAGE_STYLE_SUFFIX, "clip": ["2", 0],
        }},
        "5": {"class_type": "FluxGuidance", "inputs": {
            "conditioning": ["4", 0], "guidance": FLUX_CFG,
        }},
        # Noise + scheduler + sampler
        "6": {"class_type": "RandomNoise",    "inputs": {"noise_seed": seed}},
        "7": {"class_type": "BasicScheduler", "inputs": {
            "model": ["1", 0],   # siempre base model para los sigmas
            "scheduler": "normal",
            "steps": FLUX_STEPS,
            "denoise": 1.0,
        }},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        # Latente vacío
        "9": {"class_type": "EmptySD3LatentImage", "inputs": {
            "width": width, "height": height, "batch_size": 1,
        }},
        # Guider con el modelo (post-LoRA si aplica)
        "11": {"class_type": "BasicGuider", "inputs": {
            "model": model_src, "conditioning": ["5", 0],
        }},
        # Sampler avanzado
        "12": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise":        ["6",  0],
            "guider":       ["11", 0],
            "sampler":      ["8",  0],
            "sigmas":       ["7",  0],
            "latent_image": ["9",  0],
        }},
        # Decode + guardar
        "13": {"class_type": "VAEDecode",  "inputs": {"samples": ["12", 0], "vae": ["3", 0]}},
        "14": {"class_type": "SaveImage",  "inputs": {"images": ["13", 0], "filename_prefix": "pipeline"}},
    })
    return workflow


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
    raise TimeoutError(f"ComfyUI image job timed out after {timeout}s")


def _download_image(filename: str, subfolder: str, output_path: Path) -> Path:
    params = urllib.parse.urlencode({
        "filename": filename, "subfolder": subfolder, "type": "output"
    })
    output_path.write_bytes(
        urllib.request.urlopen(f"{COMFYUI_URL}/view?{params}").read()
    )
    return output_path


def generate_image(prompt: str, negative: str = "", seed: int = 0,
                   output_path: Path = None,
                   width: int = VIDEO_WIDTH, height: int = VIDEO_HEIGHT,
                   style_prefix: str = "",
                   lora_name: str = None, lora_strength: float = 0.8) -> Path:
    full_prompt = f"{style_prefix} {prompt}".strip() if style_prefix else prompt
    tag = f" [LoRA: {lora_name}]" if lora_name else ""
    print(f"    [IMG] {full_prompt[:70]}...{tag}")

    wf = _build_workflow(full_prompt, seed, width, height, lora_name, lora_strength)
    pid = _queue_prompt(wf)
    result = _wait_for_completion(pid)

    for node_output in result.get("outputs", {}).values():
        if "images" in node_output:
            img = node_output["images"][0]
            return _download_image(img["filename"], img.get("subfolder", ""), output_path)

    raise RuntimeError(f"No image output from ComfyUI for prompt {pid}")
