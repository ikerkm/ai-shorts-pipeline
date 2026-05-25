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
    return script


def generate_ad_script(product: dict, num_scenes: int = 6) -> dict:
    """Genera un guión de anuncio absurdo único — cada vídeo es diferente."""
    num_scenes = max(4, min(6, num_scenes))
    visual_anchor    = product["visual_anchor"]
    visual_style     = product["visual_style"]
    ad_tone          = product["ad_tone"]
    product_type     = product.get("product_type", "producto")
    usage_ritual     = product.get("usage_ritual", "")
    problem          = product.get("problem", product.get("problem_solved", ""))
    product_rule       = product.get("product_rule", product.get("core_logic", ""))
    product_rule_short = product.get("product_rule_short", "")
    product_definition = product.get("product_definition", "")
    obs                = product.get("observable_effects", {})
    trigger          = obs.get("trigger", "")
    immediate_behavior = obs.get("immediate_behavior", "")
    social_consequence = obs.get("social_consequence", "")
    escalation       = product.get("social_behaviors", product.get("escalation", product.get("fake_benefits", [])))

    system = """Eres el guionista de los anuncios absurdos más virales de España.

VOZ: locutor serio que no sabe que es gracioso. Frases completas y naturales — sujeto, verbo, complemento.
No telegráfico. No listas de sustantivos. Como un locutor de radio, no como un formulario.
La rareza está en los hechos. El narrador los presenta como si fueran completamente normales.

GUIÓN DE REFERENCIA — este es el registro exacto que debes replicar:
  hook:             "Sigues usando champú como si tu pelo tuviera futuro."
  problem:          "Te estás lavando el pelo sin saber que hoy es el último día que lo usas."
  physical_demo:    "CalvoClean. Champú transparente. Te lo aplicas en la ducha como cualquier otro. El pelo empieza a caerse de forma perfectamente ordenada."
  testimonial:      "Lo usé pensando que era hidratante. Ahora peino mi cuero cabelludo con orgullo y calendario."
  social_reaction:  "En gimnasios de Valencia, los usuarios comparan brillos de cabeza como si fueran modelos de coche nuevo."
  absurd_protocol:  "Las peluquerías han cambiado el horario: primero te lavan, luego te despiden con dignidad."
  outro:            "Si lo entiendes tarde, ya es tarde."

CUATRO PATRONES OBLIGATORIOS:

1. PROBLEMA — una o dos frases con ironía ya incorporada. El espectador sonríe antes de que aparezca el producto.
   El truco: añade "sin saber que" / "como si" / "todavía" para meter ironía sin explicarla.
   BIEN: "Te estás lavando el pelo sin saber que hoy es el último día que lo usas."
   MAL:  "Cada mañana caen cabellos. No sabes cuántos." — neutro, sin ironía, sin gancho.

2. PHYSICAL_DEMO — el producto parece completamente normal. La rareza está solo en el efecto.
   Cuatro frases naturales: [nombre] / [qué es, 2-3 palabras] / [cómo se usa, como si fuera lo más normal del mundo] / [el efecto absurdo, descrito con calma].
   BIEN: "CalvoClean. Champú transparente. Te lo aplicas en la ducha como cualquier otro. El pelo empieza a caerse de forma perfectamente ordenada."
   MAL:  "CalvaNox. Frasco negro. Lo aplicas. Los cabellos caen." — fragmentos sin sujeto, sin flujo, sin normalización del absurdo.
   La clave: "como cualquier otro" / "como siempre" / "igual que harías" normaliza el uso. El absurdo llega solo en la última frase.

3. TESTIMONIAL — contraste entre lo que alguien pensaba y lo que ocurrió.
   FÓRMULA EXACTA: "[Nombre] lo [usó/compró] [pensando que era X / sin saber qué era]. Ahora [consecuencia absurda y específica]."
   BIEN: "Miguel lo usó pensando que era hidratante. Ahora peina su cuero cabelludo con orgullo y calendario."
   MAL:  "El señor Ferrándiz lleva tres carpetas AZ." — no hay historia, no hay contraste, no hay chiste.
   El contraste entre el malentendido inicial y la consecuencia absurda ES el humor.

4. OUTRO — non-sequitur o condición absurda en una sola frase que remata con ironía.
   BIEN: "Si lo entiendes tarde, ya es tarde." / "Disponible mientras quede pelo que perder."
   MAL:  "Disponible solo si el martes no es martes." — sin relación con el producto.

PROHIBIDO:
- Frases telegráficas sin sujeto ni verbo: "Frasco negro. Lo aplicas. Los cabel."
- Abstracciones: "transforma", "optimiza", "mejora", "potencia", "genera confianza"
- Testimonios sin historia ni contraste
- Explicar el chiste con palabras como "paradójicamente" o "irónicamente"
- Referencias que solo tengan sentido viendo la imagen

IMAGEN por tipo de escena:
- "problem":          sin producto — momento del problema, persona en situación real
- "physical_demo":    producto en primera aparición, composición dramática
- "social_reaction":  producto visible, persona ejecutando el ritual absurdo
- "testimonial":      persona real con el producto, entorno cotidiano, expresión seria
- "absurd_protocol":  producto solo, pose definitiva

Respondes ÚNICAMENTE con JSON válido, sin markdown ni explicaciones."""

    social_behaviors = product.get("social_behaviors", escalation)
    escalation_text = "\n".join(f"  {i+1}. {e}" for i, e in enumerate(social_behaviors))

    prompt = f"""Crea un guión de anuncio absurdo para TikTok/Shorts (~50 segundos).

═══ PRODUCTO ═══
NOMBRE: {product['product_name']}
QUÉ ES: {product_definition}
ESLOGAN: {product['tagline']}
EN POCAS PALABRAS: {product_rule_short}
RITUALES QUE HA GENERADO:
{escalation_text}

═══ GUIÓN — {num_scenes} ESCENAS ═══

Escena 1 [problem]: el momento del problema. 1-2 frases que lo cierran de golpe.
  El oyente entiende la situación sin ver nada. Sin referencias visuales implícitas.
  Ejemplo: "Te estás lavando el pelo sin saber que hoy es el último día que lo usas."

Escena 2 [physical_demo]: presenta el producto con naturalidad. 3-4 frases conversacionales.
  Qué es + cómo se usa + qué pasa. Claro sin esfuerzo. No suena a prospecto médico.
  La frase "{product_rule_short}" debe aparecer en esta escena donde fluya mejor.
  Ejemplo: "CalvoClean. Champú transparente. Te lo aplicas en la ducha como cualquier otro. El pelo empieza a caerse de forma perfectamente ordenada."

Escenas 3 a {num_scenes-1} [social_reaction / testimonial]:
  social_reaction → UNA SOLA FRASE que describa qué pasa cuando todos tienen el producto a la vez.
    La gracia es que el producto resuelve el problema individual pero cuando todos lo usan, aparece un caos nuevo e inesperado.
    La frase debe ser fluida, con sujeto y verbo claros, sin fragmentos telegráficos.
    BIEN: "En el Mercanova de la calle Béjar, el noventa por ciento de los carritos llevan parche y la caja rápida lleva tres semanas sin un solo cliente."
    BIEN: "Toda la plantilla lleva la oblea encima y las reuniones duran cuatro minutos, así que ahora convocan dos seguidas para rellenar el hueco."
    BIEN: "Desde que todos los socios llevan el parche, las máquinas están siempre libres y la cola más larga del gimnasio es la de la fuente de agua."
    MAL (telegráfico, no usar): "Todos llevan parche. Las máquinas vacías. La fuente tiene cola."
  testimonial → primera persona, 2 frases con ironía seca. La persona que habla ES el testimonio (voz diferente al narrador).
    FÓRMULA: "Lo [usé/compré] pensando que era X. Ahora [consecuencia absurda específica en primera persona]."
    Ejemplo: "Lo usé pensando que era hidratante. Ahora peino mi cuero cabelludo con orgullo y calendario."
    Si es testimonial: añade campo "voice" (masculinas: "em_santa"/"pm_santa", femeninas: "ef_dora"/"pf_dora").

Escena {num_scenes} [absurd_protocol]: remate de una frase con punch. Puede ser institucional o cotidiano.
  Ejemplo: "Las peluquerías han cambiado el horario: primero te lavan, luego te despiden con dignidad."

Outro: una frase de cierre inesperada con ironía. Que corte.
  Ejemplo: "Si lo entiendes tarde, ya es tarde."

PROHIBIDO en la narración: nombres de locales concretos, nombres de ciudades, nombres de calles.
  MAL: "En el gimnasio Olympia de Albacete..." / "En el Mercanova de la calle Béjar..."
  BIEN: "En el gimnasio..." / "En el supermercado..." / "En la oficina..."

LÍMITE: ~{num_scenes * 18} palabras en total. Ortografía española perfecta: tildes y ñ siempre.

═══ FORMATO JSON — {num_scenes} escenas completas ═══
{{
  "title": "nombre del producto + gancho absurdo (máx 60 chars)",
  "hook": "frase de apertura del problema, sin mencionar el producto (máx 12 palabras)",
  "core_chain": {{
    "problem": "el problema en una frase",
    "mechanism": "qué hace el producto que resuelve eso",
    "result": "qué le pasa al espectador como consecuencia directa"
  }},
  "scenes": [
    {{
      "id": 1,
      "scene_type": "problem",
      "narration": "el momento del problema — concreto, sin producto, MÁXIMO 15 palabras",
      "image_prompt": "NO PRODUCT. {visual_style}. Show the human problem moment: specific realistic environment, specific person in the problematic situation. Medium or wide shot. 9:16 vertical, cinematic, natural lighting, no text overlay.",
      "image_negative": "product, bottle, jar, packaging, container, blurry, text overlay, watermark",
      "use_wan": true,
      "video_prompt": "slow cinematic motion of the problem scene — one specific element moving + slow camera motion. consistent stable lighting, no light variation."
    }},
    {{
      "id": 2,
      "scene_type": "physical_demo",
      "narration": "nombre del producto + qué hace físicamente + qué hace la persona afectada de inmediato — MÁXIMO 22 palabras",
      "image_prompt": "{visual_anchor} — dramatic 3/4 angle, elevated, on elegant surface (marble or slate), {visual_style}, strong directional light, deep shadow, 9:16 vertical, no text.",
      "image_negative": "blurry, text overlay, watermark, wrong colors, inconsistent design",
      "use_wan": true,
      "video_prompt": "slow zoom-in toward the product with gentle rotation, light catching the surface edge. consistent stable lighting, no light variation."
    }}
  ],
  "outro": "condición de compra imposible, dicha con calma (máx 8 palabras)"
}}

ESCENAS 3 A {num_scenes}:
- scene_type: "social_reaction" para rituales del entorno, "testimonial" para persona concreta en primera persona, "absurd_protocol" para el cierre
- narration: MÁXIMO 20 palabras — frase corta + detalle concreto, nada más
- PRODUCT image_prompt: siempre "{visual_anchor}" + composición diferente por escena (close-up / held in hand / worm's eye / lying on side) + {visual_style}
- TESTIMONIAL image_prompt: persona descrita físicamente (edad, aspecto, ropa, expresión deadpan) usando o sosteniendo {visual_anchor}, en entorno cotidiano real, {visual_style}
- CTA image_prompt: "{visual_anchor}" centrado, luz lateral dramática, {visual_style}
- Narración DISTINTA en cada escena, siempre avanzando la cadena
- NO incluyas ™ ni ® en narración — solo en el title
- Ortografía española perfecta: tildes y ñ siempre"""

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
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
