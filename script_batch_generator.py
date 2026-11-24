"""
Genera N guiones completos en batch para todas las cuentas.
- Cuentas regulares (Sonnet): guiones de contenido informativo/viral
- anuncios_absurdos (Opus): producto absurdo + guión de anuncio

Los guiones se guardan en scripts/{cuenta}/pending/ como JSONs listos para usar.
El pipeline los consume sin llamar a Claude durante la generación de vídeo.

Uso:
  python script_batch_generator.py --account ciencia_espacial --count 10
  python script_batch_generator.py --account anuncios_absurdos --count 10
  python script_batch_generator.py --account anuncios_absurdos --count 5 --style ad_luxury
  python script_batch_generator.py --all --count 10
"""
import json
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

import anthropic

sys.path.insert(0, str(Path(__file__).parent))
from config import ANTHROPIC_API_KEY, BASE_DIR, ACCOUNTS_DIR, load_account
from modules.product_generator import generate_product
from modules.script_generator import generate_script, generate_ad_script, generate_what_if_script
from modules.topic_store import add_topic as _ts_add, is_duplicate as _ts_is_dup
from modules.topic_store import migrate_from_list as _ts_migrate, count as _ts_count

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SCRIPTS_DIR = BASE_DIR / "scripts"
MIN_PENDING  = 3
TARGET_PENDING = 10


# ── Helpers ───────────────────────────────────────────────────────────────────

def count_pending(account_name: str, script_type: str = None) -> int:
    if script_type == "what_if":
        d = SCRIPTS_DIR / account_name / "what_if" / "pending"
    else:
        d = SCRIPTS_DIR / account_name / "pending"
    return len(list(d.glob("*.json"))) if d.exists() else 0


def _pending_dir(account_name: str, script_type: str = None) -> Path:
    if script_type == "what_if":
        d = SCRIPTS_DIR / account_name / "what_if" / "pending"
    else:
        d = SCRIPTS_DIR / account_name / "pending"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_used_topics(account_name: str) -> set:
    log_path = BASE_DIR / "logs" / f"{account_name}_topics.json"
    if not log_path.exists():
        return set()
    data = json.loads(log_path.read_text(encoding="utf-8"))
    return set(data.get("topics", []))


def _save_json(pending_dir: Path, i: int, topic: str, payload: dict,
               account_name: str = None) -> str:
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in topic[:25].replace(" ", "_"))
    fname = f"{ts}_{i:02d}_{safe}.json"
    (pending_dir / fname).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Track pending topic in ChromaDB so future batches don't generate duplicates
    if account_name:
        _ts_add(account_name, topic)
    return fname


# ── Generación de temas ───────────────────────────────────────────────────────

def _generate_topics_regular(profile: dict, n: int, used_topics: set) -> list[str]:
    account_name = profile["display_name"]
    style        = profile.get("default_style", "informativo")
    extra        = profile.get("system_prompt_extra", "")

    # Auto-migrate to ChromaDB on first use
    if _ts_count(account_name) == 0 and used_topics:
        added = _ts_migrate(account_name, list(used_topics))
        print(f"  [TopicStore] Migrados {added} topics a ChromaDB")

    used_str = ""
    if used_topics:
        used_str = "\n\nTemas ya usados (NO repetir ni el mismo concepto con distinta formulación):\n" + \
                   "\n".join(f"- {t}" for t in sorted(used_topics))

    # Sesgo data-driven hacia los arquetipos que más rinden (campo opcional del perfil).
    patterns_str = ""
    if profile.get("topic_patterns"):
        patterns_str = (
            "\n\nLO QUE MÁS FUNCIONA EN ESTE CANAL (sesga ~70% de los temas hacia estos arquetipos, "
            "deja el ~30% restante para explorar variedad):\n" + profile["topic_patterns"]
        )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": (
            f'Eres el editor de contenido de la cuenta de TikTok/Shorts "{account_name}" (estilo: {style}).\n'
            f"Contexto de la cuenta: {extra}\n\n"
            f"Genera exactamente {n * 2} temas frescos y virales para vídeos cortos de ~50 segundos.\n"
            f"Genera el doble de los necesarios para compensar posibles descartes por similitud.{patterns_str}{used_str}\n\n"
            f'Responde SOLO con JSON: {{"topics": ["tema 1", "tema 2", ...]}}\n'
            "Reglas:\n"
            "- Máx 60 caracteres por tema\n"
            "- Sin emojis ni símbolos especiales (@, #, *, &, %)\n"
            "- Usa español correcto con tildes y eñe — obligatorias\n"
            "- Cada tema debe poder generar un vídeo autónomo y completo"
        )}]
    )
    text = response.content[0].text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    candidates = json.loads(text)["topics"]

    result = []
    for t in candidates:
        if t in used_topics:
            continue
        is_dup, closest, sim = _ts_is_dup(account_name, t)
        if is_dup:
            print(f"  [TopicStore] Rechazado '{t[:50]}' (sim={sim:.2f} con '{closest[:50]}')")
            continue
        result.append(t)
        if len(result) == n:
            break
    return result


def _generate_topics_ads(n: int) -> list[str]:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": (
            f"Genera exactamente {n} ideas de productos absurdos e imposibles para anuncios TikTok/Shorts. "
            "Cada idea debe tener una contradicción inherente clara "
            "(como 'champú para quedarse calvo', 'jabón para ensuciar', 'aspiradora que esparce el polvo'). "
            f'Responde SOLO con JSON: {{"topics": ["idea 1", "idea 2", ...]}} '
            "Sin emojis. Máx 50 chars por idea. Español con tildes y ñ."
        )}]
    )
    text = response.content[0].text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)["topics"][:n]


# ── Generadores por tipo ──────────────────────────────────────────────────────

def _generate_batch_regular(account_name: str, profile: dict, count: int) -> int:
    """Cuentas informativas — Sonnet con system prompt cacheado."""
    pending_dir         = _pending_dir(account_name)
    num_scenes          = profile.get("default_scenes", 5)
    style               = profile.get("default_style", "informativo")
    system_prompt_extra = profile.get("system_prompt_extra", "")

    used   = _load_used_topics(account_name)
    topics = _generate_topics_regular(profile, count, used)
    print(f"  Temas: {len(topics)}")
    for i, t in enumerate(topics, 1):
        print(f"    {i}. {t}")

    generated = 0
    for i, topic in enumerate(topics, 1):
        print(f"\n[{i}/{len(topics)}] {topic}")
        try:
            t0     = time.time()
            script = generate_script(topic, style, num_scenes, system_prompt_extra)
            fname  = _save_json(pending_dir, i, topic, {
                "topic": topic, "account": account_name, "num_scenes": num_scenes,
                "script": script, "generated_at": datetime.now().isoformat(timespec="seconds"),
            }, account_name=account_name)
            print(f"  OK ({time.time()-t0:.1f}s) → {fname}")
            generated += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
        if i < len(topics):
            time.sleep(2)

    print(f"\n  {generated}/{count} guiones en {pending_dir}")
    return generated


def _generate_batch_ads(account_name: str, profile: dict, count: int, style_hint: str = None) -> int:
    """Cuenta anuncios_absurdos — Opus con system prompt cacheado."""
    pending_dir = _pending_dir(account_name)
    num_scenes  = profile.get("default_scenes", 5)

    topics = _generate_topics_ads(count)
    print(f"  Temas: {len(topics)}")
    for i, t in enumerate(topics, 1):
        print(f"    {i}. {t}")

    generated = 0
    for i, topic in enumerate(topics, 1):
        print(f"\n[{i}/{len(topics)}] {topic}")
        try:
            t0      = time.time()
            product = generate_product(topic, style_hint=style_hint)
            script  = generate_ad_script(product, num_scenes)
            fname   = _save_json(pending_dir, i, topic, {
                "topic": topic, "account": account_name, "num_scenes": num_scenes,
                "product": product, "script": script,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            })
            print(f"  OK ({time.time()-t0:.1f}s) → {fname}")
            generated += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
        if i < len(topics):
            time.sleep(2)

    print(f"\n  {generated}/{count} guiones en {pending_dir}")
    return generated


def _generate_topics_what_if(n: int, used_topics: set, account_name: str = "ciencia_espacial") -> list[str]:
    """Genera N hipótesis 'Y si...' variadas para ciencia_espacial."""
    collection_name = f"{account_name}_what_if"

    if _ts_count(collection_name) == 0 and used_topics:
        added = _ts_migrate(collection_name, list(used_topics))
        print(f"  [TopicStore] Migrados {added} hipótesis a ChromaDB")

    used_str = ""
    if used_topics:
        used_str = "\n\nHipótesis ya usadas (NO repetir ni el mismo concepto):\n" + \
                   "\n".join(f"- {t}" for t in sorted(used_topics))

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": (
            f"Genera exactamente {n * 2} hipótesis científicas del tipo 'Y si...' aplicadas a la Tierra "
            "para vídeos de divulgación científica en TikTok/Shorts. "
            "Genera el doble de las necesarias para compensar posibles descartes por similitud. "
            "Cubre variedad: condiciones de otros planetas, configuración del sistema solar, "
            "cambios en la Luna/Sol, eje terrestre, campo magnético, etc. "
            f"Cada hipótesis debe tener consecuencias concretas y visualizables.{used_str}\n\n"
            'Responde SOLO con JSON: {"topics": ["Y si ...", "Y si ...", ...]} '
            "Máx 70 chars por hipótesis. Sin emojis. Español con tildes y ñ."
        )}]
    )
    text = response.content[0].text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    candidates = json.loads(text)["topics"]

    result = []
    for t in candidates:
        if t in used_topics:
            continue
        is_dup, closest, sim = _ts_is_dup(collection_name, t)
        if is_dup:
            print(f"  [TopicStore] Rechazado '{t[:50]}' (sim={sim:.2f} con '{closest[:50]}')")
            continue
        result.append(t)
        if len(result) == n:
            break
    return result


def _generate_batch_what_if(account_name: str, profile: dict, count: int) -> int:
    """Guiones hipotéticos what_if para cuentas con what_if_ratio > 0."""
    pending_dir = _pending_dir(account_name, script_type="what_if")
    num_scenes  = profile.get("default_scenes", 6)

    used   = _load_used_topics(f"{account_name}_what_if")
    topics = _generate_topics_what_if(count, used, account_name=account_name)
    print(f"  Hipótesis: {len(topics)}")
    for i, t in enumerate(topics, 1):
        print(f"    {i}. {t}")

    generated = 0
    for i, topic in enumerate(topics, 1):
        print(f"\n[{i}/{len(topics)}] {topic}")
        try:
            t0     = time.time()
            script = generate_what_if_script(topic, num_scenes)
            fname  = _save_json(pending_dir, i, topic, {
                "topic": topic, "account": account_name, "script_type": "what_if",
                "num_scenes": num_scenes, "script": script,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            }, account_name=f"{account_name}_what_if")
            print(f"  OK ({time.time()-t0:.1f}s) → {fname}")
            generated += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
        if i < len(topics):
            time.sleep(2)

    print(f"\n  {generated}/{count} guiones what_if en {pending_dir}")
    return generated


# ── API pública ───────────────────────────────────────────────────────────────

def generate_batch(account_name: str, count: int = TARGET_PENDING,
                   style_hint: str = None, script_type: str = None) -> int:
    profile = load_account(account_name)
    label   = f"what_if" if script_type == "what_if" else "guiones"
    print(f"\n{'='*55}")
    print(f"  BATCH: {profile['display_name']}  ({count} {label})")
    print(f"{'='*55}")
    if script_type == "what_if":
        return _generate_batch_what_if(account_name, profile, count)
    elif profile.get("account_type") == "anuncios":
        return _generate_batch_ads(account_name, profile, count, style_hint)
    else:
        return _generate_batch_regular(account_name, profile, count)


def main():
    parser = argparse.ArgumentParser(description="Generador de guiones en batch con prompt caching")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--account", help="Nombre de la cuenta")
    group.add_argument("--all", action="store_true", help="Todas las cuentas")
    parser.add_argument("--count", type=int, default=TARGET_PENDING,
                        help=f"Guiones a generar por cuenta (default: {TARGET_PENDING})")
    parser.add_argument("--style", default=None,
                        choices=["ad_corporate", "ad_infomercial", "ad_luxury"],
                        help="Fuerza estilo (solo para anuncios_absurdos)")
    parser.add_argument("--type", default=None, choices=["what_if"],
                        help="Tipo de guión especial (what_if: hipótesis aplicadas a la Tierra)")
    args = parser.parse_args()

    if args.all:
        accounts = [p.stem for p in sorted(ACCOUNTS_DIR.glob("*.json"))]
        print(f"Procesando {len(accounts)} cuentas: {accounts}")
        for account in accounts:
            generate_batch(account, args.count, style_hint=args.style, script_type=args.type)
    else:
        generate_batch(args.account, args.count, style_hint=args.style, script_type=args.type)


if __name__ == "__main__":
    main()
