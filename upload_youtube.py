"""
Sube vídeos pendientes a YouTube Shorts.

Uso:
  # Sube todos los vídeos pendientes de una cuenta
  python upload_youtube.py --account ciencia_espacial

  # Sube todos los vídeos pendientes de todas las cuentas
  python upload_youtube.py --all

  # Sube un vídeo concreto con tema manual
  python upload_youtube.py --account ciencia_espacial --file output/ciencia_espacial/video.mp4 --topic "El agujero negro más grande"

  # Solo autenticar (sin subir) — útil para hacer el OAuth la primera vez
  python upload_youtube.py --account ciencia_espacial --auth-only
"""
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from config import ACCOUNTS_DIR, BASE_DIR, load_account
from modules.youtube_uploader import upload_video, _get_credentials, get_channel_info

LOGS_DIR = BASE_DIR / "logs"


def _log_path(account_name: str) -> Path:
    return LOGS_DIR / f"{account_name}_topics.json"


def _load_log(account_name: str) -> dict:
    p = _log_path(account_name)
    if not p.exists():
        return {"topics": [], "runs": []}
    return json.loads(p.read_text(encoding="utf-8"))


def _save_log(account_name: str, data: dict):
    _log_path(account_name).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _build_metadata(profile: dict, topic: str, dynamic_tags: list = None) -> dict:
    tags_base   = profile.get("youtube_tags", [])
    category_id = profile.get("youtube_category_id", "28")
    desc_suffix = profile.get("youtube_description_suffix", "")

    # Mezclar: dinámicos primero (más relevantes), luego base, sin duplicados
    combined = list(dict.fromkeys((dynamic_tags or []) + tags_base))

    title = f"{topic} #Shorts"
    hashtags = " ".join(f"#{t.replace(' ', '')}" for t in combined)
    description = f"{topic}\n\n{desc_suffix}\n\n{hashtags} #Shorts".strip()

    return {
        "title": title,
        "description": description,
        "tags": combined + ["Shorts", "shorts"],
        "category_id": category_id,
    }


def upload_pending(account_name: str, limit: int = None):
    profile = load_account(account_name)
    data    = _load_log(account_name)
    runs    = data.get("runs", [])

    pending = [r for r in runs if r.get("video") not in ("", "ERROR") and not r.get("youtube_url")]

    # Filtrar archivos que ya no existen en disco (generados antes de integrar upload)
    pending = [r for r in pending if Path(r["video"]).exists()]

    if not pending:
        print(f"  [{account_name}] No hay vídeos pendientes de subir.")
        return

    if limit is not None:
        pending = pending[:limit]

    print(f"\n{'='*55}")
    print(f"  YOUTUBE UPLOAD: {profile['display_name']}")
    print(f"  Subiendo: {len(pending)} vídeo(s)")
    print(f"{'='*55}")

    for run in pending:
        video_path = Path(run["video"])
        topic       = run.get("topic", video_path.stem)
        dynamic_tags = run.get("tags", [])

        print(f"\n  Subiendo: {topic}")
        meta = _build_metadata(profile, topic, dynamic_tags=dynamic_tags)

        try:
            url = upload_video(
                account_name=account_name,
                video_path=video_path,
                title=meta["title"],
                description=meta["description"],
                tags=meta["tags"],
                category_id=meta["category_id"],
            )
            run["youtube_url"] = url
            run["youtube_date"] = datetime.now().isoformat(timespec="seconds")

            # Mover a subcarpeta "subidos"
            subidos_dir = video_path.parent / "subidos"
            subidos_dir.mkdir(exist_ok=True)
            dest = subidos_dir / video_path.name
            video_path.rename(dest)
            run["video"] = str(dest)
            print(f"  Movido a: subidos/{video_path.name}")

            _save_log(account_name, data)
        except Exception as e:
            print(f"  [ERROR] {e}")


def upload_single(account_name: str, file_path: Path, topic: str):
    profile = load_account(account_name)
    meta    = _build_metadata(profile, topic)

    print(f"\n  Subiendo: {topic}")
    url = upload_video(
        account_name=account_name,
        video_path=file_path,
        title=meta["title"],
        description=meta["description"],
        tags=meta["tags"],
        category_id=meta["category_id"],
    )

    # Registrar en el log si existe entrada para este vídeo
    data = _load_log(account_name)
    for run in data.get("runs", []):
        if Path(run.get("video", "")) == file_path:
            run["youtube_url"]  = url
            run["youtube_date"] = datetime.now().isoformat(timespec="seconds")
            _save_log(account_name, data)
            break


def main():
    parser = argparse.ArgumentParser(description="Sube vídeos a YouTube Shorts")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--account", help="Nombre de la cuenta")
    group.add_argument("--all", action="store_true", help="Todas las cuentas")

    parser.add_argument("--file",  help="Ruta al vídeo (upload manual)")
    parser.add_argument("--topic", help="Tema del vídeo (requerido con --file)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Máximo de vídeos a subir por ejecución (default: todos)")
    parser.add_argument("--auth-only", action="store_true",
                        help="Solo autenticar, no subir")
    args = parser.parse_args()

    if args.all:
        accounts = [p.stem for p in sorted(ACCOUNTS_DIR.glob("*.json"))]
        for account in accounts:
            if args.auth_only:
                print(f"\nAutenticando {account}...")
                _get_credentials(account)
                info = get_channel_info(account)
                print(f"  Token guardado para {account}")
                print(f"  Canal autenticado: {info['title']} (id: {info['id']})")
            else:
                upload_pending(account, limit=args.limit)
        return

    account_name = args.account

    if args.auth_only:
        print(f"\nAutenticando {account_name}...")
        _get_credentials(account_name)
        info = get_channel_info(account_name)
        print(f"  Token guardado para {account_name}")
        print(f"  Canal autenticado: {info['title']} (id: {info['id']})")
        return

    if args.file:
        if not args.topic:
            parser.error("--file requiere --topic")
        upload_single(account_name, Path(args.file), args.topic)
    else:
        upload_pending(account_name, limit=args.limit)


if __name__ == "__main__":
    main()
