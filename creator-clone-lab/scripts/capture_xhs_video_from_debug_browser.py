#!/usr/bin/env python
"""
Capture and download a Xiaohongshu video note from an already logged-in Chrome
debug session.

Start Chrome manually when needed:
  chrome.exe --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir=%TEMP%\\xhs-debug https://www.xiaohongshu.com/explore

Then log in and run:
  python scripts/capture_xhs_video_from_debug_browser.py "https://www.xiaohongshu.com/explore/..." --out samples/xhs_note
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from capture_manifest import canonical_public_url, relative_file, stable_source_id, write_capture_manifest

try:
    import websocket
except ImportError:  # pragma: no cover - handled at runtime for users
    websocket = None


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
VIDEO_HINTS = ("sns-video", ".mp4", "video_mp4")


class CdpClient:
    def __init__(self, ws_url: str) -> None:
        if websocket is None:
            raise RuntimeError("missing websocket-client; run scripts/check_install_media_tools.py --install")
        self.ws = websocket.create_connection(ws_url, timeout=5, suppress_origin=True)
        self.next_id = 0

    def close(self) -> None:
        self.ws.close()

    def send(self, method: str, params: dict[str, Any] | None = None) -> int:
        self.next_id += 1
        self.ws.send(json.dumps({"id": self.next_id, "method": method, "params": params or {}}))
        return self.next_id

    def wait_for_response(self, message_id: int, timeout: float = 5.0) -> dict[str, Any]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.ws.settimeout(max(0.1, deadline - time.time()))
            message = json.loads(self.ws.recv())
            if message.get("id") == message_id:
                return message
        raise TimeoutError(f"CDP response timeout for id {message_id}")

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 5.0) -> dict[str, Any]:
        return self.wait_for_response(self.send(method, params), timeout=timeout)

    def recv_event(self, timeout: float) -> dict[str, Any] | None:
        self.ws.settimeout(timeout)
        try:
            message = json.loads(self.ws.recv())
        except TimeoutError:
            return None
        except Exception:
            return None
        return message if "method" in message else None


def http_json(url: str) -> Any:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def get_page_target(debug_url: str) -> dict[str, Any]:
    targets = http_json(debug_url.rstrip("/") + "/json/list")
    pages = [target for target in targets if target.get("type") == "page" and target.get("webSocketDebuggerUrl")]
    if not pages:
        raise RuntimeError(f"no Chrome page target found at {debug_url}; start Chrome with --remote-debugging-port")
    # Prefer an existing Xiaohongshu tab so the logged-in profile is reused.
    for page in pages:
        if "xiaohongshu.com" in (page.get("url") or ""):
            return page
    return pages[0]


def looks_like_video_url(url: str, mime: str | None = None) -> bool:
    lower = url.lower()
    if mime and mime.lower().startswith("video/"):
        return True
    if "fe-platform" in lower:
        return False
    return any(hint in lower for hint in VIDEO_HINTS) and "xhscdn.com" in lower


def capture_video_urls(note_url: str, debug_url: str, wait_seconds: float) -> list[dict[str, Any]]:
    target = get_page_target(debug_url)
    client = CdpClient(target["webSocketDebuggerUrl"])
    captured: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        client.call("Network.enable")
        client.call("Page.enable")
        client.call("Page.navigate", {"url": note_url}, timeout=10)
        # A small nudge helps pages that load the video only after playback starts.
        client.send("Runtime.evaluate", {"expression": "setTimeout(() => document.querySelector('video')?.play?.(), 2500)"})

        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            event = client.recv_event(timeout=max(0.1, min(1.0, deadline - time.time())))
            if not event:
                continue
            method = event.get("method")
            params = event.get("params") or {}
            url = ""
            status = None
            mime = None
            if method == "Network.requestWillBeSent":
                request = params.get("request") or {}
                url = request.get("url") or ""
            elif method == "Network.responseReceived":
                response = params.get("response") or {}
                url = response.get("url") or ""
                status = response.get("status")
                mime = response.get("mimeType")
            if url and url not in seen and looks_like_video_url(url, mime):
                seen.add(url)
                captured.append({"url": url, "status": status, "mime": mime, "method": method})
    finally:
        client.close()
    return captured


def note_id_from_url(url: str) -> str:
    match = re.search(r"/(?:explore|discovery/item)/([A-Za-z0-9]+)", url)
    if match:
        return match.group(1)
    parsed = urlparse(url)
    fallback = re.sub(r"[^A-Za-z0-9]+", "_", parsed.path.strip("/"))[:40]
    return fallback or "xhs_video"


def download_video(url: str, referer: str, out_file: Path) -> None:
    headers = {
        "User-Agent": UA,
        "Referer": referer,
        "Accept": "*/*",
        "Range": "bytes=0-",
    }
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=120) as response:
            out_file.write_bytes(response.read())
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"download failed HTTP {exc.code}: {detail[:300]}") from exc
    except URLError as exc:
        raise RuntimeError(f"download failed: {exc}") from exc


def choose_download_candidates(items: list[dict[str, Any]]) -> list[str]:
    urls = [item["url"] for item in items]
    mp4_urls = [url for url in urls if ".mp4" in url.lower() or "sns-video" in url.lower()]
    return mp4_urls or urls


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("note_url", help="Xiaohongshu note/detail URL, usually https://www.xiaohongshu.com/explore/<note_id>")
    parser.add_argument("--debug-url", default="http://127.0.0.1:9222", help="Chrome remote debugging URL")
    parser.add_argument("--out", default="samples/xhs_video_note", help="Output folder")
    parser.add_argument("--wait", type=float, default=20.0, help="Seconds to watch network traffic")
    parser.add_argument("--no-download", action="store_true", help="Only save captured video URLs")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    urls = capture_video_urls(args.note_url, args.debug_url, args.wait)
    (out_dir / "network_video_urls.json").write_text(
        json.dumps({"note_url": args.note_url, "captured": urls}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if not urls:
        print("no video URL captured")
        print("Open the note in the logged-in Chrome tab, press play if needed, then retry with a longer --wait.")
        return 2

    print(f"captured video urls: {len(urls)}")
    for item in urls[:5]:
        print(f"- {item.get('status') or ''}\t{item.get('mime') or ''}\t{item['url'][:180]}")

    if args.no_download:
        print(f"saved: {out_dir / 'network_video_urls.json'}")
        return 0

    out_file = out_dir / f"{note_id_from_url(args.note_url)}.mp4"
    last_error = None
    for candidate in choose_download_candidates(urls):
        try:
            download_video(candidate, args.note_url, out_file)
            if out_file.stat().st_size >= 4096:
                break
            last_error = RuntimeError(f"downloaded file is too small: {out_file.stat().st_size} bytes")
        except Exception as exc:
            last_error = exc
            continue
    else:
        raise RuntimeError(f"no captured URL produced a usable video file: {last_error}")
    print(f"downloaded: {out_file}")
    print(f"bytes: {out_file.stat().st_size}")
    (out_dir / "network_video_urls.json").write_text(
        json.dumps(
            {
                "note_url": canonical_public_url(args.note_url),
                "captured_count": len(urls),
                "signed_urls_retained": False,
                "note": "Temporary signed media URLs were removed after download.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    note_id = note_id_from_url(args.note_url)
    manifest_path = write_capture_manifest(
        out_dir,
        platform="xiaohongshu",
        creator="",
        capture_kind="single-video",
        items=[
            {
                "source_id": stable_source_id("xiaohongshu", note_id, note_id),
                "content_type": "video",
                "url": canonical_public_url(args.note_url),
                "title": "",
                "published_at": "",
                "local_path": relative_file(out_file, out_dir),
                "body_path": "",
                "understanding_level": "partial",
                "metrics": {},
            }
        ],
    )
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"capture_xhs_video_from_debug_browser failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
