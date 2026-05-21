# install.ps1 — Setup completo del ecosistema AI desde cero
# Requisitos previos: Python 3.12, Git, NVIDIA drivers, FFmpeg en PATH
# Uso: .\install.ps1 -Drive Z -HfToken "hf_..." -AnthropicKey "sk-ant-..."
#
# IMPORTANTE: No usar --highvram con Wan 14B GGUF en RTX 5080 (causa OOM)

param(
    [string]$Drive = "Z",
    [string]$HfToken = "",
    [string]$AnthropicKey = "",
    [switch]$SkipModels = $false,
    [switch]$SkipComfyUI = $false
)

$ErrorActionPreference = "Stop"
$AIRoot = "${Drive}:\AI"
$ComfyRoot = "$AIRoot\ComfyUI"
$PipelineRoot = "$AIRoot\pipeline"
$Venv = "$ComfyRoot\.venv"
$Pip = "$Venv\Scripts\pip.exe"
$Python = "$Venv\Scripts\python.exe"

Write-Host "=== Setup Ecosistema AI ===" -ForegroundColor Cyan
Write-Host "Raiz: $AIRoot"

# 1. Crear estructura de directorios
Write-Host "`n[1/7] Creando estructura..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $AIRoot | Out-Null
New-Item -ItemType Directory -Force -Path "$AIRoot\pipeline\output" | Out-Null
New-Item -ItemType Directory -Force -Path "$AIRoot\pipeline\temp" | Out-Null
New-Item -ItemType Directory -Force -Path "$AIRoot\pipeline\logs" | Out-Null
New-Item -ItemType Directory -Force -Path "$AIRoot\pipeline\music" | Out-Null

# 2. Instalar/actualizar ComfyUI
if (-not $SkipComfyUI) {
    Write-Host "`n[2/7] Instalando ComfyUI..." -ForegroundColor Yellow
    Set-Location $AIRoot
    if (Test-Path $ComfyRoot) {
        Write-Host "  ComfyUI ya existe, actualizando..."
        Set-Location $ComfyRoot
        git pull
    } else {
        git clone https://github.com/comfyanonymous/ComfyUI.git $ComfyRoot
        Set-Location $ComfyRoot
    }

    # Crear venv con Python 3.12
    if (-not (Test-Path "$Venv\Scripts\python.exe")) {
        Write-Host "  Creando venv Python 3.12..."
        python -m venv $Venv
    }

    # Instalar PyTorch cu130 (RTX 5080 / Blackwell)
    Write-Host "  Instalando PyTorch 2.12.0+cu130..."
    & $Pip install torch==2.12.0+cu130 torchvision==0.22.0+cu130 torchaudio==2.12.0+cu130 `
        --index-url https://download.pytorch.org/whl/cu130

    # Instalar dependencias de ComfyUI
    Write-Host "  Instalando dependencias ComfyUI..."
    & $Pip install -r "$ComfyRoot\requirements.txt"

    # Instalar custom nodes
    Write-Host "`n[3/7] Instalando custom nodes..." -ForegroundColor Yellow
    $CustomNodes = "$ComfyRoot\custom_nodes"
    New-Item -ItemType Directory -Force -Path $CustomNodes | Out-Null

    $Nodes = @(
        @{ name="ComfyUI-GGUF";                url="https://github.com/city96/ComfyUI-GGUF" },
        @{ name="ComfyUI-TeaCache";             url="https://github.com/welltop-cn/ComfyUI-TeaCache" },
        @{ name="ComfyUI-VideoHelperSuite";     url="https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite" },
        @{ name="ComfyUI-Frame-Interpolation";  url="https://github.com/Fannovel16/ComfyUI-Frame-Interpolation" },
        @{ name="RTXVideoSuperResolution";      url="https://github.com/Limitless-Flow/RTXVideoSuperResolution" }
    )

    foreach ($node in $Nodes) {
        $nodePath = "$CustomNodes\$($node.name)"
        if (Test-Path $nodePath) {
            Write-Host "  $($node.name) ya instalado, actualizando..."
            Set-Location $nodePath; git pull
        } else {
            Write-Host "  Clonando $($node.name)..."
            git clone $node.url $nodePath
        }
        # Instalar requirements del nodo si existen
        if (Test-Path "$nodePath\requirements.txt") {
            & $Pip install -r "$nodePath\requirements.txt"
        }
    }

    # Extras requeridos por ComfyUI-GGUF con T5/Wan
    & $Pip install sentencepiece protobuf

    # Crear start_comfy.bat
    $startBat = "@echo off`nset PYTHONUTF8=1`n`"$Python`" `"$ComfyRoot\main.py`" --fp8_e4m3fn-unet --preview-method auto`npause"
    Set-Content -Path "$ComfyRoot\start_comfy.bat" -Value $startBat -Encoding UTF8
    Write-Host "  Creado: $ComfyRoot\start_comfy.bat"
}

# 4. Instalar dependencias del pipeline
Write-Host "`n[4/7] Instalando dependencias del pipeline..." -ForegroundColor Yellow
& $Pip install -r "$PipelineRoot\requirements-pipeline.txt"

# 5. Configurar HuggingFace
if ($HfToken -ne "") {
    Write-Host "`n[5/7] Configurando HuggingFace token..." -ForegroundColor Yellow
    $env:PYTHONUTF8 = "1"
    & $Python -c "from huggingface_hub import login; login(token='$HfToken')"
} else {
    Write-Host "`n[5/7] Saltando HuggingFace (sin token proporcionado)" -ForegroundColor DarkYellow
}

# 6. Descargar modelos
if (-not $SkipModels -and $HfToken -ne "") {
    Write-Host "`n[6/7] Descargando modelos (~55GB, puede tardar 1-2h)..." -ForegroundColor Yellow

    $manifest = Get-Content "$PipelineRoot\models_manifest.json" | ConvertFrom-Json

    foreach ($model in $manifest.models) {
        $destDir = "$ComfyRoot\$($model.dest)"
        $destFile = "$destDir\$($model.name)"
        New-Item -ItemType Directory -Force -Path $destDir | Out-Null

        if (Test-Path $destFile) {
            Write-Host "  [ya existe] $($model.name)" -ForegroundColor DarkGreen
            continue
        }

        Write-Host "  Descargando $($model.name) ($($model.size_gb)GB)..."
        $env:PYTHONUTF8 = "1"
        & $Python -c @"
from huggingface_hub import hf_hub_download
import shutil, os
path = hf_hub_download(
    repo_id='$($model.hf_repo)',
    filename='$($model.hf_filename)',
    token='$HfToken' if '$($model.requires_hf_token)' == 'True' else None
)
shutil.copy(path, r'$destFile')
print(f'  -> Guardado en $destFile')
"@
    }
} else {
    Write-Host "`n[6/7] Saltando descarga de modelos (usar -SkipModels o proporcionar -HfToken)" -ForegroundColor DarkYellow
    Write-Host "  Ver models_manifest.json para la lista completa de modelos a descargar"
}

# 7. Crear .env
Write-Host "`n[7/7] Configurando .env..." -ForegroundColor Yellow
$envFile = "$PipelineRoot\.env"
if (-not (Test-Path $envFile)) {
    $envContent = "ANTHROPIC_API_KEY=$AnthropicKey`nCOMFYUI_URL=http://localhost:8188`nHF_TOKEN=$HfToken"
    Set-Content -Path $envFile -Value $envContent -Encoding UTF8
    Write-Host "  Creado .env — recuerda rellenar las claves API"
} else {
    Write-Host "  .env ya existe, no sobreescrito"
}

Write-Host "`n=== Setup completado ===" -ForegroundColor Green
Write-Host "Proximos pasos:"
Write-Host "  1. Arrancar ComfyUI: $ComfyRoot\start_comfy.bat"
Write-Host "  2. Instalar rife49.pth desde la UI de ComfyUI (ComfyUI-Frame-Interpolation)"
Write-Host "  3. Generar música: PYTHONUTF8=1 `"$Python`" `"$PipelineRoot\music_generator.py`""
Write-Host "  4. Generar vídeo:  PYTHONUTF8=1 `"$Python`" `"$PipelineRoot\pipeline.py`" `"tema`" --account ciencia_espacial"
