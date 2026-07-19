#!/usr/bin/env python
"""
Check and optionally install media-capture dependencies for Creator Clone Lab.

Usage:
  python scripts/check_install_media_tools.py
  python scripts/check_install_media_tools.py --install
  python scripts/check_install_media_tools.py --install --install-system
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class PyDep:
    module: str
    package: str
    purpose: str


PY_DEPS = [
    PyDep("yt_dlp", "yt-dlp", "video/page extraction"),
    PyDep("websocket", "websocket-client", "browser debug connection"),
    PyDep("faster_whisper", "faster-whisper", "ASR speech-to-text"),
    PyDep("rapidocr_onnxruntime", "rapidocr-onnxruntime", "OCR for burned-in subtitles"),
    PyDep("PIL", "pillow", "image loading"),
    PyDep("networkx", "networkx", "Obsidian relationship graph previews"),
    PyDep("cv2", "opencv-python-headless", "frame processing"),
]


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def run(cmd: list[str]) -> int:
    print("+ " + " ".join(cmd))
    return subprocess.call(cmd)


def pip_install(packages: list[str]) -> list[str]:
    """Install independently so one unavailable wheel does not block every tool."""
    failed: list[str] = []
    for package in packages:
        cmd = [sys.executable, "-m", "pip", "install", package]
        if run(cmd) != 0:
            failed.append(package)
    return failed


def install_ffmpeg() -> None:
    system = platform.system().lower()
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return

    if system == "windows" and shutil.which("winget"):
        code = run(["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--accept-package-agreements", "--accept-source-agreements"])
        if code == 0:
            return
    elif system == "darwin" and shutil.which("brew"):
        code = run(["brew", "install", "ffmpeg"])
        if code == 0:
            return
    elif system == "linux" and shutil.which("apt-get"):
        code = run(["sudo", "apt-get", "update"])
        if code == 0:
            code = run(["sudo", "apt-get", "install", "-y", "ffmpeg"])
            if code == 0:
                return

    print("\nffmpeg/ffprobe are still missing.")
    print("Install manually:")
    print("  Windows: winget install --id Gyan.FFmpeg -e")
    print("  macOS:   brew install ffmpeg")
    print("  Ubuntu:  sudo apt-get update && sudo apt-get install -y ffmpeg")


def missing_python_packages() -> list[str]:
    missing: list[str] = []
    for dep in PY_DEPS:
        ok = has_module(dep.module)
        print(f"{dep.module:<24} {'OK' if ok else 'MISSING':<8} {dep.purpose}")
        if not ok:
            missing.append(dep.package)
    return missing


def has_ffmpeg_tools() -> tuple[bool, bool]:
    return shutil.which("ffmpeg") is not None, shutil.which("ffprobe") is not None


def has_sqlite_fts5() -> bool:
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE test_fts USING fts5(content)")
        conn.close()
        return True
    except sqlite3.Error:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true", help="Install missing Python packages")
    parser.add_argument("--install-system", action="store_true", help="Try installing ffmpeg with winget/brew/apt")
    args = parser.parse_args()

    print("Creator Clone Lab dependency check\n")

    missing_packages = missing_python_packages()
    ffmpeg_ok, ffprobe_ok = has_ffmpeg_tools()
    print(f"{'ffmpeg':<24} {'OK' if ffmpeg_ok else 'MISSING':<8} video/audio processing")
    print(f"{'ffprobe':<24} {'OK' if ffprobe_ok else 'MISSING':<8} media inspection")
    sqlite_fts_ok = has_sqlite_fts5()
    print(f"{'sqlite_fts5':<24} {'OK' if sqlite_fts_ok else 'MISSING':<8} local knowledge search")
    groq_key_ok = bool(os.environ.get("GROQ_API_KEY"))
    print(f"{'GROQ_API_KEY':<24} {'SET' if groq_key_ok else 'NOT SET':<8} optional API fallback for ASR")

    if args.install and missing_packages:
        print("\nInstalling missing Python packages...")
        failed_installs = pip_install(missing_packages)
        if failed_installs:
            print("\nCould not install: " + ", ".join(failed_installs))
            print("Continue with the installed capabilities and configure the documented fallback where available.")
        print("\nRechecking Python packages...")
        missing_packages = missing_python_packages()

    if args.install_system and (not ffmpeg_ok or not ffprobe_ok):
        print("\nTrying to install ffmpeg/ffprobe...")
        install_ffmpeg()
        ffmpeg_ok, ffprobe_ok = has_ffmpeg_tools()
        print(f"{'ffmpeg':<24} {'OK' if ffmpeg_ok else 'MISSING':<8} video/audio processing")
        print(f"{'ffprobe':<24} {'OK' if ffprobe_ok else 'MISSING':<8} media inspection")

    if not args.install and missing_packages:
        print("\nMissing Python packages. Run:")
        print(f"  {sys.executable} scripts/check_install_media_tools.py --install")

    asr_ok = has_module("faster_whisper") or groq_key_ok
    if not asr_ok:
        print("\nASR fallback is not ready.")
        print("Either install faster-whisper locally or set GROQ_API_KEY for API transcription.")
        print("If faster-whisper has no wheel for this Python version, use Python 3.11/3.12 or the API fallback.")

    if (not ffmpeg_ok or not ffprobe_ok) and not args.install_system:
        print("\nffmpeg/ffprobe missing. Run with --install-system or install manually:")
        print(f"  {sys.executable} scripts/check_install_media_tools.py --install-system")

    if not sqlite_fts_ok:
        print("\nSQLite FTS5 is unavailable in this Python build. Install a standard Python build with SQLite FTS5 support.")

    required_modules = {"yt_dlp", "websocket", "rapidocr_onnxruntime", "PIL", "networkx", "cv2"}
    required_missing = [dep.package for dep in PY_DEPS if dep.module in required_modules and not has_module(dep.module)]
    if required_missing or not asr_ok or not ffmpeg_ok or not ffprobe_ok or not sqlite_fts_ok:
        return 1

    print("\nAll required tools are available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
