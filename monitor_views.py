"""
Snapshot horario de views/likes de los últimos vídeos de cada cuenta.
Acumula en logs/view_snapshots.jsonl — una línea por vídeo y ejecución.
Permite reconstruir la curva de arranque (views a 3h/24h/48h) de cada vídeo.

Uso:  python monitor_views.py            (pensado para tarea programada horaria)
      python monitor_views.py --report   (tabla de views por edad de cada vídeo)

Coste API: 1 unidad por cuenta y ejecución (videos.list) — irrelevante para la quota.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

BASE = Path(__file__).parent
LOGS = BASE / "logs"
SNAPSHOTS = LOGS / "view_snapshots.jsonl"
ACCOUNTS = ["ciencia_espacial", "datos_curiosos", "misterio_historia"]
N_RECENT = 15  # últimos N vídeos por cuenta


def _video_id(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def take_snapshot():
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for account in ACCOUNTS:
        token = BASE / "tokens" / f"youtube_{account}.json"
        log = LOGS / f"{account}_topics.json"
        if not token.exists() or not log.exists():
            continue
        try:
            d = json.load(open(log, encoding="utf-8"))
            runs = d if isinstance(d, list) else d.get("runs", d)
            recent = [r for r in runs if r.get("youtube_url")][-N_RECENT:]
            ids = [_video_id(r["youtube_url"]) for r in recent]
            if not ids:
                continue
            creds = Credentials.from_authorized_user_file(str(token))
            yt = build("youtube", "v3", credentials=creds)
            resp = yt.videos().list(part="statistics,snippet", id=",".join(ids)).execute()
            for it in resp.get("items", []):
                s = it["statistics"]
                rows.append({
                    "ts": now,
                    "account": account,
                    "video_id": it["id"],
                    "published_at": it["snippet"]["publishedAt"],
                    "title": it["snippet"]["title"],
                    "views": int(s.get("viewCount", 0)),
                    "likes": int(s.get("likeCount", 0)),
                    "comments": int(s.get("commentCount", 0)),
                })
        except Exception as e:
            print(f"[{account}] ERROR: {e}", file=sys.stderr)
    if rows:
        with open(SNAPSHOTS, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{now} snapshot: {len(rows)} videos")


def report():
    """Views de cada vídeo en hitos de edad (3h, 6h, 12h, 24h, 48h, ahora)."""
    if not SNAPSHOTS.exists():
        print("Sin snapshots todavía.")
        return
    snaps = {}
    for line in open(SNAPSHOTS, encoding="utf-8"):
        r = json.loads(line)
        snaps.setdefault(r["video_id"], []).append(r)

    milestones = [3, 6, 12, 24, 48]
    for vid, rows in snaps.items():
        rows.sort(key=lambda r: r["ts"])
        last = rows[-1]
        pub = datetime.fromisoformat(last["published_at"].replace("Z", "+00:00"))
        cells = []
        for m in milestones:
            best = None
            for r in rows:
                age = (datetime.fromisoformat(r["ts"]) - pub).total_seconds() / 3600
                if age <= m:
                    best = r["views"]
            cells.append(f"{best:>6}" if best is not None else "     -")
        age_now = (datetime.fromisoformat(last["ts"]) - pub).total_seconds() / 3600
        print(f"{last['account'][:8]} | {pub.isoformat()[:16]} | "
              + " ".join(cells)
              + f" | now({age_now:.0f}h)={last['views']:>6} | {last['title'][:40]}")


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        take_snapshot()
