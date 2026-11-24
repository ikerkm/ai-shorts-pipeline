"""Adquisicion de imagen REAL de dominio publico (NASA Image Library) por escena.

Flujo (4 capas):
  1. stock_query (lo genera Claude por escena) -> busqueda en la API de NASA
  2. filtro heuristico: descarta ilustraciones/diagramas/renders por titulo
  3. verificacion visual con Claude Haiku: elige la candidata que de verdad
     ilustra la escena, o las rechaza (-> fallback a Flux)
  4. descarga + encaje a 1080x1920 (scale-to-cover, crop centrado)

Devuelve Path a la imagen lista, o None si no hay foto real adecuada
(el pipeline hace entonces fallback a Flux como hasta ahora).
"""
import json
import ssl
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

import config  # carga .env (ANTHROPIC_API_KEY) via load_dotenv
from config import FFMPEG, VIDEO_WIDTH, VIDEO_HEIGHT

_CTX = ssl.create_default_context()
_UA = {"User-Agent": "Mozilla/5.0 (pipeline stock_fetcher)"}

# Titulos que NO son fotografia real -> se descartan en el filtro heuristico
_SKIP_TITLE = (
    "illustration", "artist concept", "artist's concept", "artists concept",
    "diagram", "chart", "infographic", "graphic", "logo", "poster",
    "cartoon", "animation", "rendering", "render of", "schematic", "map of",
)


def _req(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers=_UA)


def _nasa_search(query: str, k: int = 8) -> list[dict]:
    """Devuelve hasta k items de la NASA Image Library para 'query'."""
    url = "https://images-api.nasa.gov/search?" + urllib.parse.urlencode(
        {"q": query, "media_type": "image"}
    )
    data = json.load(urllib.request.urlopen(_req(url), timeout=30, context=_CTX))
    return data.get("collection", {}).get("items", [])[:k]


def _preview_url(item: dict) -> str | None:
    """URL de la miniatura (para mostrar a Claude, ligera)."""
    for link in item.get("links", []):
        if link.get("render") == "image" or link.get("href", "").lower().endswith(
            (".jpg", ".jpeg", ".png")
        ):
            return link["href"]
    return None


def _full_image_url(nasa_id: str) -> str | None:
    """URL de un jpg grande (no thumb, no orig gigante) desde el manifiesto."""
    url = f"https://images-api.nasa.gov/asset/{urllib.parse.quote(nasa_id)}"
    try:
        data = json.load(urllib.request.urlopen(_req(url), timeout=30, context=_CTX))
    except Exception:
        return None
    hrefs = [
        i["href"] for i in data.get("collection", {}).get("items", [])
        if i.get("href", "").lower().endswith((".jpg", ".jpeg", ".png"))
    ]
    for key in ("~large", "~medium", "~orig"):
        for h in hrefs:
            if key in h:
                return h
    return hrefs[0] if hrefs else None


def _heuristic_keep(item: dict) -> bool:
    title = (item.get("data", [{}])[0].get("title", "") or "").lower()
    return not any(bad in title for bad in _SKIP_TITLE)


def _verify_with_claude(narration: str, candidates: list[dict]) -> int | None:
    """Claude Haiku elige la mejor candidata (1..N) o 0 si ninguna sirve.

    candidates: lista de dicts con 'preview' (url) y 'title'. Devuelve indice
    0-based en la lista, o None si rechaza todas / hay error.
    """
    try:
        from anthropic import Anthropic
    except Exception:
        return 0  # sin SDK -> usar la primera tras el filtro heuristico

    content = []
    for i, c in enumerate(candidates, 1):
        content.append({"type": "text", "text": f"Imagen {i} (titulo: {c['title'][:80]}):"})
        content.append({"type": "image", "source": {"type": "url", "url": c["preview"]}})
    content.append({
        "type": "text",
        "text": (
            "Eres editor de un canal de divulgacion espacial. La escena del video narra:\n"
            f"\"{narration}\"\n\n"
            "Elige la imagen que MEJOR ilustra esa escena como FOTOGRAFIA REAL del espacio "
            "(planetas, lunas, galaxias, nebulosas, superficies, misiones reales). "
            "CRITERIOS, en orden: (1) que sea foto real, no diagrama/grafico/ilustracion/logo; "
            "(2) sin una nave espacial en primer plano salvo que la escena trate de esa nave; "
            "(3) PREFIERE imagenes que LLENEN el encuadre (primer plano de superficie, nubes o "
            "nebulosa) frente a un objeto pequeno sobre fondo negro, porque el video es vertical "
            "a pantalla completa. "
            "Responde SOLO con el numero de la mejor imagen, o 0 si ninguna encaja bien."
        ),
    })

    try:
        client = Anthropic()
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=8,
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        num = int("".join(ch for ch in text if ch.isdigit()) or "0")
        if 1 <= num <= len(candidates):
            return num - 1
        return None  # 0 -> ninguna sirve
    except Exception as e:
        print(f"    [stock] verificacion Claude fallo ({e}); uso filtro heuristico")
        return 0


def _download_and_fit(img_url: str, out_path: Path) -> bool:
    """Descarga y encaja a 1080x1920 (scale-to-cover, crop centrado)."""
    tmp = out_path.with_suffix(".src")
    try:
        urllib.request.urlretrieve(img_url, tmp)  # noqa: S310 (url de NASA)
    except Exception:
        return False
    r = subprocess.run(
        [FFMPEG, "-y", "-i", str(tmp),
         "-vf", f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}",
         "-frames:v", "1", str(out_path)],
        capture_output=True, text=True,
    )
    tmp.unlink(missing_ok=True)
    return r.returncode == 0 and out_path.exists()


def fetch_stock_image(stock_query: str, narration: str, out_path: Path,
                      verify: bool = True, max_candidates: int = 3) -> Path | None:
    """Intenta conseguir una foto real de NASA para la escena.

    Devuelve out_path si lo logra, o None (-> el pipeline usa Flux).
    """
    if not stock_query:
        return None
    try:
        items = _nasa_search(stock_query)
    except Exception as e:
        print(f"    [stock] busqueda NASA fallo ({e})")
        return None

    # capa 2: filtro heuristico + necesita miniatura
    cands = []
    for it in items:
        if not _heuristic_keep(it):
            continue
        prev = _preview_url(it)
        data = it.get("data", [{}])[0]
        if prev and data.get("nasa_id"):
            cands.append({"preview": prev, "title": data.get("title", ""),
                          "nasa_id": data["nasa_id"]})
        if len(cands) >= max_candidates:
            break

    if not cands:
        print(f"    [stock] sin candidatas reales para '{stock_query}' -> Flux")
        return None

    # capa 3: verificacion visual
    idx = _verify_with_claude(narration, cands) if verify else 0
    if idx is None:
        print(f"    [stock] Claude rechazo todas para '{stock_query}' -> Flux")
        return None
    chosen = cands[idx]

    # capa 4: descarga full-res + encaje
    full = _full_image_url(chosen["nasa_id"]) or chosen["preview"]
    if _download_and_fit(full, out_path):
        print(f"    [stock] NASA OK: '{chosen['title'][:55]}'")
        return out_path
    print(f"    [stock] descarga/encaje fallo -> Flux")
    return None
