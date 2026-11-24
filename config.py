import os
import json
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / '.env')

ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
COMFYUI_URL = os.getenv('COMFYUI_URL', 'http://localhost:8188')

OUTPUT_DIR = BASE_DIR / 'output'
TEMP_DIR = BASE_DIR / 'temp'
ACCOUNTS_DIR = BASE_DIR / 'accounts'
MUSIC_DIR = BASE_DIR / 'music'
ASSETS_DIR = BASE_DIR / 'assets'
OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)


def load_account(name: str) -> dict:
    path = ACCOUNTS_DIR / f"{name}.json"
    if not path.exists():
        available = [p.stem for p in ACCOUNTS_DIR.glob("*.json")]
        raise FileNotFoundError(
            f"Cuenta '{name}' no encontrada. Disponibles: {available}"
        )
    return json.loads(path.read_text(encoding="utf-8"))

FFMPEG = r"C:\Users\ikerk\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"
FFPROBE = r"C:\Users\ikerk\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffprobe.exe"

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 32  # RIFE ×2 desde los 16fps de Wan

# Duración del HOOK card (gancho visual del frame 1, ms). Calibrar con la curva
# de retención: subir si la gente aún se va tras desaparecer; bajar si tapa el vídeo.
HOOK_OVERLAY_DUR_MS = 2200

TTS_VOICE = 'es-ES-AlvaroNeural'
TTS_RATE = '+0%'

FLUX_MODEL = 'flux1-dev-Q8_0.gguf'      # UnetLoaderGGUF
FLUX_CLIP1 = 'clip_l.safetensors'        # DualCLIPLoaderGGUF
FLUX_CLIP2 = 't5xxl_fp8_e4m3fn.safetensors'
FLUX_VAE   = 'ae.safetensors'
FLUX_STEPS = 25
FLUX_CFG   = 3.5                         # FluxGuidance
IMAGE_STYLE_SUFFIX = ", photorealistic cinematic photography, natural balanced exposure, good contrast, film grain, shallow depth of field, 9:16 vertical portrait format, no text, no watermark, no logo, not overexposed, not blown out, not illustrated, not cartoon, not flat design"

# Wan 2.2 I2V — Lightning LoRA 4 steps (2-stage KSamplerAdvanced)
WAN_UNET_HIGH   = "Wan2.2-I2V-A14B-HighNoise-Q6_K.gguf"
WAN_UNET_LOW    = "Wan2.2-I2V-A14B-LowNoise-Q6_K.gguf"
WAN_CLIP        = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
WAN_VAE         = "wan_2.1_vae.safetensors"
WAN_LORA_HIGH   = "Wan2.2-Lightning_I2V-A14B-4steps-lora_HIGH_fp16.safetensors"
WAN_LORA_LOW    = "Wan2.2-Lightning_I2V-A14B-4steps-lora_LOW_fp16.safetensors"
WAN_FPS         = 16
WAN_WIDTH       = 480
WAN_HEIGHT      = 832
WAN_CLIP_FRAMES = 125  # 7.8s @ 16fps (Lightning 4-step max)

COMFYUI_OUTPUT_DIR = Path(r"Z:\AI\ComfyUI\output")
COMFYUI_INPUT_DIR  = Path(r"Z:\AI\ComfyUI\input")

# Presets de color grading por género (filtros FFmpeg aplicados antes de quemar subtítulos)
COLOR_PRESETS = {
    "space":   "eq=saturation=0.92:contrast=1.08,colorbalance=bs=0.05:bm=0.03:bh=0.02",
    "upbeat":  "eq=saturation=1.12:contrast=1.05,colorbalance=rs=0.04:rm=0.02:rh=0.01",
    "mystery": "eq=saturation=0.78:brightness=-0.03:contrast=1.10",
    "none":    "",
}
