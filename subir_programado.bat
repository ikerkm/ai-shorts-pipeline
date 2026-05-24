@echo off
:: Uso: subir_programado.bat --account ciencia_espacial [--limit 1]
set PYTHONUTF8=1
"Z:\AI\ComfyUI\.venv\Scripts\python.exe" "Z:\AI\pipeline\upload_youtube.py" %*
