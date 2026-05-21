"""
Registra/elimina tareas en Windows Task Scheduler para el pipeline.

Uso:
  python setup_tasks.py create           # crea tareas para todas las cuentas
  python setup_tasks.py create --account ciencia_espacial
  python setup_tasks.py list             # lista tareas creadas
  python setup_tasks.py delete           # elimina todas las tareas del pipeline
"""
import subprocess
import argparse
import sys
import ctypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import ACCOUNTS_DIR


def _require_admin():
    """Relanza el proceso con privilegios de administrador si es necesario."""
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        is_admin = False
    if not is_admin:
        print("Se necesitan permisos de administrador — solicitando UAC...")
        params = " ".join(f'"{a}"' for a in sys.argv)
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1
        )
        sys.exit(0)

BAT = r"Z:\AI\pipeline\run_scheduler.bat"
TASK_PREFIX = "Pipeline_Shorts"

# Horarios por defecto: mañana, tarde, noche  (hora, minuto)
DEFAULT_TIMES = ["08:00", "14:00", "20:00"]
VIDEOS_PER_RUN = 1  # 1 vídeo por ejecución × 3 horarios = 3 vídeos/día/cuenta


def task_name(account: str, time_slot: str) -> str:
    return f"{TASK_PREFIX}_{account}_{time_slot.replace(':', 'h')}"


def create_task(account: str, time_slot: str):
    name = task_name(account, time_slot)
    cmd = f'"{BAT}" --account {account} --videos {VIDEOS_PER_RUN}'
    result = subprocess.run([
        "schtasks", "/create",
        "/tn", name,
        "/tr", cmd,
        "/sc", "DAILY",
        "/st", time_slot,
        "/f",                    # sobrescribe si ya existe
        "/rl", "HIGHEST",        # máximos privilegios
    ], capture_output=True, text=True)

    if result.returncode == 0:
        print(f"  [OK] {name} → {time_slot}")
    else:
        print(f"  [ERR] {name}: {result.stderr.strip()}")


def delete_task(account: str, time_slot: str):
    name = task_name(account, time_slot)
    result = subprocess.run([
        "schtasks", "/delete", "/tn", name, "/f"
    ], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  [OK] Eliminada: {name}")
    else:
        print(f"  [--] No existía: {name}")


def list_tasks():
    result = subprocess.run([
        "schtasks", "/query", "/fo", "LIST", "/v"
    ], capture_output=True, text=True)
    lines = result.stdout.splitlines()
    found = []
    current = {}
    for line in lines:
        if line.startswith("TaskName:") and TASK_PREFIX in line:
            current = {"name": line.split(":", 1)[1].strip()}
        elif current and line.startswith("Next Run Time:"):
            current["next"] = line.split(":", 1)[1].strip()
        elif current and line.startswith("Status:"):
            current["status"] = line.split(":", 1)[1].strip()
            found.append(current)
            current = {}
    if found:
        print(f"\n{len(found)} tarea(s) del pipeline registradas:\n")
        for t in found:
            print(f"  {t['name']}")
            print(f"    Estado:  {t.get('status', '?')}")
            print(f"    Próxima: {t.get('next', '?')}")
    else:
        print("No hay tareas del pipeline registradas.")


def get_accounts(account_arg: str) -> list[str]:
    if account_arg:
        return [account_arg]
    return [p.stem for p in sorted(ACCOUNTS_DIR.glob("*.json"))]


def main():
    _require_admin()
    parser = argparse.ArgumentParser(description="Gestión de tareas programadas del pipeline")
    parser.add_argument("action", choices=["create", "delete", "list"])
    parser.add_argument("--account", default=None, help="Cuenta específica (todas si se omite)")
    parser.add_argument("--times", nargs="+", default=DEFAULT_TIMES,
                        help=f"Horarios HH:MM (default: {DEFAULT_TIMES})")
    args = parser.parse_args()

    if args.action == "list":
        list_tasks()
        return

    accounts = get_accounts(args.account)
    print(f"\nCuentas: {accounts}")
    print(f"Horarios: {args.times}")
    print(f"Vídeos/ejecución: {VIDEOS_PER_RUN}\n")

    for account in accounts:
        print(f"[{account}]")
        for t in args.times:
            if args.action == "create":
                create_task(account, t)
            elif args.action == "delete":
                delete_task(account, t)

    if args.action == "create":
        print(f"\nTotal: {len(accounts) * len(args.times)} tareas creadas")
        print(f"→ {len(accounts)} cuentas × {len(args.times)} ejecuciones/día = "
              f"{len(accounts) * len(args.times) * VIDEOS_PER_RUN} vídeos/día")
        print("\nVerifica con: python setup_tasks.py list")


if __name__ == "__main__":
    main()
