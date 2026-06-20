"""Fail CI when active docs use deprecated entity IDs or removed dashboard files."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DOC_PATHS = [
    ROOT / "README.md",
    ROOT / "modeldeck" / "README.md",
    ROOT / "docs",
]

DEPRECATED_ENTITY = re.compile(
    r"sensor\.(codex|claude|cursor)_[a-z0-9_]+",
    re.IGNORECASE,
)

COLLECTOR_STATUS_ENTITY = re.compile(
    r"sensor\.[a-z]+_collector_status",
    re.IGNORECASE,
)

HISTORY_YAML = re.compile(r"modeldeck-history\.yaml", re.IGNORECASE)

ALLOWLIST_FILES = {
    ROOT / "CHANGELOG.md",
}

ALLOWLIST_LINE_PATTERNS = (
    re.compile(r"short slug", re.IGNORECASE),
    re.compile(r"v0\.1\.0", re.IGNORECASE),
    re.compile(r"v0\.1\.[0-4]", re.IGNORECASE),
    re.compile(r"historical", re.IGNORECASE),
    re.compile(r"migration", re.IGNORECASE),
    re.compile(r"Old short slug", re.IGNORECASE),
    re.compile(r"still see only", re.IGNORECASE),
)


def _iter_markdown_files() -> list[Path]:
    files: list[Path] = []
    for path in DOC_PATHS:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.rglob("*.md")))
    return [f for f in files if f not in ALLOWLIST_FILES]


def _line_allowed(line: str) -> bool:
    if "|" in line and "sensor.modeldeck_" in line:
        return True
    if re.match(r"^\|\s*`sensor\.(codex|claude|cursor)", line, re.IGNORECASE):
        return True
    return any(p.search(line) for p in ALLOWLIST_LINE_PATTERNS)


def check_file(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(ROOT)
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _line_allowed(line):
            continue
        if DEPRECATED_ENTITY.search(line):
            errors.append(f"{rel}:{lineno}: deprecated short-slug entity ID")
        if COLLECTOR_STATUS_ENTITY.search(line):
            errors.append(f"{rel}:{lineno}: use sensor.modeldeck_{{provider}}_status")
        if HISTORY_YAML.search(line):
            errors.append(f"{rel}:{lineno}: references removed modeldeck-history.yaml")
    return errors


def main() -> int:
    all_errors: list[str] = []
    for path in _iter_markdown_files():
        all_errors.extend(check_file(path))
    if all_errors:
        print("Deprecated documentation patterns found:\n")
        for err in all_errors:
            print(f"  {err}")
        return 1
    print("Documentation entity ID check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
