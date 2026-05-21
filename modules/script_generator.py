import json
import anthropic
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))
from config import ANTHROPIC_API_KEY

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """Eres un guionista experto en contenido viral para TikTok y YouTube Shorts en español.
Tu especialidad es transformar cualquier tema en un vídeo de 50 segundos que engancha desde el primer segundo y se comparte solo.

REGLA ABSOLUTA — ORTOGRAFÍA ESPAÑOLA:
Todo texto en español debe tener tildes y eñe correctas. Sin excepción.
CORRECTO: también, físicos, años, canción, corazón, después, más, qué, cómo, quién, así, fácil, energía, único, vergüenza, pingüino, cigüeña, agüero
INCORRECTO: tambien, fisicos, anos, cancion, corazon, despues, mas, que, como, quien, asi, facil, energia, unico, verguenza, pinguino, ciguena, aguero
Si omites una tilde, una ñ o una ü, el resultado es inaceptable.

PRINCIPIOS DE GUIÓN VIRAL:
- El hook (escena 1) debe generar una pregunta implícita en la mente del espectador que solo se resuelve viendo el resto
- Cada escena debe terminar con el espectador queriendo saber qué viene después
- Los datos concretos (números, fechas, nombres, lugares) siempre superan a las afirmaciones vagas
- Frases cortas. Ritmo rápido. Presente continuo. Máx 20 palabras por frase.
- Nunca uses "increíble", "fascinante" o "interesante" — demuéstralo con el dato, no lo etiquetes

Respondes ÚNICAMENTE con JSON válido, sin markdown ni explicaciones."""

def generate_script(topic: str, style: str = "informativo", num_scenes: int = 5,
                    system_prompt_extra: str = "") -> dict:
    system = SYSTEM_PROMPT
    if system_prompt_extra:
        system += f"\n\nContexto de cuenta: {system_prompt_extra}"

    prompt = f"""Crea un guión para un vídeo corto de TikTok/Shorts sobre: "{topic}"
Estilo: {style}
Número de escenas: {num_scenes}

Devuelve exactamente este JSON:
{{
  "title": "título atractivo del vídeo (máx 60 chars)",
  "hook": "frase de gancho MUY impactante para la primera escena (máx 12 palabras)",
  "scenes": [
    {{
      "id": 1,
      "narration": "texto que se narrará, natural y conversacional (máx 20 palabras)",
      "image_prompt": "vivid cinematic scene in English — MANDATORY: derive the visual subject DIRECTLY from the narration text of this scene (identify who/what/where/when is being described and translate it into a concrete visual scene) + [natural balanced lighting: soft overcast daylight / golden hour side light / cool blue twilight / dim studio with shadows — properly exposed with visible detail in both highlights and shadows, NOT blown out or overexposed] + [camera angle: aerial view / extreme close-up / wide establishing shot / medium shot] + [atmosphere and colors: rich saturated colors, good contrast, cinematic tones]. If people: show clear face and natural proportions. NO silhouettes as main subject. NO generic topic-level scenes — the image must illustrate THIS specific narration sentence.",
      "image_negative": "blurry, low quality, text, watermark, logo, distorted, deformed, bad anatomy, extra limbs, malformed hands, fused fingers, cloned faces, amateur, overexposed, blown out, washed out, too bright, white haze, burnt highlights, murky, muddy colors, silhouette, black background, noise, pixelated, oversaturated",
      "video_prompt": "motion description in English for a 5s animated clip — MANDATORY: identify the main subject of this scene's image and describe what specific element moves (examples: ruins → 'dust particles slowly drifting through crumbling archway, gentle camera push-in'; soldiers → 'distant soldiers marching slowly, gradual zoom-out'; space → 'nebula clouds slowly expanding, stars drifting, subtle zoom-out'; person → 'hair gently moving in wind, slow push-in on face'). Always combine: specific subject motion + camera motion (slow zoom-in / gentle push-in / smooth pan / slow zoom-out). CRITICAL: use ONLY slow, smooth, gentle movements — NEVER 'intensifying', 'exploding', 'expanding rapidly', 'dramatic burst'. Always end with: 'consistent stable lighting, no light variation'. One sentence, cinematic and calm."
    }}
  ],
  "outro": "llamada a la acción final (máx 10 palabras, ej: Sígueme para más)"
}}

Reglas críticas:
- Narración total: máx 120 palabras en total para que el vídeo dure ~50 segundos
- La escena 1 usa el hook como narración
- image_prompt siempre en inglés, muy descriptivo y visual, SIEMPRE bien iluminado
- image_prompt debe representar visualmente EXACTAMENTE lo que se narra en esa escena: el sujeto, la acción, el lugar y la época descritos en la narración. NO uses sujetos genéricos del tema; traduce la narración a descripción visual concreta. EJEMPLO CORRECTO: narración "El Imperio Romano cayó en el 476 d.C." → image_prompt "Odoacro deposes Romulus Augustulus in crumbling Roman throne room, barbarian soldiers, golden hour twilight, wide shot". EJEMPLO INCORRECTO: "Roman colosseum at sunset" (genérico del tema, no de la narración)
- video_prompt: describe solo el movimiento cinematico, NUNCA la descripción estática
- video_prompt debe ser coherente con el tipo de escena (espacio: zoom-out lento + nebulosa pulsando; naturaleza: pan suave + hojas cayendo; personas: push-in lento + luz cambiando)
- Estilo narrativo: directo, impactante, presente continuo
- NO uses emojis ni símbolos especiales (@, #, *, &, %, ^, ~, |, <, >) en ningún campo
- Usa español correcto con tildes y eñe (á, é, í, ó, ú, ñ, ü, Á, É, Í, Ó, Ú, Ñ) — son obligatorias"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    script = json.loads(text)
    script = _fix_ortografia(script)

    # Inject outro into last scene
    last = script["scenes"][-1]
    last["narration"] = last["narration"] + " " + script["outro"]

    return script


def _fix_ortografia(script: dict) -> dict:
    """Corrección automática de ortografía en todos los campos de texto en español."""
    fields = {"title": script.get("title", ""), "hook": script.get("hook", ""),
              "outro": script.get("outro", "")}
    for i, s in enumerate(script.get("scenes", [])):
        fields[f"narration_{i}"] = s.get("narration", "")

    texts_json = json.dumps(fields, ensure_ascii=False)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        messages=[{"role": "user", "content": (
            "Corrige ÚNICAMENTE los errores ortográficos (tildes, ñ, ü) del siguiente JSON en español. "
            "No cambies palabras, orden, ni significado. Solo añade tildes que falten, corrige ñ y ü (vergüenza, pingüino, etc.). "
            "Devuelve SOLO el JSON corregido, sin explicaciones ni markdown.\n\n" + texts_json
        )}]
    )

    fixed_text = response.content[0].text.strip()
    if "```" in fixed_text:
        fixed_text = fixed_text.split("```")[1]
        if fixed_text.startswith("json"):
            fixed_text = fixed_text[4:]
        fixed_text = fixed_text.strip()

    try:
        fixed = json.loads(fixed_text)
    except Exception:
        return script  # si falla el fix, devolver original

    script["title"] = fixed.get("title", script["title"])
    script["hook"] = fixed.get("hook", script["hook"])
    script["outro"] = fixed.get("outro", script["outro"])
    for i, s in enumerate(script.get("scenes", [])):
        key = f"narration_{i}"
        if key in fixed:
            s["narration"] = fixed[key]

    return script
