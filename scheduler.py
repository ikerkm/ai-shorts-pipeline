"""
Scheduler del pipeline de Shorts/TikToks.

Uso:
  python scheduler.py --account ciencia_espacial --videos 3
  python scheduler.py --account datos_curiosos --videos 5
  python scheduler.py --all --videos 2          # todas las cuentas
"""
import json
import sys
import time
import argparse
import hashlib
from pathlib import Path
from datetime import datetime, date

import anthropic

sys.path.insert(0, str(Path(__file__).parent))
from config import ANTHROPIC_API_KEY, ACCOUNTS_DIR, BASE_DIR, load_account
from pipeline import run

LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ── Log de temas ─────────────────────────────────────────────────────────────

def _log_path(account_name: str) -> Path:
    return LOGS_DIR / f"{account_name}_topics.json"


def load_used_topics(account_name: str) -> set:
    p = _log_path(account_name)
    if not p.exists():
        return set()
    data = json.loads(p.read_text(encoding="utf-8"))
    return set(data.get("topics", []))


def save_topic(account_name: str, topic: str):
    p = _log_path(account_name)
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"topics": [], "runs": []}
    if topic not in data["topics"]:
        data["topics"].append(topic)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_run(account_name: str, topic: str, video_path: str, duration_s: float):
    p = _log_path(account_name)
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"topics": [], "runs": []}
    data["runs"].append({
        "date": datetime.now().isoformat(timespec="seconds"),
        "topic": topic,
        "video": str(video_path),
        "duration_s": round(duration_s, 1),
    })
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Generación de temas ───────────────────────────────────────────────────────

def generate_topics(profile: dict, n: int, used_topics: set) -> list[str]:
    account_name = profile["display_name"]
    style = profile.get("default_style", "informativo")
    extra = profile.get("system_prompt_extra", "")

    used_str = ""
    if used_topics:
        sample = list(used_topics)[-30:]  # últimos 30 para no inflar el prompt
        used_str = "\n\nTemas ya usados (NO repetir ni temas similares):\n" + "\n".join(f"- {t}" for t in sample)

    prompt = f"""Eres el editor de contenido de la cuenta de TikTok/Shorts "{account_name}" (estilo: {style}).
Contexto de la cuenta: {extra}

Genera exactamente {n} temas frescos y virales para vídeos cortos de ~50 segundos.
Cada tema debe ser concreto, específico y diferente de los demás.{used_str}

Responde SOLO con JSON:
{{"topics": ["tema 1", "tema 2", ...]}}

Reglas:
- Máx 60 caracteres por tema
- Sin emojis ni símbolos especiales (@, #, *, &, %)
- Usa español correcto con tildes y eñe (á, é, í, ó, ú, ñ) — obligatorias
- Cada tema debe poder generar un vídeo autónomo y completo"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    topics = json.loads(text)["topics"]
    return [t for t in topics if t not in used_topics][:n]


# ── Runner principal ──────────────────────────────────────────────────────────

def run_account(account_name: str, n_videos: int):
    profile = load_account(account_name)
    used = load_used_topics(account_name)

    print(f"\n{'='*55}")
    print(f"  SCHEDULER: {profile['display_name']}")
    print(f"  Vídeos a generar: {n_videos}  |  Temas usados: {len(used)}")
    print(f"{'='*55}")

    print(f"\nGenerando {n_videos} temas con Claude...")
    topics = generate_topics(profile, n_videos, used)

    if not topics:
        print("  [!] No se generaron temas nuevos.")
        return

    print(f"  Temas seleccionados:")
    for i, t in enumerate(topics, 1):
        print(f"    {i}. {t}")

    for i, topic in enumerate(topics, 1):
        print(f"\n[{i}/{len(topics)}] '{topic}'")
        save_topic(account_name, topic)

        t0 = time.time()
        try:
            video_path = run(topic, profile=profile)
            elapsed = time.time() - t0
            save_run(account_name, topic, video_path, elapsed)
            print(f"  Completado en {elapsed/60:.1f} min → {video_path.name}")
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  [ERROR] {e}")
            save_run(account_name, topic, "ERROR", elapsed)

        if i < len(topics):
            print("  Pausa 5s antes del siguiente...")
            time.sleep(5)

    print(f"\n  Sesión completada para {profile['display_name']}")


def main():
    parser = argparse.ArgumentParser(description="Scheduler automático de Shorts/TikToks")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--account", help="Nombre de la cuenta")
    group.add_argument("--all", action="store_true", help="Todas las cuentas")
    parser.add_argument("--videos", type=int, default=3,
                        help="Vídeos a generar por cuenta (default: 3)")
    args = parser.parse_args()

    if args.all:
        accounts = [p.stem for p in sorted(ACCOUNTS_DIR.glob("*.json"))]
        print(f"Procesando {len(accounts)} cuentas: {accounts}")
        for account in accounts:
            run_account(account, args.videos)
    else:
        run_account(args.account, args.videos)


if __name__ == "__main__":
    main()
