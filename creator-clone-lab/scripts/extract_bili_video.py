#!/usr/bin/env python
"""
Extract public Bilibili video metadata and optionally download/merge video.

Usage:
  python scripts/extract_bili_video.py "https://b23.tv/..." --out samples/bili_video --download
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from capture_manifest import relative_file, stable_source_id, write_capture_manifest


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"


def request(url: str, *, binary: bool = False, referer: str = "https://www.bilibili.com/") -> str | bytes:
    req = Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "*/*",
            "Referer": referer,
            "Origin": "https://www.bilibili.com",
        },
    )
    try:
        with urlopen(req, timeout=120) as response:
            data = response.read()
            return data if binary else data.decode("utf-8", errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:300]}") from exc
    except URLError as exc:
        raise RuntimeError(f"request failed: {exc}") from exc


def resolve_url(url: str) -> str:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=60) as response:
        return response.geturl()


def find_bvid(url: str) -> str:
    resolved = resolve_url(url)
    match = re.search(r"BV[0-9A-Za-z]+", resolved)
    if match:
        return match.group(0)
    query = parse_qs(urlparse(resolved).query)
    for values in query.values():
        joined = " ".join(values)
        match = re.search(r"BV[0-9A-Za-z]+", joined)
        if match:
            return match.group(0)
    raise RuntimeError(f"could not find bvid in resolved URL: {resolved}")


def api_json(url: str, referer: str) -> dict:
    data = json.loads(request(url, referer=referer))
    if data.get("code") != 0:
        raise RuntimeError(f"API error {data.get('code')}: {data.get('message')}")
    return data["data"]


def normalize_url(url: str) -> str:
    url = url.replace("\\u0026", "&")
    if url.startswith("http://"):
        return "https://" + url[len("http://") :]
    if url.startswith("//"):
        return "https:" + url
    return url


def choose_video(dash: dict, quality: int) -> dict:
    videos = dash.get("video") or []
    avc = [v for v in videos if str(v.get("codecs", "")).startswith("avc1")]
    candidates = avc or videos
    if not candidates:
        raise RuntimeError("no video stream in playurl response")
    same_quality = [v for v in candidates if int(v.get("id", 0)) == quality]
    if same_quality:
        return same_quality[0]
    return sorted(candidates, key=lambda v: int(v.get("id", 0)), reverse=True)[0]


def download_file(url: str, path: Path, referer: str) -> None:
    path.write_bytes(request(normalize_url(url), binary=True, referer=referer))


def merge_with_ffmpeg(video_path: Path, audio_path: Path, out_path: Path) -> None:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(video_path), "-i", str(audio_path), "-c", "copy", str(out_path)]
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg merge failed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Bilibili video URL or b23 short link")
    parser.add_argument("--out", default="samples/bili_video")
    parser.add_argument("--download", action="store_true", help="Download DASH video/audio and merge to merged.mp4")
    parser.add_argument("--quality", type=int, default=32, help="Preferred quality id, 32=480P, 16=360P")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    bvid = find_bvid(args.url)
    referer = f"https://www.bilibili.com/video/{bvid}"
    view = api_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}", referer)
    (out_dir / "view.json").write_text(json.dumps(view, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "bvid": view.get("bvid"),
        "aid": view.get("aid"),
        "cid": view.get("cid"),
        "title": view.get("title"),
        "owner": (view.get("owner") or {}).get("name"),
        "duration": view.get("duration"),
        "pic": normalize_url(view.get("pic", "")),
        "pubdate": view.get("pubdate"),
        "stat": view.get("stat"),
        "subtitle": view.get("subtitle"),
        "ugc_season_stat": (view.get("ugc_season") or {}).get("stat"),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if summary["pic"]:
        try:
            download_file(summary["pic"], out_dir / "cover.jpg", referer)
        except Exception as exc:
            summary["cover_download_error"] = str(exc)

    if args.download:
        playurl = api_json(
            f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={view['cid']}&qn={args.quality}&fnval=16&fourk=1",
            referer,
        )
        (out_dir / "playurl.json").write_text(json.dumps(playurl, ensure_ascii=False, indent=2), encoding="utf-8")
        dash = playurl.get("dash") or {}
        video = choose_video(dash, args.quality)
        audios = dash.get("audio") or []
        if not audios:
            raise RuntimeError("no audio stream in playurl response")
        audio = audios[0]
        download_file(video["baseUrl"], out_dir / "video.m4s", referer)
        download_file(audio["baseUrl"], out_dir / "audio.m4s", referer)
        merge_with_ffmpeg(out_dir / "video.m4s", out_dir / "audio.m4s", out_dir / "merged.mp4")

    media_path = out_dir / "merged.mp4"
    stat = summary.get("stat") or {}
    manifest_path = write_capture_manifest(
        out_dir,
        platform="bilibili",
        creator=summary.get("owner") or "",
        capture_kind="single-video",
        items=[
            {
                "source_id": stable_source_id("bilibili", bvid, bvid),
                "content_type": "video",
                "url": referer,
                "title": summary.get("title") or "",
                "published_at": datetime.fromtimestamp(summary["pubdate"], tz=timezone.utc).isoformat()
                if summary.get("pubdate")
                else "",
                "local_path": relative_file(media_path if media_path.exists() else None, out_dir),
                "body_path": "",
                "understanding_level": "partial" if media_path.exists() else "metadata-only",
                "metrics": {
                    "views": stat.get("view"),
                    "likes": stat.get("like"),
                    "favorites": stat.get("favorite"),
                    "coins": stat.get("coin"),
                    "shares": stat.get("share"),
                    "comments": stat.get("reply"),
                    "danmaku": stat.get("danmaku"),
                },
            }
        ],
    )

    print(f"title: {summary['title']}")
    print(f"owner: {summary['owner']}")
    print(f"duration: {summary['duration']}s")
    print(f"view/like/fav/coin/reply: {summary['stat'].get('view')}/{summary['stat'].get('like')}/{summary['stat'].get('favorite')}/{summary['stat'].get('coin')}/{summary['stat'].get('reply')}")
    print(f"saved: {out_dir}")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"extract_bili_video failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
