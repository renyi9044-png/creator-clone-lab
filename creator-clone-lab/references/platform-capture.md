# Platform Capture Reference

## Shared Order

1. Resolve the URL and identify profile vs individual item.
2. Try public extraction.
3. Reuse an already logged-in browser if public extraction is incomplete.
4. Ask for login only when no usable authenticated session exists.
5. Capture media, metadata, comments, OCR, ASR, and frames as available.
6. Write `capture_manifest.json` without cookies, tokens, or signed media URLs.
7. Import the manifest and register each source with its understanding level:

```bash
python scripts/import_capture_manifest.py <project_dir> <capture_manifest.json> --copy --auto-body
```

## Douyin And Kuaishou

- Prefer public short-link resolution first.
- Use authenticated browser responses for profile lists when public access is blocked.
- For no-subtitle videos, transcribe speech and OCR representative frames.
- Do not claim full understanding from the caption alone.

## Xiaohongshu

For public profile SSR candidates:

```bash
python scripts/extract_xhs_profile.py "<profile url>" --out <output> --download-covers
```

For a logged-in video detail page, launch Chrome with remote debugging, log in, then run:

```bash
python scripts/capture_xhs_video_from_debug_browser.py "<note url>" --out <output>
```

Successful downloads remove temporary signed media URLs from the saved network record. `--no-download` is a debugging mode that retains those temporary URLs; do not distribute its output.

Public profiles may expose titles, likes, types, and covers while hiding note IDs or media URLs. Treat those as candidates, not downloaded videos.

For image-text notes, process every carousel image with OCR and analyze the cover separately.

## Bilibili

```bash
python scripts/extract_bili_video.py "<bilibili or b23 url>" --out <output> --download
```

If `yt-dlp` returns HTTP 412, use the bundled API fallback and merge DASH video/audio with ffmpeg. Capture title, description, tags, duration, uploader, views, likes, coins, favorites, shares, comments, and danmaku when available.

## WeChat Articles

- Preserve the canonical article URL, title, author/account, publish time, body, images, and visible metrics.
- Normalize body text for search while keeping an immutable source copy.
- For large account archives, register each article independently so evidence remains traceable.

## Local Files

- Treat filenames as weak metadata only.
- Copy immutable sources into the project when requested.
- Process video/audio with ASR, images with OCR, and documents with structured parsers where available.

## ASR

Local first:

```bash
python scripts/transcribe_audio.py input.mp4 --provider local --output transcript.txt --language zh
```

API fallback:

```bash
python scripts/transcribe_audio.py input.mp4 --provider groq --output transcript.txt --language zh
```

Specialized terms may require a larger local model or a second provider comparison.
