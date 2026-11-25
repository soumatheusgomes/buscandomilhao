from __future__ import annotations

import asyncio
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def wrap(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if font.getlength(candidate) <= max_width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def render_slides(script: str, source: str, output_dir: str | Path, width: int = 1080, height: int = 1920) -> list[Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    background = (13, 17, 23)
    accent = (255, 176, 0)
    chunks = [chunk.strip() for chunk in script.split(". ") if chunk.strip()]
    slides: list[Path] = []

    for index, chunk in enumerate(chunks[:6], start=1):
        image = Image.new("RGB", (width, height), background)
        draw = ImageDraw.Draw(image)
        title_font = _font(68)
        body_font = _font(52)
        draw.rectangle((0, 0, width, 28), fill=accent)
        draw.text((70, 130), "BUSCANDO MILHAO", font=_font(38), fill=accent)
        lines = wrap(chunk + ".", body_font, width - 140)
        y = 620
        for line in lines[:12]:
            draw.text((70, y), line, font=body_font, fill=(255, 255, 255))
            y += 72
        if index == len(chunks) or index == 6:
            for source_line in wrap(source, _font(34), width - 140)[:4]:
                draw.text((70, height - 220), source_line, font=_font(34), fill=accent)
                y_source = height - 220
                y_source += 44
        draw.text((70, height - 90), f"{index}/{min(len(chunks), 6)}", font=_font(32), fill=(180, 180, 180))
        path = output / f"slide-{index:02d}.png"
        image.save(path)
        slides.append(path)
    return slides


async def generate_tts(script: str, output_path: str | Path) -> bool:
    try:
        import edge_tts
    except ImportError:
        return False
    communicate = edge_tts.Communicate(script, "pt-BR-FranciscaNeural")
    await communicate.save(str(output_path))
    return True


def synthesize(script: str, output_path: str | Path) -> bool:
    return asyncio.run(generate_tts(script, output_path))


def assemble_video(slides: list[Path], audio_path: Path | None, output_path: Path, duration_seconds: int = 45) -> bool:
    try:
        from moviepy import AudioFileClip, ImageSequenceClip
    except ImportError:
        try:
            from moviepy.editor import AudioFileClip, ImageSequenceClip
        except ImportError:
            return False

    if not slides:
        return False
    clip_duration = max(1.0, duration_seconds)
    clip = ImageSequenceClip(
        [str(path) for path in slides],
        durations=[clip_duration / len(slides)] * len(slides),
    )
    if audio_path and audio_path.exists():
        try:
            audio = AudioFileClip(str(audio_path))
            if hasattr(clip, "with_duration"):
                clip = clip.with_duration(min(clip_duration, audio.duration)).with_audio(audio)
            else:
                clip = clip.set_duration(min(clip_duration, audio.duration)).set_audio(audio)
        except Exception:
            pass
    clip.write_videofile(
        str(output_path),
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=2,
        logger=None,
    )
    clip.close()
    return output_path.exists()
