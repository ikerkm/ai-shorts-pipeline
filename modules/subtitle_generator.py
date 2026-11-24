from pathlib import Path

# Cambia al estilo Highlighted (amarillo) y vuelve a Default (blanco)
_HIGHLIGHT = r"{\rHighlighted}"
_RESET     = r"{\r}"


def _ms_to_ass(ms: int) -> str:
    cs = (ms // 10) % 100
    s = (ms // 1000) % 60
    m = (ms // 60000) % 60
    h = ms // 3600000
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Rounded MT Bold,82,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,1,0,0,0,100,100,1,0,1,6,3,2,90,90,380,1
Style: Highlighted,Arial Rounded MT Bold,82,&H0000FFFF,&H000000FF,&H00000000,&H64000000,1,0,0,0,100,100,1,0,1,6,3,2,90,90,380,1
Style: Title,Arial Rounded MT Bold,64,&H00FFFFFF,&H000000FF,&H00111111,&HCC000000,1,0,0,0,100,100,2,0,1,5,3,8,60,60,150,1
Style: Hook,Arial Rounded MT Bold,100,&H00FFFFFF,&H000000FF,&H00000000,&H96000000,1,0,0,0,100,100,1,0,1,7,4,8,80,80,470,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# Palabra activa: salta al estilo Highlighted (amarillo) + pop de escala (116% -> 100%)
# que da el "snap" viral en cada palabra, y vuelve a Default tras la palabra.
def _active_tag() -> str:
    return r"{\rHighlighted\fscx116\fscy116\t(0,90,\fscx100\fscy100)}"


def _build_chunk_text(chunk: list[dict], active_idx: int) -> str:
    """Chunk de palabras con la palabra active_idx resaltada en amarillo + pop."""
    parts = []
    for j, w in enumerate(chunk):
        word = w["word"]
        if j == active_idx:
            parts.append(f"{_active_tag()}{word}{_RESET}")
        else:
            parts.append(word)
    return " ".join(parts)


def generate_ass(scenes: list[dict], output_path: Path, title: str = "",
                 hook: str = "", hook_dur_ms: int = 2200) -> Path:
    lines = [ASS_HEADER]

    # HOOK card — pattern interrupt contra el swipe del segundo 1.
    # Texto grande centrado en el tercio superior con "slam-in" (pop de escala +
    # fade) durante los primeros ~2,2s. Reemplaza la antigua tarjeta de título
    # pequeña: el espectador lee el gancho aunque vea el vídeo sin sonido.
    hook_text = (hook or title).strip()
    if hook_text:
        safe = hook_text.replace("\\", "").replace("{", "").replace("}", "")
        end = _ms_to_ass(max(800, hook_dur_ms))
        lines.append(
            f"Dialogue: 0,0:00:00.00,{end},Hook,,0,0,0,,"
            f"{{\\fad(120,250)\\fscx62\\fscy62\\t(0,200,\\fscx100\\fscy100)}}{safe}"
        )

    for scene in scenes:
        offset = scene["time_offset_ms"]
        timings = scene.get("word_timings", [])
        duration_ms = scene.get("duration_ms", 4000)

        if not timings:
            start = _ms_to_ass(offset)
            end   = _ms_to_ass(offset + duration_ms)
            lines.append(
                f"Dialogue: 0,{start},{end},Default,,0,0,0,,{scene['narration'].replace(chr(10), ' ')}"
            )
            continue

        chunk_size = 3
        chunks = [timings[ci:ci + chunk_size] for ci in range(0, len(timings), chunk_size)]

        for chunk_idx, chunk in enumerate(chunks):
            next_chunk_start = (
                offset + chunks[chunk_idx + 1][0]["start_ms"]
                if chunk_idx + 1 < len(chunks) else None
            )

            for wi, word_data in enumerate(chunk):
                w_start = offset + word_data["start_ms"]

                if wi + 1 < len(chunk):
                    # No es el último del chunk: termina cuando empieza la siguiente palabra
                    w_end = offset + chunk[wi + 1]["start_ms"]
                elif next_chunk_start is not None:
                    # Último del chunk pero hay más: termina justo donde empieza el siguiente chunk
                    w_end = next_chunk_start
                else:
                    # Última palabra de toda la escena: pequeño margen
                    w_end = offset + word_data["start_ms"] + word_data["duration_ms"] + 200

                if w_end - w_start < 80:
                    w_end = w_start + 80

                text = _build_chunk_text(chunk, wi)
                lines.append(
                    f"Dialogue: 0,{_ms_to_ass(w_start)},{_ms_to_ass(w_end)},Default,,0,0,0,,{text}"
                )

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
