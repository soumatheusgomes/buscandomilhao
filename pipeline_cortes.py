#!/usr/bin/env python3
"""Create short vertical sports clips from a video URL or local media file."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from yt_dlp import YoutubeDL

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".m4v", ".avi"}
ANALYSIS_WINDOW_SECONDS = 15 * 60
TRANSCRIPTION_CHUNK_SECONDS = 10 * 60
MIN_CLIP_SECONDS = 45
MAX_CLIP_SECONDS = 65


class PipelineError(RuntimeError):
    """An expected pipeline failure with a message suitable for the operator."""


def run_command(command: list[str], *, capture_output: bool = False) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture_output else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise PipelineError(f"Ferramenta não encontrada: {command[0]}.") from exc
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or "").strip()
        raise PipelineError(
            f"Falha ao executar {command[0]}."
            + (f"\nDetalhes: {details[-2500:]}" if details else "")
        ) from exc
    return result.stdout if capture_output else ""


def require_media_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise PipelineError(
                f"{tool} não foi encontrado no PATH. Instale o FFmpeg e tente novamente."
            )


def download_source(url: str, destination: Path) -> Path:
    options = {
        "format": "bestvideo*+bestaudio/best",
        "outtmpl": str(destination / "%(title).80s-%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
            candidates = [
                download.get("filepath")
                for download in info.get("requested_downloads", [])
                if download.get("filepath")
            ]
            candidates.extend(
                [info.get("filepath"), info.get("_filename"), downloader.prepare_filename(info)]
            )
    except Exception as exc:
        raise PipelineError(f"Não foi possível baixar o vídeo: {exc}") from exc

    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise PipelineError("O download terminou, mas o arquivo de vídeo não foi localizado.")


def get_duration(media_path: Path) -> float:
    output = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ],
        capture_output=True,
    )
    try:
        duration = float(output.strip())
    except ValueError as exc:
        raise PipelineError(f"Não foi possível determinar a duração de {media_path}.") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise PipelineError("A duração do vídeo é inválida.")
    return duration


def get_field(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def transcribe_media(client: OpenAI, media_path: Path, work_dir: Path) -> list[dict[str, Any]]:
    duration = get_duration(media_path)
    audio_dir = work_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    transcript_segments: list[dict[str, Any]] = []
    model = os.getenv("TRANSCRIPTION_MODEL", "whisper-1")

    for chunk_index, start in enumerate(range(0, math.ceil(duration), TRANSCRIPTION_CHUNK_SECONDS)):
        chunk_duration = min(TRANSCRIPTION_CHUNK_SECONDS, duration - start)
        if chunk_duration <= 0:
            continue
        audio_path = audio_dir / f"chunk_{chunk_index:03d}.mp3"
        run_command(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-ss",
                str(start),
                "-i",
                str(media_path),
                "-t",
                str(chunk_duration),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-b:a",
                "64k",
                str(audio_path),
            ]
        )
        try:
            with audio_path.open("rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model=model,
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
        except Exception as exc:
            raise PipelineError(
                f"Falha na transcrição do trecho iniciado em {start}s: {exc}"
            ) from exc

        segments = get_field(response, "segments", [])
        if not segments:
            raise PipelineError(
                "A API não retornou segmentos com timestamps. "
                "Confirme se o modelo de transcrição aceita verbose_json."
            )
        for segment in segments:
            segment_start = get_field(segment, "start")
            segment_end = get_field(segment, "end")
            segment_text = str(get_field(segment, "text", "")).strip()
            if segment_start is None or segment_end is None or not segment_text:
                continue
            transcript_segments.append(
                {
                    "start": round(start + float(segment_start), 3),
                    "end": round(start + float(segment_end), 3),
                    "text": segment_text,
                }
            )

    if not transcript_segments:
        raise PipelineError("A transcrição não contém segmentos utilizáveis.")
    return transcript_segments


def call_json_model(client: OpenAI, model: str, prompt: str) -> dict[str, Any]:
    try:
        response = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            temperature=0.4,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é editor de cortes de análise esportiva. "
                        "Trabalhe somente com os fatos e falas presentes na transcrição. "
                        "Não invente contexto, citações ou acusações. Responda somente JSON válido."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content
        result = json.loads(content or "")
    except Exception as exc:
        raise PipelineError(f"Falha na análise da transcrição pelo LLM: {exc}") from exc
    if not isinstance(result, dict):
        raise PipelineError("O LLM retornou uma resposta JSON em formato inesperado.")
    return result


def validate_candidate(
    candidate: Any, *, video_duration: float, lower_bound: float, upper_bound: float
) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        raise PipelineError("O LLM retornou um candidato de corte inválido.")
    try:
        start = float(candidate["start"])
        end = float(candidate["end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PipelineError("Um candidato não contém timestamps numéricos válidos.") from exc
    clip_duration = end - start
    if not (math.isfinite(start) and math.isfinite(end)):
        raise PipelineError("Um candidato contém timestamps não finitos.")
    if clip_duration < MIN_CLIP_SECONDS or clip_duration > MAX_CLIP_SECONDS:
        raise PipelineError(
            f"Duração de corte fora do intervalo permitido ({MIN_CLIP_SECONDS}–{MAX_CLIP_SECONDS}s)."
        )
    if start < lower_bound or end > upper_bound or end > video_duration:
        raise PipelineError("Um candidato está fora do intervalo de vídeo analisado.")
    return {
        "start": round(start, 3),
        "end": round(end, 3),
        "duration": round(clip_duration, 3),
        "reason": str(candidate.get("reason", "")).strip(),
        "category": str(candidate.get("category", "análise")).strip(),
        "score": candidate.get("score", 5),
    }


def discover_candidates(
    client: OpenAI, model: str, segments: list[dict[str, Any]], video_duration: float
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    window_count = math.ceil(video_duration / ANALYSIS_WINDOW_SECONDS)
    for window_index in range(window_count):
        lower = window_index * ANALYSIS_WINDOW_SECONDS
        upper = min((window_index + 1) * ANALYSIS_WINDOW_SECONDS, video_duration)
        window_segments = [
            segment
            for segment in segments
            if segment["start"] < upper and segment["end"] > lower
        ]
        if not window_segments:
            continue
        transcript = "\n".join(
            f"[{item['start']:.1f}-{item['end']:.1f}] {item['text']}"
            for item in window_segments
        )
        result = call_json_model(
            client,
            model,
            (
                "Encontre de 0 a 5 possíveis cortes fortes nesta transcrição de futebol "
                "(polêmica, bastidores, análise tática ou declaração marcante). "
                "Cada corte deve durar entre 45 e 65 segundos, usar timestamps absolutos "
                f"do vídeo e ficar dentro de {lower:.1f}s–{upper:.1f}s. "
                "Prefira trechos que façam sentido sem contexto externo. Não fabrique falas. "
                'Formato: {"candidates":[{"start":0,"end":50,"category":"tática",'
                '"score":1,"reason":"motivo factual"}]}. '
                f"Janela analisada: {lower:.1f}s–{upper:.1f}s.\n\n{transcript}"
            ),
        )
        batch = result.get("candidates")
        if not isinstance(batch, list) or len(batch) > 5:
            raise PipelineError("O LLM retornou uma lista de candidatos inválida.")
        candidates.extend(
            validate_candidate(
                item,
                video_duration=video_duration,
                lower_bound=lower,
                upper_bound=upper,
            )
            for item in batch
        )

    if len(candidates) < 3:
        raise PipelineError(
            "Foram encontrados menos de 3 candidatos válidos. "
            "Use um vídeo mais longo ou com mais conteúdo relevante."
        )
    return candidates


def select_final_clips(
    client: OpenAI, model: str, candidates: list[dict[str, Any]], video_duration: float
) -> list[dict[str, Any]]:
    result = call_json_model(
        client,
        model,
        (
            "Selecione os 3 a 5 melhores cortes distintos da lista. Evite sobreposição entre "
            "intervalos. Mantenha os timestamps exatamente iguais aos candidatos. "
            "Para cada corte, gere em português brasileiro: hook curto para o topo (máximo "
            "60 caracteres), legenda de postagem objetiva (máximo 500 caracteres), "
            "categoria, nota viral de 1 a 10 e justificativa factual. Não invente nomes, "
            "falas, contexto, polêmica ou acusações. Use somente as informações fornecidas. "
            f"A duração total do vídeo é {video_duration:.1f}s. "
            'Formato: {"clips":[{"start":0,"end":50,"hook":"...","caption":"...",'
            '"category":"...","score":8,"reason":"..."}]}.\n\n'
            + json.dumps(candidates, ensure_ascii=False)
        ),
    )
    clips = result.get("clips")
    if not isinstance(clips, list) or not 3 <= len(clips) <= 5:
        raise PipelineError("O LLM não selecionou entre 3 e 5 cortes.")

    validated: list[dict[str, Any]] = []
    for clip in clips:
        candidate = validate_candidate(
            clip, video_duration=video_duration, lower_bound=0, upper_bound=video_duration
        )
        hook = str(clip.get("hook", "")).strip()
        caption = str(clip.get("caption", "")).strip()
        if not hook or len(hook) > 60:
            raise PipelineError("Um hook está vazio ou excede 60 caracteres.")
        if not caption or len(caption) > 500:
            raise PipelineError("Uma legenda está vazia ou excede 500 caracteres.")
        try:
            score = float(clip["score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PipelineError("Um corte não possui nota numérica válida.") from exc
        if not 1 <= score <= 10:
            raise PipelineError("A nota de um corte deve estar entre 1 e 10.")
        candidate.update(
            {
                "hook": hook,
                "caption": caption,
                "category": str(clip.get("category", candidate["category"])).strip(),
                "score": score,
                "reason": str(clip.get("reason", candidate["reason"])).strip(),
            }
        )
        validated.append(candidate)

    by_start = sorted(validated, key=lambda clip: clip["start"])
    for previous, current in zip(by_start, by_start[1:]):
        if current["start"] < previous["end"]:
            raise PipelineError("O LLM selecionou cortes sobrepostos; tente novamente.")
    return sorted(validated, key=lambda clip: clip["score"], reverse=True)


def load_title_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_path = os.getenv("FONT_PATH", "").strip()
    candidates = [font_path] if font_path else []
    candidates.extend(
        [
            r"C:\Windows\Fonts\arialbd.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default(size=size)


def make_title_image(title: str, image_path: Path) -> None:
    image = Image.new("RGBA", (1080, 340), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font_size = 66
    max_width = 930
    lines: list[str] = []
    while font_size >= 38:
        font = load_title_font(font_size)
        lines = []
        current = ""
        for word in title.split():
            proposed = f"{current} {word}".strip()
            if draw.textbbox((0, 0), proposed, font=font)[2] <= max_width:
                current = proposed
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if len(lines) <= 2:
            break
        font_size -= 4
    font = load_title_font(font_size)
    line_height = font_size + 12
    box_height = max(120, len(lines) * line_height + 48)
    draw.rounded_rectangle((40, 24, 1040, 24 + box_height), radius=28, fill=(0, 0, 0, 205))
    for line_index, line in enumerate(lines):
        text_width = draw.textbbox((0, 0), line, font=font)[2]
        x = (1080 - text_width) / 2
        y = 24 + 24 + line_index * line_height
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255), stroke_width=1)
    image.save(image_path)


def render_clip(
    source: Path, clip: dict[str, Any], index: int, output_dir: Path, layout: str, work_dir: Path
) -> Path:
    title_path = work_dir / f"title_{index:02d}.png"
    output_path = output_dir / f"corte_{index:02d}.mp4"
    make_title_image(clip["hook"], title_path)
    if layout == "blur":
        video_filter = (
            "[0:v]split=2[bg][fg];"
            "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,boxblur=20:10[background];"
            "[fg]scale=1080:1600:force_original_aspect_ratio=decrease[foreground];"
            "[background][foreground]overlay=(W-w)/2:(H-h)/2[base];"
            "[1:v]format=rgba[title];"
            "[base][title]overlay=0:0:format=auto[v]"
        )
    else:
        video_filter = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920[base];"
            "[1:v]format=rgba[title];"
            "[base][title]overlay=0:0:format=auto[v]"
        )
    run_command(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-ss",
            f"{clip['start']:.3f}",
            "-i",
            str(source),
            "-loop",
            "1",
            "-framerate",
            "30",
            "-i",
            str(title_path),
            "-t",
            f"{clip['duration']:.3f}",
            "-filter_complex",
            video_filter,
            "-map",
            "[v]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(output_path),
        ]
    )
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera de 3 a 5 cortes verticais de uma coletiva ou podcast esportivo."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="URL de vídeo do YouTube ou caminho de um arquivo de vídeo local.",
    )
    parser.add_argument(
        "--layout",
        choices=("blur", "crop"),
        default="blur",
        help="Fundo desfocado com vídeo ajustado (padrão) ou crop centralizado.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/cortes",
        help="Pasta de saída (padrão: outputs/cortes).",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    require_media_tools()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or api_key == "your_openai_api_key":
        raise PipelineError("Defina OPENAI_API_KEY no arquivo .env.")
    if not os.getenv("OPENAI_MODEL", "").strip():
        raise PipelineError("Defina OPENAI_MODEL no arquivo .env.")

    input_value = args.input.strip()
    is_url = input_value.lower().startswith(("https://", "http://"))
    local_source = Path(input_value).expanduser()
    if not is_url and not local_source.is_file():
        raise PipelineError(f"Arquivo de entrada não encontrado: {local_source}")
    if not is_url and local_source.suffix.lower() not in VIDEO_EXTENSIONS:
        raise PipelineError(
            "Formato de vídeo local não reconhecido. "
            f"Extensões aceitas: {', '.join(sorted(VIDEO_EXTENSIONS))}."
        )

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    client = OpenAI(api_key=api_key)
    model = os.environ["OPENAI_MODEL"].strip()

    with tempfile.TemporaryDirectory(prefix="pipeline_cortes_") as temporary:
        work_dir = Path(temporary)
        source = download_source(input_value, work_dir) if is_url else local_source.resolve()
        duration = get_duration(source)
        if duration < MIN_CLIP_SECONDS * 3:
            raise PipelineError(
                "A fonte precisa ter pelo menos 135 segundos para produzir 3 cortes distintos."
            )
        print(f"Transcrevendo: {source.name}")
        transcript = transcribe_media(client, source, work_dir)
        print(f"Analisando {len(transcript)} segmentos da transcrição...")
        candidates = discover_candidates(client, model, transcript, duration)
        clips = select_final_clips(client, model, candidates, duration)
        manifest: list[dict[str, Any]] = []

        for index, clip in enumerate(clips, start=1):
            output_path = render_clip(source, clip, index, output_dir, args.layout, work_dir)
            sidecar_path = output_dir / f"corte_{index:02d}.txt"
            sidecar_path.write_text(
                f"{clip['hook']}\n\n{clip['caption']}\n",
                encoding="utf-8",
            )
            manifest.append(
                {
                    **clip,
                    "file": output_path.name,
                    "caption_file": sidecar_path.name,
                    "layout": args.layout,
                }
            )

        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "source": source.name,
                    "transcription_model": os.getenv("TRANSCRIPTION_MODEL", "whisper-1"),
                    "analysis_model": model,
                    "clips": manifest,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    print(f"Concluído: {len(clips)} cortes em {output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PipelineError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(1)
