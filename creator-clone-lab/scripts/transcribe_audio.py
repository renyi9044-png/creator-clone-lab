#!/usr/bin/env python
"""
Transcribe an audio/video file for Creator Clone Lab.

Default behavior:
  1. Try local faster-whisper when installed.
  2. Fall back to Groq Whisper API when GROQ_API_KEY is set.

Usage:
  python scripts/transcribe_audio.py input.mp4 --output transcript.txt --language zh
  python scripts/transcribe_audio.py input.mp4 --provider groq --output transcript.txt
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


GROQ_TRANSCRIPTIONS_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


def has_local_whisper() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except Exception:
        return False
    return True


def transcribe_local(path: Path, language: str | None, model_name: str) -> str:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(path), language=language)
    return "\n".join(segment.text.strip() for segment in segments if segment.text.strip())


def multipart_body(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = "----creator-clone-lab-" + uuid.uuid4().hex
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")

    filename = file_path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    chunks.append(f"--{boundary}\r\n".encode("utf-8"))
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(file_path.read_bytes())
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


def transcribe_groq(path: Path, language: str | None, model_name: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")

    if path.stat().st_size > 25 * 1024 * 1024:
        print("Warning: Groq free tier direct uploads are documented with a 25 MB file limit.", file=sys.stderr)
        print("Compress or cut the audio before retrying if the request fails.", file=sys.stderr)

    fields = {
        "model": model_name,
        "response_format": "text",
    }
    if language:
        fields["language"] = language

    body, boundary = multipart_body(fields, "file", path)
    request = Request(
        GROQ_TRANSCRIPTIONS_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "text/plain, application/json",
            "User-Agent": "creator-clone-lab/1.0",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=300) as response:
            return response.read().decode("utf-8", errors="replace").strip()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
            detail = json.dumps(parsed, ensure_ascii=False)
        except Exception:
            pass
        raise RuntimeError(f"Groq transcription failed: HTTP {exc.code} {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Groq transcription failed: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Audio or video file to transcribe")
    parser.add_argument("--output", "-o", help="Write transcript to this file")
    parser.add_argument("--language", default="zh", help="ISO-639-1 language code, e.g. zh, en")
    parser.add_argument("--provider", choices=["auto", "local", "groq"], default="auto", help="auto uses local first, then Groq fallback")
    parser.add_argument("--local-model", default="small", help="faster-whisper model, e.g. base, small, medium; use medium or Groq for better Chinese creator terms")
    parser.add_argument("--groq-model", default="whisper-large-v3-turbo")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 2

    provider = args.provider
    transcript: str

    if provider in {"auto", "local"} and has_local_whisper():
        transcript = transcribe_local(input_path, args.language, args.local_model)
        used = "local"
    elif provider == "local":
        print("Local faster-whisper is not installed. Run check_install_media_tools.py --install.", file=sys.stderr)
        return 1
    elif provider in {"auto", "groq"}:
        transcript = transcribe_groq(input_path, args.language, args.groq_model)
        used = "groq"
    else:
        print("No ASR provider is available. Install faster-whisper or set GROQ_API_KEY.", file=sys.stderr)
        return 1

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(transcript + "\n", encoding="utf-8")
        print(f"Transcript written with {used} provider: {output_path}")
    else:
        print(transcript)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
