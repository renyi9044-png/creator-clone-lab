from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "creator-clone-lab"

REQUIRED_FILES = [
    ROOT / "README.md",
    ROOT / "VERSION",
    SKILL / "SKILL.md",
    SKILL / "agents" / "openai.yaml",
]

FORBIDDEN_PARTS = {
    "__pycache__",
    "projects",
    "captures",
    "downloads",
    "output",
    "outputs",
    "browser-data",
    "chrome-data",
    ".venv",
}

FORBIDDEN_SUFFIXES = {
    ".pyc",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".har",
    ".mp3",
    ".wav",
    ".m4a",
    ".mp4",
    ".mov",
    ".webm",
}

SECRET_PATTERNS = {
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "Groq-style key": re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b"),
    "GitHub token": re.compile(r"\bgh[opusr]_[A-Za-z0-9]{20,}\b"),
    "Feishu app id": re.compile(r"\bcli_[A-Za-z0-9]{12,}\b"),
    "Windows user path": re.compile(r"[A-Za-z]:\\" + r"Users\\[^\\\s]+", re.IGNORECASE),
    "macOS user path": re.compile(r"/" + r"Users/[^/\s]+"),
    "Linux home path": re.compile(r"/" + r"home/[^/\s]+"),
}

TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".json", ".jsonl", ".txt", ""}


def fail(message: str) -> None:
    print(f"release validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_FILES if not path.is_file()]
    if missing:
        fail(f"missing required files: {', '.join(missing)}")

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        fail(f"invalid VERSION: {version!r}")

    skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    if not skill_text.startswith("---\nname: creator-clone-lab\ndescription:"):
        fail("SKILL.md frontmatter is missing or malformed")
    major_minor = ".".join(version.split(".")[:2])
    if f"# Creator Clone Lab V{major_minor}" not in skill_text:
        fail("VERSION and SKILL.md heading disagree")

    files = [path for path in ROOT.rglob("*") if path.is_file() and ".git" not in path.parts]
    for path in files:
        relative = path.relative_to(ROOT)
        lowered_parts = {part.lower() for part in relative.parts}
        if lowered_parts & FORBIDDEN_PARTS:
            fail(f"runtime directory is tracked: {relative.as_posix()}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            fail(f"runtime artifact is tracked: {relative.as_posix()}")
        if path.name == ".env" or path.name.startswith(".env."):
            fail(f"environment file is tracked: {relative.as_posix()}")

        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                fail(f"{label} found in {relative.as_posix()}")

    print(f"release validation passed: version={version}, files={len(files)}")


if __name__ == "__main__":
    main()
