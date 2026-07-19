# Platform Capture Reference

## Mandatory Playwright Controller

All web-platform capture starts through the installed `playwright` browser-automation skill. Playwright is the browser control and verification layer; specialized scripts handle downstream media extraction only after the target page and access level are confirmed.

1. Check that the `playwright` skill or Playwright CLI through `npx` is available.
2. Open the shared URL in a named Playwright session and resolve redirects.
3. Take a fresh snapshot and identify profile vs individual item from the visible page.
4. Inspect DOM and network activity before calling a specialized extractor.
5. Try the public page in Playwright without login.
6. Reuse an authenticated named Playwright session when public access is incomplete.
7. Ask the user to log in or verify only inside the headed Playwright window when no authenticated session exists.
8. Capture media, metadata, comments, screenshots, OCR, ASR, and frames as available.
9. Write `capture_manifest.json` without cookies, tokens, browser storage, or signed media URLs.
10. Import the manifest and register each source with its understanding level:

```bash
python scripts/import_capture_manifest.py <project_dir> <capture_manifest.json> --copy --auto-body
```

## Douyin And Kuaishou

- Resolve public short links and inspect the resulting page through Playwright first.
- Use authenticated Playwright sessions and observed browser responses for profile lists when public access is blocked.
- For no-subtitle videos, transcribe speech and OCR representative frames.
- Do not claim full understanding from the caption alone.

## Xiaohongshu

After Playwright confirms the public profile page, extract SSR candidates with:

```bash
python scripts/extract_xhs_profile.py "<profile url>" --out <output> --download-covers
```

For a logged-in video detail page, prefer a headed authenticated Playwright session. The bundled Chrome-debug script remains a downstream compatibility extractor when Playwright has confirmed the note URL and access state:

```bash
python scripts/capture_xhs_video_from_debug_browser.py "<note url>" --out <output>
```

Successful downloads remove temporary signed media URLs from the saved network record. `--no-download` is a debugging mode that retains those temporary URLs; do not distribute its output.

Public profiles may expose titles, likes, types, and covers while hiding note IDs or media URLs. Treat those as candidates, not downloaded videos.

For image-text notes, process every carousel image with OCR and analyze the cover separately.

## Bilibili

Open the Bilibili URL with Playwright and confirm the canonical video page before running:

```bash
python scripts/extract_bili_video.py "<bilibili or b23 url>" --out <output> --download
```

If `yt-dlp` returns HTTP 412, use the bundled API fallback and merge DASH video/audio with ffmpeg. Capture title, description, tags, duration, uploader, views, likes, coins, favorites, shares, comments, and danmaku when available.

## WeChat Articles

- Open and snapshot each article with Playwright before archiving it.
- Preserve the canonical article URL, title, author/account, publish time, body, images, and visible metrics.
- Normalize body text for search while keeping an immutable source copy.
- For large account archives, register each article independently so evidence remains traceable.

## Local Files

- Treat filenames as weak metadata only.
- Copy immutable sources into the project when requested.
- Process video/audio with ASR, images with OCR, and documents with structured parsers where available.

## ASR

Preferred automatic path (Groq first, local fallback):

```bash
python scripts/transcribe_audio.py input.mp4 --output transcript.txt --language zh
```

Configure the key in the operating-system user environment, not in the skill or project:

```powershell
[Environment]::SetEnvironmentVariable("GROQ_API_KEY", "your-key", "User")
```

```bash
export GROQ_API_KEY="your-key"
```

Create a key at `https://console.groq.com/keys`. Never commit it, package it, or ask the user to paste it into a public artifact. Restart the terminal or Codex after setting a persistent environment variable.

Use local explicitly when Groq cannot be configured:

```bash
python scripts/check_install_media_tools.py --install-local-asr
python scripts/transcribe_audio.py input.mp4 --provider local --output transcript.txt --language zh
```

Specialized terms may require a larger local model or a second provider comparison.
