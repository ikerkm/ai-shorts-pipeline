import json
import anthropic
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ANTHROPIC_API_KEY

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """Eres el director creativo de la agencia de publicidad más absurda y brillante del mundo.
Tu especialidad es inventar productos imposibles y dotarlos de una identidad de marca tan seria que el espectador no sabe si reírse o creerlo.
El humor nunca es explícito — surge del contraste entre lo absurdo del producto y la solemnidad con que se presenta.

REGLA FUNDAMENTAL DE ANCLAJE:
Todo producto debe responder a estas 4 preguntas. Si falta alguna → el producto es inválido:
  1. QUÉ ES       — objeto físico concreto (parche, spray, cápsula, guante…)
  2. DÓNDE SE USA — contexto físico específico (en la cola, en la reunión, en la puerta…)
  3. CÓMO SE ACTIVA — acción física del usuario (pegar, rociar, encender, ponerse…)
  4. QUÉ PASA INMEDIATAMENTE — efecto observable sin inferencia ni psicología

REGLA DE DEFINICIÓN:
El producto SIEMPRE debe poder describirse con esta plantilla:
"Es un [OBJETO] que se usa en [LUGAR] y hace que cuando haces [ACCIÓN], ocurre [EFECTO INMEDIATO]."
Si no cabe en este molde → el producto es inválido.

PROHIBIDO en cualquier campo del JSON:
- "transforma energía social", "optimiza conversaciones", "mejora presencia"
- "reduce ansiedad", "potencia autenticidad", "activa conciencia corporal"
- porcentajes de laboratorio, "estudios internos", terminología técnica abstracta
- estados internos ("el usuario se siente", "genera confianza", "crea sinergias")

Respondes ÚNICAMENTE con JSON válido, sin markdown ni explicaciones."""


def generate_product(topic: str, style_hint: str = None) -> dict:
    """
    Genera un brief completo de producto absurdo para un vídeo de anuncio.
    topic puede ser una pista temática o vacío para total libertad creativa.
    """
    inspiration = f'Inspiración temática (úsala como punto de partida, no como límite): "{topic}"' if topic.strip() else "Inventa algo completamente original sin restricciones temáticas."

    _style_hints = {
        "ad_infomercial": (
            'OBLIGATORIO: visual_style debe ser estilo infomercial televisivo (80s-90s TV shopping, '
            'colores saturados vibrantes, set de TV barato, energía QVC). '
            'music_style DEBE ser exactamente "ad_infomercial". '
            'El producto debe ser doméstico, práctico o de uso diario — algo que vendería un presentador entusiasta gritando.'
        ),
        "ad_corporate": (
            'OBLIGATORIO: visual_style debe ser estilo Apple/Tesla minimalista (fondo blanco puro, '
            'fotografía de producto ultra limpia, sombras suaves, una sola fuente de luz). '
            'music_style DEBE ser exactamente "ad_corporate". '
            'El producto debe ser tecnológico, premium o aspiracional.'
        ),
        "ad_luxury": (
            'OBLIGATORIO: visual_style debe ser estilo lujo oscuro (Chanel/Dior/Rolex aesthetic, '
            'fondo negro o muy oscuro, iluminación chiaroscuro, atmósfera cinematográfica y seria). '
            'music_style DEBE ser exactamente "ad_luxury". '
            'El producto debe ser exclusivo, elitista o aspiracional de lujo.'
        ),
    }
    style_override = _style_hints.get(style_hint, "") if style_hint else ""

    prompt = f"""Inventa un producto absurdo e imposible para un anuncio de TikTok/YouTube Shorts.
{inspiration}

El producto debe:
- Ser imposible, ridículo o completamente innecesario, pero presentado con total seriedad corporativa
- Tener un nombre de marca creíble y un eslogan con doble sentido absurdo
- Poder representarse visualmente de forma CONSISTENTE en 5-6 escenas

Devuelve exactamente este JSON:
{{
  "product_name": "Nombre comercial con trademark. OBLIGATORIO: el nombre debe sonar natural cuando un narrador en español lo pronuncia en voz alta. Usa palabras o raíces en español, latín o italiano — NUNCA inglés. MALO: MeetEnd™, MeteoLure™, CaloVoid™, SkinBoost™ (suenan a inglés en boca española). BIEN: TermiNox™, CharlaPaz™, ReuniFin™, AquaPolvo™, SombraVoz®, NuloTas™, CierreActa™, PausaNul® (suenan naturales en español). Una sola palabra compuesta, máx 10 letras, con ™ o ®.",
  "tagline": "Eslogan absurdo pero convincente, máx 8 palabras",
  "product_type": "El sustantivo físico del objeto: champú, spray, crema, cápsula, parche, dispositivo, guante, pastilla, sérum... Una sola palabra.",
  "product_definition": "La definición completa usando la plantilla obligatoria: 'Es un [OBJETO físico con forma/tamaño/material] que se usa en [LUGAR o situación concreta] y hace que cuando haces [ACCIÓN física de activación], ocurre [EFECTO inmediato y observable].' Todos los huecos deben ser concretos. BIEN: 'Es un parche adhesivo circular del tamaño de una moneda de dos euros que se usa en la cola del supermercado y hace que cuando lo pegas en la clavícula derecha, la persona de delante deja de hablar contigo.' MAL: 'Es un producto que mejora la experiencia de espera.'",
  "problem": "LA PRIMERA FRASE YA CONTIENE EL PROBLEMA COMPLETO — no el contexto previo, el problema en sí. Si lees solo la primera frase, el espectador ya entiende qué está sufriendo. MALO: 'Son las 8:47. El metro va lleno. Tres personas miran el asiento.' (contexto, contexto, todavía no hay problema). BUENO: 'Tu descanso entre series dura treinta segundos. El tipo de al lado los aprovecha para contarte su rutina entera.' (primera frase = situación, segunda = problema completo). Máx 3 frases.",
  "product_rule": "LA REGLA ABSURDA DEL PRODUCTO en una sola frase que empiece por 'Este producto hace que'. Debe completarse con una acción humana concreta y observable. BIEN: 'Este producto hace que cualquier persona empiece a hablar de parkings subterráneos en veinte segundos.' / 'Este producto hace que nadie pueda terminar una frase sin mencionar el código postal.' / 'Este producto hace que los perros del parque se sienten formando una fila ordenada.' MAL: 'Este producto mejora las interacciones sociales del usuario.' / 'Este producto transforma la energía conversacional.' La frase entera debe poder decirse en voz alta y que cualquiera entienda qué pasa.",
  "product_rule_short": "LA REGLA EN 6 PALABRAS O MENOS. El titular del producto. Sin sujeto complejo, sin condiciones, sin 'cualquier persona situada a menos de'. Solo el efecto puro. Formato: verbo + consecuencia. BIEN: 'Hace que nadie te hable en la cola.' / 'Hace que cualquier reunión acabe en dos minutos.' / 'Hace que la gente empiece a hablar del tiempo.' MAL: 'Hace que cualquier persona situada en un radio de dos metros perciba una señal.' Debe poder decirse en menos de 3 segundos.",
  "observable_effects": {{
    "trigger": "La acción física exacta que activa el efecto — gesto específico, momento concreto. Ej: 'Aplicar dos pulsaciones en la muñeca derecha antes de entrar en cualquier sala.' Una frase.",
    "immediate_behavior": "Qué hace EXACTAMENTE la persona afectada en los siguientes 30 segundos — acción visible, sin inferencia, sin estado interno. BIEN: 'La persona que está enfrente interrumpe lo que está haciendo y busca papel para apuntar el código postal.' MAL: 'La persona percibe un cambio en el ambiente.' Una frase.",
    "social_consequence": "El ritual absurdo concreto que el entorno ha adoptado como respuesta normalizada al efecto. Con hora, objeto o norma específica. BIEN: 'En la oficina tienen un cuaderno en recepción donde apuntan los códigos postales que van surgiendo. Ya van 47 páginas.' Una frase."
  }},
  "social_behaviors": [
    "Comportamiento social absurdo #1 — UNA PERSONA CONCRETA ha reorganizado un ritual cotidiano alrededor del producto. NO es la reacción física inmediata al producto — es el hábito nuevo, extraño y concreto que esa persona ha adoptado porque el producto existe. MALO (reacción física): 'El pasajero retira las rodillas.' MALO (consecuencia de poder): 'Ahora todos le respetan.' BUENO (ritual social): 'La azafata lleva en su tablilla un mapa de asientos con los usuarios certificados marcados en verde. Antes de despegar, los señala con un rotulador nuevo.'",
    "Comportamiento social absurdo #2 — un grupo o institución ha creado un protocolo absurdo y completamente innecesario alrededor del producto. Tiene hora exacta, objeto específico o norma inventada. Nadie lo cuestiona. MALO: 'Sus compañeros ya no le molestan.' BUENO: 'Cada lunes a las 8:02, cuatro usuarios se reúnen en el aparcamiento para colocarse el parche por orden de antigüedad de suscripción. El más reciente sostiene los envoltorios vacíos.'",
    "Comportamiento social extremo — una institución oficial (colegio profesional, empresa, municipio, seguro médico) ha actualizado alguna norma o documento interno para adaptarse a la lógica del producto. El documento existe, tiene páginas, fue redactado por alguien con título. La norma es ridícula pero perfectamente coherente con el mecanismo."
  ],
  "usage_ritual": "Cómo se usa físicamente — con gesto específico y solemne, como instrucción de prospecto médico. Ej: 'Aplicar tres gotas en el lóbulo izquierdo antes de cualquier conversación.' Se usará en la narración de la escena 2.",
  "visual_anchor": "Descripción visual MUY específica del packaging para copiar verbatim en TODOS los image prompts — forma exacta, colores, material, texto del label, fondo. Ej: 'sleek matte charcoal bottle with cobalt-blue label reading CALOVOID™ in Helvetica capitals, silver pump dispenser, clinical white studio background'",
  "visual_style": "Estilo visual del anuncio. Uno de: '80s infomercial, VHS scan lines, oversaturated warm colors, cheap studio set' / 'Apple-style minimalist, pure white background, single dramatic light source, ultra clean' / 'luxury perfume ad, dark moody atmosphere, cinematic chiaroscuro' / 'NASA documentary, scientific laboratory, cold clinical lighting'",
  "ad_tone": "Tono del narrador. Ej: 'deadpan corporate spokesperson, eerily calm and serious' / 'enthusiastic 80s TV host, breathless delivery' / 'ASMR whispering, reverent' / 'dramatic film trailer, deep voice'",
  "tts_speed": 0.93,
  "music_style": "ad_corporate",
  "color_palette": "2-3 colores dominantes del producto separados por comas"
}}

Reglas:
{style_override}

- product_type: una sola palabra — el objeto físico que el espectador puede imaginar comprando
- product_definition: usa EXACTAMENTE la plantilla "Es un [OBJETO] que se usa en [LUGAR] y hace que cuando haces [ACCIÓN], ocurre [EFECTO]." Todos los huecos concretos y físicos.
- problem: situación social concreta con personajes claros — no sensaciones físicas, no conceptos abstractos
- product_rule: UNA frase, empieza por "Este producto hace que". Acción humana observable.
- product_rule_short: máx 6 palabras. El efecto puro sin condiciones. Si no cabe en 3 segundos de audio, está mal.
- observable_effects.trigger: una frase — el gesto físico que activa el efecto
- observable_effects.immediate_behavior: una frase — lo que ocurre en los siguientes 30 segundos, visible sin inferencia
- observable_effects.social_consequence: una frase — el ritual absurdo concreto que el entorno ha normalizado
- social_behaviors: tres rituales sociales con personas concretas, hora exacta u objeto específico. Sin éxito genérico, sin reacciones físicas directas.
- tts_speed: 0.85-0.90 serio/dramático, 0.92-0.95 corporativo normal, 0.98-1.05 entusiasta/rápido
- music_style: exactamente uno de "ad_corporate", "ad_infomercial", "ad_luxury"
- El humor nunca es explícito — el narrador JAMÁS rompe el personaje

CHECK FINAL OBLIGATORIO — antes de devolver el JSON, verifica:
✔ ¿Se puede dibujar el producto en una frase? (objeto + lugar + acción + efecto)
✔ ¿Se entiende cómo se usa sin explicación adicional?
✔ ¿El efecto es una acción observable, no un estado interno o emoción?
Si alguna respuesta es NO → reescribe el producto hasta que las tres sean SÍ."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    product = json.loads(text)
    print(f"  Producto  : {product['product_name']}")
    print(f"  Eslogan   : {product['tagline']}")
    print(f"  Problema  : {product['problem'][:70]}...")
    print(f"  Regla     : {product.get('product_rule','')[:70]}...")
    print(f"  Musica    : {product['music_style']}")
    return product
