@echo off
title Pipeline Shorts - 2 videos x 3 cuentas = 6 videos
chcp 65001 >nul

echo.
echo ================================================
echo   PIPELINE SHORTS
echo   2 videos x 3 cuentas = 6 videos en total
echo   Tiempo estimado: 2-2.5 horas
echo ================================================
echo.

:: ── Verificar si ComfyUI ya esta corriendo ──────────
echo [1/2] Verificando ComfyUI...
powershell -command "try { Invoke-WebRequest -Uri 'http://localhost:8188' -TimeoutSec 2 -UseBasicParsing >$null; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel%==0 (
    echo [OK] ComfyUI ya esta corriendo.
    goto RUN_SCHEDULER
)

:: ── Arrancar ComfyUI si no responde ─────────────────
echo [>>] Iniciando ComfyUI en nueva ventana...
start "ComfyUI - RTX 5080" cmd /c "Z:\AI\ComfyUI\start_comfy.bat"

echo     Esperando que carguen los modelos (puede tardar 2-3 min)...
:WAIT_LOOP
timeout /t 15 /nobreak >nul
powershell -command "try { Invoke-WebRequest -Uri 'http://localhost:8188' -TimeoutSec 3 -UseBasicParsing >$null; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel%==0 (
    echo [OK] ComfyUI listo.
    goto RUN_SCHEDULER
)
echo     Aun cargando...
goto WAIT_LOOP

:: ── Lanzar scheduler ─────────────────────────────────
:RUN_SCHEDULER
echo.
echo [2/2] Lanzando scheduler...
echo       Orden: ciencia_espacial → misterio_historia → datos_curiosos
echo.

set PYTHONUTF8=1
Z:\AI\ComfyUI\.venv\Scripts\python.exe Z:\AI\pipeline\scheduler.py --all --videos 2

echo.
echo ================================================
echo   PROCESO COMPLETADO
echo   Videos en: Z:\AI\pipeline\output\
echo   - ciencia_espacial\
echo   - misterio_historia\
echo   - datos_curiosos\
echo ================================================
echo.
pause
