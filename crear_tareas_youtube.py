"""Crea las 6 tareas programadas de subida a YouTube en Windows Task Scheduler."""
import subprocess
import sys

BAT = r"Z:\AI\pipeline\subir_programado.bat"

TASKS = [
    ("Shorts_Upload_ciencia_20h",   "ciencia_espacial",  "20:00"),
    ("Shorts_Upload_ciencia_21h",   "ciencia_espacial",  "21:00"),
    ("Shorts_Upload_datos_18h",     "datos_curiosos",    "18:00"),
    ("Shorts_Upload_datos_19h",     "datos_curiosos",    "19:00"),
    ("Shorts_Upload_misterio_17h",  "misterio_historia", "17:00"),
    ("Shorts_Upload_misterio_22h",  "misterio_historia", "22:00"),
]

ok = 0
for name, account, time in TASKS:
    tr = f'"{BAT}" --account {account} --limit 1'
    result = subprocess.run(
        ["schtasks", "/create", "/tn", name, "/tr", tr, "/sc", "daily", "/st", time, "/f"],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    status = result.stdout.strip() or result.stderr.strip()
    print(f"  {name} ({time}): {status}")
    if result.returncode == 0:
        ok += 1

print(f"\n{ok}/{len(TASKS)} tareas creadas correctamente.")
if ok < len(TASKS):
    sys.exit(1)
