@echo off
chcp 65001 >nul
setlocal

set PYTHON=Z:\AI\ComfyUI\.venv\Scripts\python.exe
set SCRIPT=Z:\AI\pipeline\upload_youtube.py

echo Creando tareas programadas de subida a YouTube...
echo.

schtasks /create /tn "Shorts_Upload_ciencia_20h" /tr "cmd /c \"set PYTHONUTF8=1 && \"%PYTHON%\" \"%SCRIPT%\" --account ciencia_espacial --limit 1\"" /sc daily /st 20:00 /f
schtasks /create /tn "Shorts_Upload_ciencia_21h" /tr "cmd /c \"set PYTHONUTF8=1 && \"%PYTHON%\" \"%SCRIPT%\" --account ciencia_espacial --limit 1\"" /sc daily /st 21:00 /f
schtasks /create /tn "Shorts_Upload_datos_18h"   /tr "cmd /c \"set PYTHONUTF8=1 && \"%PYTHON%\" \"%SCRIPT%\" --account datos_curiosos --limit 1\"" /sc daily /st 18:00 /f
schtasks /create /tn "Shorts_Upload_datos_19h"   /tr "cmd /c \"set PYTHONUTF8=1 && \"%PYTHON%\" \"%SCRIPT%\" --account datos_curiosos --limit 1\"" /sc daily /st 19:00 /f
schtasks /create /tn "Shorts_Upload_misterio_17h" /tr "cmd /c \"set PYTHONUTF8=1 && \"%PYTHON%\" \"%SCRIPT%\" --account misterio_historia --limit 1\"" /sc daily /st 17:00 /f
schtasks /create /tn "Shorts_Upload_misterio_22h" /tr "cmd /c \"set PYTHONUTF8=1 && \"%PYTHON%\" \"%SCRIPT%\" --account misterio_historia --limit 1\"" /sc daily /st 22:00 /f

echo.
echo Verificando tareas creadas:
schtasks /query /tn "Shorts_Upload_ciencia_20h"   /fo list | findstr "Estado\|Proxima"
schtasks /query /tn "Shorts_Upload_ciencia_21h"   /fo list | findstr "Estado\|Proxima"
schtasks /query /tn "Shorts_Upload_datos_18h"     /fo list | findstr "Estado\|Proxima"
schtasks /query /tn "Shorts_Upload_datos_19h"     /fo list | findstr "Estado\|Proxima"
schtasks /query /tn "Shorts_Upload_misterio_17h"  /fo list | findstr "Estado\|Proxima"
schtasks /query /tn "Shorts_Upload_misterio_22h"  /fo list | findstr "Estado\|Proxima"

echo.
echo Listo.
