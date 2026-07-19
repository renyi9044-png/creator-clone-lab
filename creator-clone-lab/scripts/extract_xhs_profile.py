#!/usr/bin/env python
"""
Extract public Xiaohongshu profile SSR data into structured benchmark files.

Usage:
  python scripts/extract_xhs_profile.py "https://xhslink.com/m/..." --out samples/xhs_creator --download-covers
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from capture_manifest import relative_file, stable_source_id, write_capture_manifest


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"


def fetch(url: str, *, binary: bool = False) -> str | bytes:
    req = Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.xiaohongshu.com/",
        },
    )
    try:
        with urlopen(req, timeout=60) as response:
            data = response.read()
            return data if binary else data.decode("utf-8", errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:300]}") from exc
    except URLError as exc:
        raise RuntimeError(f"request failed: {exc}") from exc


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.replace("\\u002F", "/")
    if url.startswith("http://"):
        return "https://" + url[len("http://") :]
    if url.startswith("//"):
        return "https:" + url
    return url


def parse_initial_state(html: str) -> dict:
    marker = "window.__INITIAL_STATE__="
    start = html.find(marker)
    if start < 0:
        raise RuntimeError("window.__INITIAL_STATE__ not found; page may require login or changed structure")
    start += len(marker)
    end = html.find("</script>", start)
    if end < 0:
        raise RuntimeError("initial state script terminator not found")
    raw = html[start:end].strip().rstrip(";")
    raw = re.sub(r"\bundefined\b", "null", raw)
    return json.loads(raw)


def extract_items(data: dict) -> dict:
    user = data.get("user", {})
    user_page = user.get("userPageData", {})
    cards: list[dict] = []
    seen: set[tuple[str | None, str | None]] = set()

    for group in user.get("notes", []):
        if not isinstance(group, list):
            continue
        for item in group:
            if not isinstance(item, dict):
                continue
            card = item.get("noteCard")
            if not isinstance(card, dict):
                continue
            cover = card.get("cover") or {}
            cover_url = normalize_url(cover.get("urlDefault") or cover.get("urlPre"))
            key = (card.get("displayTitle"), cover_url)
            if key in seen:
                continue
            seen.add(key)
            note_id = card.get("noteId")
            content_type = card.get("type")
            download_status = "candidate_only"
            if content_type == "normal":
                download_status = "cover_downloadable"
            elif content_type == "video" and note_id:
                download_status = "needs_detail_fetch"
            elif content_type == "video":
                download_status = "needs_note_detail_or_logged_browser"

            cards.append(
                {
                    "index": item.get("index"),
                    "note_id": note_id,
                    "xsec_token": card.get("xsecToken") or item.get("xsecToken"),
                    "type": content_type,
                    "title": card.get("displayTitle"),
                    "liked_count": card.get("interactInfo", {}).get("likedCount"),
                    "author": card.get("user", {}).get("nickname") or card.get("user", {}).get("nickName"),
                    "user_id": card.get("user", {}).get("userId"),
                    "cover_url": cover_url,
                    "cover_width": cover.get("width"),
                    "cover_height": cover.get("height"),
                    "download_status": download_status,
                }
            )

    return {
        "basic_info": user_page.get("basicInfo"),
        "interactions": user_page.get("interactions"),
        "tags": user_page.get("tags"),
        "note_queries": user.get("noteQueries"),
        "items": cards,
    }


def download_covers(items: list[dict], out_dir: Path, limit: int) -> None:
    image_dir = out_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    for idx, item in enumerate(items[:limit]):
        url = item.get("cover_url")
        if not url:
            continue
        suffix = Path(urlparse(url).path).suffix or ".webp"
        path = image_dir / f"cover_{idx:02d}{suffix}"
        try:
            path.write_bytes(fetch(url, binary=True))
            item["cover_file"] = str(path)
        except Exception as exc:
            item["cover_download_error"] = str(exc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Xiaohongshu profile/share URL")
    parser.add_argument("--out", default="samples/xhs_profile", help="Output folder")
    parser.add_argument("--download-covers", action="store_true")
    parser.add_argument("--cover-limit", type=int, default=30)
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    html = fetch(args.url)
    (out_dir / "profile.html").write_text(html, encoding="utf-8")
    data = parse_initial_state(html)
    profile = extract_items(data)

    if args.download_covers:
        download_covers(profile["items"], out_dir, args.cover_limit)

    (out_dir / "profile_items.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    basic_info = profile.get("basic_info") or {}
    creator = basic_info.get("nickname") or basic_info.get("nickName") or ""
    manifest_items = []
    for item in profile["items"]:
        note_id = item.get("note_id")
        identity = note_id or item.get("cover_url") or f"{item.get('title')}|{item.get('index')}"
        cover_file = Path(item["cover_file"]) if item.get("cover_file") else None
        manifest_items.append(
            {
                "source_id": stable_source_id("xiaohongshu", identity, note_id),
                "content_type": "video" if item.get("type") == "video" else "image-text",
                "url": f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else "",
                "title": item.get("title") or "",
                "published_at": "",
                "local_path": relative_file(cover_file, out_dir),
                "body_path": "",
                "understanding_level": "metadata-only",
                "metrics": {"likes": item.get("liked_count")},
                "capture_status": item.get("download_status"),
            }
        )
    manifest_path = write_capture_manifest(
        out_dir,
        platform="xiaohongshu",
        creator=creator,
        capture_kind="profile-candidates",
        items=manifest_items,
    )

    print(f"profile: {(profile.get('basic_info') or {}).get('nickname')}")
    print(f"items: {len(profile['items'])}")
    print(f"saved: {out_dir / 'profile_items.json'}")
    print(f"manifest: {manifest_path}")
    for item in profile["items"][:10]:
        print(f"{item.get('index')}\t{item.get('type')}\t{item.get('liked_count')}\t{item.get('title')}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"extract_xhs_profile failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
