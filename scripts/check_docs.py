#!/usr/bin/env python3
"""Validate repository Markdown encoding, fences, and local link targets."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
INLINE_CODE = re.compile(r"`[^`]*`")
EXTERNAL_SCHEMES = {"data", "http", "https", "mailto", "tel"}


def markdown_files() -> list[Path]:
    """Return all canonical Markdown documents in stable order."""

    return [
        REPOSITORY_ROOT / "README.md",
        *sorted((REPOSITORY_ROOT / "docs").rglob("*.md")),
    ]


def _destination(raw_destination: str) -> str:
    """Remove optional Markdown title syntax from one link destination."""

    destination = raw_destination.strip()
    if destination.startswith("<") and ">" in destination:
        return destination[1 : destination.index(">")]
    return destination.split(maxsplit=1)[0]


def _has_exact_case(path: Path) -> bool:
    """Check every path component case-sensitively, including on macOS."""

    try:
        relative = path.relative_to(REPOSITORY_ROOT)
    except ValueError:
        return False

    current = REPOSITORY_ROOT
    for part in relative.parts:
        try:
            names = {child.name for child in current.iterdir()}
        except OSError:
            return False
        if part not in names:
            return False
        current /= part
    return True


def _local_target(source: Path, destination: str) -> Path | None:
    """Resolve a local link target or return None for external and anchor links."""

    parsed = urlsplit(destination)
    if parsed.scheme.lower() in EXTERNAL_SCHEMES or destination.startswith("//"):
        return None
    if not parsed.path:
        return None

    decoded_path = unquote(parsed.path)
    if decoded_path.startswith("/"):
        return (REPOSITORY_ROOT / decoded_path.lstrip("/")).resolve()
    return (source.parent / decoded_path).resolve()


def check_document(path: Path) -> list[str]:
    """Return human-readable failures for one Markdown document."""

    failures: list[str] = []
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{path.relative_to(REPOSITORY_ROOT)}: cannot read UTF-8: {exc}"]

    relative_path = path.relative_to(REPOSITORY_ROOT)
    if b"\r" in raw:
        failures.append(f"{relative_path}: use LF line endings")
    if raw and not raw.endswith(b"\n"):
        failures.append(f"{relative_path}: file must end with a newline")

    active_fence: str | None = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        fence = FENCE.match(line)
        if fence:
            marker = fence.group(1)[0]
            if active_fence is None:
                active_fence = marker
            elif active_fence == marker:
                active_fence = None
            continue

        if active_fence is not None:
            continue

        searchable_line = INLINE_CODE.sub("", line)
        for match in MARKDOWN_LINK.finditer(searchable_line):
            destination = _destination(match.group(1))
            target = _local_target(path, destination)
            if target is None:
                continue
            if not target.exists():
                failures.append(f"{relative_path}:{line_number}: missing link target {destination}")
            elif not _has_exact_case(target):
                failures.append(
                    f"{relative_path}:{line_number}: link case does not match {destination}"
                )

    if active_fence is not None:
        failures.append(f"{relative_path}: unclosed Markdown code fence")
    return failures


def main() -> int:
    """Validate every repository document and print actionable failures."""

    failures = [failure for path in markdown_files() for failure in check_document(path)]
    if failures:
        print("Documentation validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(f"Validated {len(markdown_files())} Markdown documents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
