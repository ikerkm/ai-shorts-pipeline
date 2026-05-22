"""
YouTube Shorts uploader — OAuth2 con token persistente por cuenta.
Primera ejecución: abre el navegador para autenticar el canal.
Siguientes ejecuciones: usa el token guardado (sin intervención).
"""
import json
import time
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

_BASE = Path(__file__).parent.parent
TOKENS_DIR  = _BASE / "tokens"
CLIENT_SECRETS = _BASE / "client_secrets.json"
TOKENS_DIR.mkdir(exist_ok=True)


def _get_credentials(account_name: str) -> Credentials:
    token_path = TOKENS_DIR / f"youtube_{account_name}.json"
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRETS.exists():
                raise FileNotFoundError(
                    f"No se encuentra {CLIENT_SECRETS}\n"
                    "Descarga las credenciales OAuth2 desde Google Cloud Console "
                    "y guárdalas como Z:\\AI\\pipeline\\client_secrets.json"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS), SCOPES)
            print(f"\n  Abriendo navegador para autenticar '{account_name}' en YouTube...")
            print("  IMPORTANTE: cuando el navegador abra, haz clic en")
            print("  'Usar otra cuenta' y selecciona el BRAND ACCOUNT del canal")
            print("  (no tu cuenta personal de Google).\n")
            creds = flow.run_local_server(port=0, prompt="select_account consent")
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return creds


def get_channel_info(account_name: str) -> dict:
    """Devuelve título e ID del canal autenticado para esta cuenta."""
    creds = _get_credentials(account_name)
    youtube = build("youtube", "v3", credentials=creds)
    resp = youtube.channels().list(part="snippet", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        return {"title": "desconocido", "id": ""}
    return {"title": items[0]["snippet"]["title"], "id": items[0]["id"]}


def upload_video(
    account_name: str,
    video_path: Path,
    title: str,
    description: str = "",
    tags: list = None,
    category_id: str = "28",
    privacy: str = "public",
) -> str:
    """Sube un vídeo a YouTube Shorts. Devuelve la URL del vídeo."""
    creds = _get_credentials(account_name)
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": (tags or [])[:500],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=4 * 1024 * 1024)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    retries = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"  Subiendo... {pct}%", end="\r", flush=True)
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retries < 5:
                retries += 1
                time.sleep(2 ** retries)
            else:
                raise

    video_id = response["id"]
    url = f"https://www.youtube.com/shorts/{video_id}"
    print(f"  Subido: {url}          ")
    return url
