@echo off
title Pipeline Shorts - 2 videos x 4 cuentas = 8 videos
chcp 65001 >nul

echo.
echo ================================================
echo   PIPELINE SHORTS
echo   2 videos x 4 cuentas = 8 videos en total
echo   Tiempo estimado: 3-3.5 horas
echo.
echo   Orden: ciencia_espacial, misterio_historia,
echo          datos_curiosos, anuncios_absurdos
echo.
echo   NOTA anuncios_absurdos: si hay menos de 3
echo   guiones en cola, genera un batch de 10 antes
echo   de lanzar los videos (con prompt caching).
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
echo       Orden: ciencia_espacial, misterio_historia, datos_curiosos, anuncios_absurdos
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
echo   - anuncios_absurdos\
echo ================================================
echo.
if defined NO_SHUTDOWN (
    echo ================================================
    echo   Invocado desde run_all.bat — NO se apaga.
    echo   El apagado lo gestionara run_all al terminar.
    echo ================================================
) else (
    echo ================================================
    echo   Apagando el PC en 60 segundos...
    echo   Ejecuta "shutdown /a" para cancelar.
    echo ================================================
    shutdown /s /t 60
)
