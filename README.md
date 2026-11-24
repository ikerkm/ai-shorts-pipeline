# AI Shorts Pipeline

Pipeline automatizado de generación de vídeos cortos (Shorts/TikToks) con IA local.

**Stack:** Claude API → Flux.1 Dev (imágenes) → Wan 2.2 I2V (vídeo) → Kokoro TTS → FFmpeg · ChromaDB + embeddings para los temas

> Proyecto personal.

## Qué hace

- **De un tema a un Short publicado:** guion JSON con la API de Claude, imágenes, clips de vídeo, voz, subtítulos, música y montaje, todo en local.
- **Temas sin repetir:** cada tema nuevo se compara por significado con los ya hechos, con embeddings multilingües (`paraphrase-multilingual-MiniLM-L12-v2`) en una base vectorial ChromaDB (`modules/topic_store.py`).
- **Fotos reales cuando existen:** la cuenta de espacio busca primero una foto de dominio público en la NASA Image Library y solo genera con Flux si no hay una adecuada (`modules/stock_fetcher.py`).
- **Retención:** gancho visual en el primer fotograma, subtítulos con la palabra activa resaltada y tarjeta de suscripción al final sin romper el bucle del Short.
- **Voz natural:** los números se pasan a palabras antes del TTS.
- **Publicación y métricas:** subida programada a YouTube declarando el contenido como sintético, registro de errores, snapshot horario de vistas y likes (`monitor_views.py`) y un compilatorio semanal en formato largo a partir de los vídeos de la semana (`weekly_compilation.py`).

## Requisitos de hardware

- GPU NVIDIA RTX con ≥16GB VRAM (probado en RTX 5080 / Blackwell sm_12.0)
- 32GB RAM
- ~100GB de espacio libre (modelos ~55GB + outputs)

## Requisitos de software

- Python 3.12
- Git
- FFmpeg (en PATH)
- NVIDIA drivers actualizados (CUDA 13.0+)

## Instalación desde cero

```powershell
# Clonar el pipeline
git clone https://github.com/ikerkm/ai-shorts-pipeline.git Z:\AI\pipeline

# Instalar todo (ComfyUI + modelos + dependencias)
cd Z:\AI\pipeline
.\install.ps1 -Drive Z -HfToken "hf_tu_token" -AnthropicKey "sk-ant-tu_clave"
```

El script tarda ~1-2h por la descarga de modelos (~55GB).

### Instalación sin descarga de modelos

```powershell
.\install.ps1 -Drive Z -SkipModels
```

Luego descarga los modelos manualmente según `models_manifest.json`.

## Uso

### Generar un vídeo

```bash
PYTHONUTF8=1 Z:\AI\ComfyUI\.venv\Scripts\python.exe pipeline.py "agujeros negros" --account ciencia_espacial
```

### Cuentas disponibles

| Cuenta | Temática | Voz |
|---|---|---|
| `ciencia_espacial` | Divulgación científica / espacio | em_alex |
| `misterio_historia` | Misterios e historia | em_alex |
| `datos_curiosos` | Datos curiosos / viral | em_alex |

### Arrancar ComfyUI

```
Z:\AI\ComfyUI\start_comfy.bat
# → http://localhost:8188
```

## Estructura del proyecto

```
pipeline/
├── pipeline.py              # Orquestador principal
├── config.py                # Configuración centralizada
├── scheduler.py             # Scheduler automático
├── script_batch_generator.py# Cola de guiones por adelantado
├── upload_youtube.py        # Subida de los vídeos pendientes
├── weekly_compilation.py    # Compilatorio semanal (formato largo)
├── monitor_views.py         # Snapshot horario de vistas y likes
├── music_generator.py       # Genera 15 tracks ambient
├── install.ps1              # Setup desde cero
├── models_manifest.json     # Lista de modelos + fuentes HuggingFace
├── requirements-pipeline.txt
├── .env.example             # Plantilla de credenciales
├── accounts/                # Perfiles por cuenta (JSON)
├── modules/
│   ├── script_generator.py  # Claude API → guión JSON
│   ├── topic_store.py       # Deduplicación semántica de temas (ChromaDB)
│   ├── stock_fetcher.py     # Fotos reales de la NASA (dominio público)
│   ├── image_generator.py   # ComfyUI Flux → imágenes
│   ├── video_generator.py   # ComfyUI Wan 2.2 → clips
│   ├── tts_generator.py     # Kokoro TTS → audio
│   ├── subtitle_generator.py# Subtítulos ASS
│   ├── video_assembler.py   # FFmpeg → MP4 final + tarjeta de suscripción
│   └── youtube_uploader.py  # YouTube Data API
└── comfyui_workflows/       # Workflows ComfyUI exportados (JSON)
```

## Configuración

Copia `.env.example` a `.env` y rellena:

```env
ANTHROPIC_API_KEY=sk-ant-...
COMFYUI_URL=http://localhost:8188
HF_TOKEN=hf_...
```

## Notas técnicas importantes

- **Orden de ejecución:** imágenes Flux PRIMERO → TTS Kokoro → `release_kokoro()` → Wan 2.2. Esto maximiza VRAM disponible para cada etapa.
- **NO usar `--highvram`** en ComfyUI con Wan 14B GGUF en RTX 5080 — causa OOM.
- **Siempre `PYTHONUTF8=1`** al ejecutar Python en Windows (caracteres españoles en guiones/subtítulos).
- **sageattention no compatible** con Windows (requiere triton, solo Linux).
- ComfyUI workflows en `comfyui_workflows/` — importar manualmente via UI tras instalar.
- Música se genera una vez con `music_generator.py` (15 tracks × 3 estilos).

## Pipeline detallado (v3.3)

```
Claude API (claude-sonnet-4-6)
  → Guión JSON: narración + image_prompt por escena + video_prompt específico
  ↓
Flux Dev Q8_0 GGUF (25 steps, cfg 3.5, scheduler beta)
  → Imágenes 1080×1920 (todas las escenas antes del TTS)
  ↓
Kokoro TTS em_alex → MP3 + word timings
  → release_kokoro() libera VRAM
  ↓
Wan 2.2 I2V (HighNoise/LowNoise Q6_K + Lightning LoRA 4 steps)
  → Clips con VAEDecodeTiled overlap=128 (anti-flickering)
  → -stream_loop -1 para clips con narración > 7.8s
  ↓
RTX Video Super Resolution ULTRA + RIFE VFI ×2
  → 480p → 1080p, 16fps → 32fps
  ↓
FFmpeg
  → Concat clips + audio + música ambient + subtítulos ASS → MP4 final
  → -movflags +faststart (compatible Windows Media Player)
```
