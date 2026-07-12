#!/usr/bin/env python3
"""Synchronize and validate repository-managed agent Skills."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

SOURCE_DIRECTORY = Path("agent-skills")
MIRROR_DIRECTORIES = (Path(".agents/skills"), Path(".claude/skills"))
SKILL_FILENAME = "SKILL.md"
ALLOWED_FRONTMATTER_KEYS = {"name", "description"}
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_SKILL_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
YAML_NON_STRING_SCALARS = {
    "null",
    "~",
    "true",
    "false",
    "yes",
    "no",
    "on",
    "off",
    "y",
    "n",
    ".nan",
    ".inf",
    "-.inf",
    "+.inf",
}
YAML_PLAIN_FORBIDDEN_START = frozenset("-?:,[]{}#&*!|>'\"%@`~")
FRONTMATTER_PATTERN = re.compile(
    r"\A---(?:\r\n|\n)(?P<metadata>.*?)(?P<closing>^---(?:\r\n|\n|\Z))",
    re.DOTALL | re.MULTILINE,
)


def display_path(path: Path, repository_root: Path) -> str:
    """Return a stable repository-relative path for diagnostics."""
    try:
        return path.relative_to(repository_root).as_posix()
    except ValueError:
        return path.as_posix()


def find_symlink_component(path: Path, repository_root: Path) -> Path | None:
    """Return the first symlink between the repository root and a managed path."""
    try:
        relative_path = path.relative_to(repository_root)
    except ValueError:
        return path

    current = repository_root
    for component in relative_path.parts:
        current /= component
        if current.is_symlink():
            return current
        if not current.exists():
            break
    return None


def is_disallowed_frontmatter_character(character: str) -> bool:
    """Reject characters outside the repository's single-line metadata contract."""
    codepoint = ord(character)
    return (
        (codepoint < 0x20 and character not in "\r\n")
        or 0x7F <= codepoint <= 0x9F
        or 0xD800 <= codepoint <= 0xDFFF
        or codepoint in {0x2028, 0x2029}
    )


def discover_skills(
    directory: Path,
    repository_root: Path,
    *,
    require_skills: bool,
) -> tuple[dict[str, Path], list[str]]:
    """Find direct child Skill directories without following managed symlinks."""
    errors: list[str] = []
    skills: dict[str, Path] = {}
    label = display_path(directory, repository_root)

    symlink_component = find_symlink_component(directory, repository_root)
    if symlink_component is not None:
        return {}, [
            f"{display_path(symlink_component, repository_root)}: "
            "managed Skill paths must not contain symlinks"
        ]
    if not directory.exists():
        return {}, [f"{label}: directory does not exist"]
    if not directory.is_dir():
        return {}, [f"{label}: expected a directory"]

    for skill_directory in sorted(directory.iterdir(), key=lambda path: path.name):
        if not skill_directory.is_dir() and not skill_directory.is_symlink():
            continue
        skill_label = display_path(skill_directory, repository_root)
        if skill_directory.is_symlink():
            errors.append(f"{skill_label}: Skill directories must not be symlinks")
            continue

        skill_file = skill_directory / SKILL_FILENAME
        if not skill_file.exists():
            errors.append(f"{skill_label}: missing {SKILL_FILENAME}")
            continue
        if skill_file.is_symlink():
            errors.append(
                f"{display_path(skill_file, repository_root)}: Skill files must not be symlinks"
            )
            continue
        if not skill_file.is_file():
            errors.append(f"{display_path(skill_file, repository_root)}: expected a regular file")
            continue

        skills[skill_directory.name] = skill_file

    if require_skills and not skills:
        errors.append(f"{label}: no {SKILL_FILENAME} files found")

    return skills, errors


def parse_string_scalar(raw_value: str, path: str, line_number: int) -> tuple[str, list[str]]:
    """Parse the single-line YAML string subset used by repository Skill metadata."""
    value = raw_value.strip()
    location = f"{path}:{line_number}"
    if not value:
        return "", [f"{location}: frontmatter values must be non-empty strings"]
    if any(is_disallowed_frontmatter_character(character) for character in raw_value):
        return "", [
            f"{location}: frontmatter values must not contain control or line-separator characters"
        ]

    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as error:
            return "", [f"{location}: invalid double-quoted string: {error.msg}"]
        if not isinstance(parsed, str):
            return "", [f"{location}: frontmatter values must be strings"]
        if any(is_disallowed_frontmatter_character(character) for character in parsed):
            return "", [
                f"{location}: decoded frontmatter values must not contain control or line-separator characters"
            ]
        return parsed, []

    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            return "", [f"{location}: invalid single-quoted string"]
        inner = value[1:-1]
        if "'" in inner.replace("''", ""):
            return "", [f"{location}: escape single quotes as two consecutive quotes"]
        return inner.replace("''", "'"), []

    if (
        value[0] in YAML_PLAIN_FORBIDDEN_START
        or value[0].isdigit()
        or value[0] in "+."
        or re.search(r":(?:\s|$)|\s#", value)
    ):
        return "", [f"{location}: quote values that use YAML indicators or begin like numbers"]

    if value.casefold() in YAML_NON_STRING_SCALARS:
        return "", [f"{location}: quote YAML boolean or null-like values"]

    return value, []


def validate_skill_file(path: Path, skill_name: str, repository_root: Path) -> list[str]:
    """Validate the repository's stricter Skill frontmatter and body contract."""
    label = display_path(path, repository_root)
    try:
        data = path.read_bytes()
    except OSError as error:
        return [f"{label}: cannot read file: {error}"]

    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError as error:
        return [f"{label}: must be UTF-8: {error}"]

    errors: list[str] = []
    if not data.endswith(b"\n"):
        errors.append(f"{label}: file must end with a newline")

    if not content.startswith(("---\n", "---\r\n")):
        return [*errors, f"{label}: YAML frontmatter must start with '---'"]

    frontmatter_match = FRONTMATTER_PATTERN.match(content)
    if frontmatter_match is None:
        return [*errors, f"{label}: YAML frontmatter is missing its closing '---'"]

    frontmatter = frontmatter_match.group("metadata")
    for position, character in enumerate(frontmatter):
        if is_disallowed_frontmatter_character(character):
            line_number = frontmatter.count("\n", 0, position) + 2
            return [
                *errors,
                f"{label}:{line_number}: frontmatter must not contain control or line-separator characters",
            ]

    metadata: dict[str, str] = {}
    for index, line in enumerate(frontmatter.splitlines(), start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1].isspace():
            errors.append(f"{label}:{index}: frontmatter keys and values must each use one line")
            continue
        if ":" not in line:
            errors.append(f"{label}:{index}: expected a 'key: value' frontmatter entry")
            continue

        key, raw_value = line.split(":", 1)
        key = key.strip()
        if not key:
            errors.append(f"{label}:{index}: frontmatter key must not be empty")
            continue
        if key in metadata:
            errors.append(f"{label}:{index}: duplicate frontmatter key '{key}'")
            continue

        value, value_errors = parse_string_scalar(raw_value, label, index)
        errors.extend(value_errors)
        metadata[key] = value

    keys = set(metadata)
    missing_keys = sorted(ALLOWED_FRONTMATTER_KEYS - keys)
    unexpected_keys = sorted(keys - ALLOWED_FRONTMATTER_KEYS)
    if missing_keys:
        errors.append(f"{label}: missing frontmatter key(s): {', '.join(missing_keys)}")
    if unexpected_keys:
        errors.append(
            f"{label}: unexpected frontmatter key(s): {', '.join(unexpected_keys)}; "
            "only name and description are allowed"
        )

    name = metadata.get("name", "").strip()
    if name:
        if len(name) > MAX_SKILL_NAME_LENGTH:
            errors.append(
                f"{label}: name is {len(name)} characters; maximum is {MAX_SKILL_NAME_LENGTH}"
            )
        if not SKILL_NAME_PATTERN.fullmatch(name):
            errors.append(f"{label}: name must use lowercase letters, digits, and single hyphens")
        if name != skill_name:
            errors.append(f"{label}: frontmatter name '{name}' must match directory '{skill_name}'")

    description = metadata.get("description", "").strip()
    if description:
        if len(description) > MAX_DESCRIPTION_LENGTH:
            errors.append(
                f"{label}: description is {len(description)} characters; maximum is "
                f"{MAX_DESCRIPTION_LENGTH}"
            )
        if "<" in description or ">" in description:
            errors.append(f"{label}: description must not contain angle brackets")

    body = content[frontmatter_match.end() :].strip()
    if not body:
        errors.append(f"{label}: Markdown instructions must not be empty")

    return errors


def compare_mirrors(repository_root: Path) -> tuple[int, list[str]]:
    """Check Skill sets, byte equality, and canonical Skill format without writing."""
    source_root = repository_root / SOURCE_DIRECTORY
    source_skills, errors = discover_skills(source_root, repository_root, require_skills=True)
    expected_names = set(source_skills)

    for relative_mirror in MIRROR_DIRECTORIES:
        mirror_root = repository_root / relative_mirror
        mirror_skills, mirror_errors = discover_skills(
            mirror_root, repository_root, require_skills=False
        )
        errors.extend(mirror_errors)
        actual_names = set(mirror_skills)

        missing_names = sorted(expected_names - actual_names)
        extra_names = sorted(actual_names - expected_names)
        if missing_names:
            errors.append(
                f"{relative_mirror.as_posix()}: missing Skill(s): {', '.join(missing_names)}"
            )
        if extra_names:
            errors.append(
                f"{relative_mirror.as_posix()}: source-less Skill(s): "
                f"{', '.join(extra_names)}; remove them explicitly if the canonical Skill was deleted"
            )

        for name in sorted(expected_names & actual_names):
            source = source_skills[name]
            mirror = mirror_skills[name]
            try:
                if source.read_bytes() != mirror.read_bytes():
                    errors.append(
                        f"{display_path(mirror, repository_root)}: differs byte-for-byte from "
                        f"{display_path(source, repository_root)}; run 'make skills-sync'"
                    )
            except OSError as error:
                errors.append(
                    f"{display_path(mirror, repository_root)}: cannot compare file: {error}"
                )

    for name, source in sorted(source_skills.items()):
        errors.extend(validate_skill_file(source, name, repository_root))

    return len(source_skills), errors


def copy_to_mirror(
    source_skills: dict[str, Path], mirror_root: Path, repository_root: Path
) -> tuple[int, int]:
    """Copy changed canonical Skill files to one mirror in byte-preserving mode."""
    symlink_component = find_symlink_component(mirror_root, repository_root)
    if symlink_component is not None:
        raise RuntimeError(
            f"{display_path(symlink_component, repository_root)}: "
            "refusing to write through a symlink"
        )

    copied = 0
    unchanged = 0
    for name, source in sorted(source_skills.items()):
        destination = mirror_root / name / SKILL_FILENAME
        symlink_component = find_symlink_component(destination, repository_root)
        if symlink_component is not None:
            raise RuntimeError(
                f"{display_path(symlink_component, repository_root)}: "
                "refusing to write through a symlink"
            )

        source_bytes = source.read_bytes()
        if destination.is_file() and destination.read_bytes() == source_bytes:
            unchanged += 1
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        copied += 1

    return copied, unchanged


def synchronize(repository_root: Path) -> int:
    """Copy canonical Skills to both mirrors, then run the read-only checks."""
    source_root = repository_root / SOURCE_DIRECTORY
    source_skills, discovery_errors = discover_skills(
        source_root, repository_root, require_skills=True
    )
    if discovery_errors:
        print_errors(discovery_errors)
        return 1

    for relative_mirror in MIRROR_DIRECTORIES:
        mirror_root = repository_root / relative_mirror
        copied, unchanged = copy_to_mirror(source_skills, mirror_root, repository_root)
        print(f"Synced {relative_mirror.as_posix()}: {copied} copied, {unchanged} unchanged")

    skill_count, errors = compare_mirrors(repository_root)
    if errors:
        print_errors(errors)
        return 1

    print(f"Skill synchronization and validation passed ({skill_count} Skills).")
    return 0


def check(repository_root: Path) -> int:
    """Run the non-mutating synchronization and format checks."""
    skill_count, errors = compare_mirrors(repository_root)
    if errors:
        print_errors(errors)
        return 1

    print(f"Skill synchronization and validation passed ({skill_count} Skills).")
    return 0


def print_errors(errors: list[str]) -> None:
    print("Skill synchronization check failed:", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Synchronize and validate shared agent Skill files."
    )
    parser.add_argument("command", choices=("sync", "check"))
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repository_root = args.root.resolve()
    try:
        if args.command == "sync":
            return synchronize(repository_root)
        return check(repository_root)
    except OSError as error:
        print(f"Skill synchronization failed: {error}", file=sys.stderr)
        return 1
    except RuntimeError as error:
        print(f"Skill synchronization failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
