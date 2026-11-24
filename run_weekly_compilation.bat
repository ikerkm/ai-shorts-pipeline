@echo off
REM Compilatorio semanal (16:9) de ciencia_espacial — lanzado por la Tarea Programada del sábado.
REM La SUBIDA a YouTube es MANUAL (el archivo queda en output\ciencia_espacial\compilations\).
cd /d Z:\AI\pipeline
set PYTHONUTF8=1
"Z:\AI\ComfyUI\.venv\Scripts\python.exe" weekly_compilation.py --account ciencia_espacial >> logs\compilation.log 2>&1
