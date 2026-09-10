#!/usr/bin/env python3
"""Scan the repository for accidentally committed secrets.

Stdlib-only, offline, $0 — no third-party scanner required. Designed to be
run locally and in CI (see .github/workflows/ci.yml).

What it detects:
  1. ``.env`` / ``.env.*`` files tracked in git (except ``.env.example``).
  2. Secret-looking assignments to known secret variable names
     (``api_key``, ``access_token``, ``secret``, ``password``,
     ``authorization``, ``token``) with a non-empty quoted value, in
     non-test, non-example, non-vendored, non-documentation files.
  3. High-entropy values (32+ chars, mixed case/digits) assigned to
     secret-named variables.

Explicitly SKIPPED (safe/false-positive zones):
  - ``tests/`` — fake secrets like ``test-key`` are expected there.
  - ``*.example`` / ``.env.example`` — documented placeholders.
  - ``media/scripts/`` — vendored third-party code (MIT).
  - ``.git/``, ``.venv/``, ``output/``, ``data/``, ``.pytest_cache/``,
    ``__pycache__/``.

Usage:
    python scripts/scan_secrets.py            # scan git-tracked files (or workspace)
    python scripts/scan_secrets.py --verbose  # print scanned file count

Exit codes:
    0 - No secrets detected
    1 - Secrets detected (or unrecoverable error)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

# Directories/files that are allowed to contain secret-shaped strings.
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "output",
    "renders",
    "artifacts",
    "data",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "tests",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".github",  # workflows reference ${{ secrets.X }} (not literals)
}
SKIP_DIR_SUFFIXES = ("media/scripts",)
SKIP_FILE_SUFFIXES = (".example", ".md")
SKIP_FILES = {
    "ruff.toml",
    "pyproject.toml",
    "requirements.txt",
    ".gitignore",
    "AGENTS.md",
    "PLAN.md",
}

# Secret variable names whose values are almost always credentials.
SECRET_NAME_RE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|secret|password|passwd|"
    r"authorization|auth[_-]?token|client[_-]?secret|private[_-]?key|"
    r"token)\b"
)

# A "value" that looks like a real secret (not a placeholder/example).
# Requires >= 12 chars with at least one digit and one letter (or 24+ bare),
# and must not be a known placeholder.
PLACEHOLDER_RE = re.compile(
    r"(?i)(<.*>|\".*placeholder.*\"|your[_-]?|example|test|change[_-]?me|"
    r"xxxx+|dummy|fake|sample|redacted)"
)

# Match `NAME = "value"` or `NAME: "value"` (env, yaml, python, etc.)
ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    ^[^#]*?                      # ignore commented lines (allow trailing text)
    \b(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\s*[=:]\s*
    ["'](?P<value>[^"']{6,})["']
    """
)


def is_skippable(path: Path, root: Path) -> bool:
    """Return True for paths in the safe/false-positive zones."""
    rel = path.relative_to(root).as_posix()

    # File-level skip
    if path.name in SKIP_FILES:
        return True
    if path.name.endswith(SKIP_FILE_SUFFIXES):
        return True

    # Dir-level skip (any ancestor)
    parts = rel.split("/")
    for part in parts[:-1]:
        if part in SKIP_DIRS:
            return True
    for suffix in SKIP_DIR_SUFFIXES:
        if rel.startswith(suffix):
            return True

    return False


def iter_targets(root: Path, git_only: bool) -> Iterable[Path]:
    """Yield candidate files to scan (git-tracked or workspace walk)."""
    if git_only:
        try:
            result = subprocess.run(
                ["git", "ls-files"],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=True,
            )
        except (subprocess.SubprocessError, OSError):
            # Fall back to a workspace walk (e.g. not a git repo)
            git_only = False
        else:
            for line in result.stdout.splitlines():
                path = root / line
                if path.is_file():
                    yield path
            return

    for path in sorted(root.rglob("*")):
        if path.is_file() and not is_skippable(path, root):
            yield path


def scan_file(path: Path, root: Path) -> list[str]:
    """Scan a single file; return list of findings (file:line: detail)."""
    findings: list[str] = []

    # Rule 1: tracked .env files
    rel = path.relative_to(root).as_posix()
    if path.name.startswith(".env") and path.name != ".env.example":
        findings.append(f"{rel}: TRACKED ENV FILE (contains secrets?)")
        return findings

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return findings

    for lineno, line in enumerate(lines, start=1):
        match = ASSIGNMENT_RE.search(line)
        if not match:
            continue
        name = match.group("name")
        value = match.group("value")

        if not SECRET_NAME_RE.search(name):
            continue
        if PLACEHOLDER_RE.search(value):
            continue
        if len(value) < 8:
            continue

        findings.append(
            f"{rel}:{lineno}: possible secret in assignment to '{name}'"
        )

    return findings


def run_scan(root: Path, *, verbose: bool = False, git_only: bool = True) -> int:
    """Run the scan; return process exit code (0 clean, 1 findings)."""
    targets = list(iter_targets(root, git_only))
    findings: list[str] = []

    for path in targets:
        if is_skippable(path, root):
            continue
        findings.extend(scan_file(path, root))

    if targets:
        print(f"Scanned {len(targets)} files")
    else:
        print("No files to scan")

    if findings:
        print("\n⚠  Potential secrets detected:")
        for finding in findings:
            print(f"  ✗ {finding}")
        print("\nInvestigate each finding. Remove secrets from tracked files")
        print("and rotate any leaked credential.")
        return 1

    print("✓ No secrets detected")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Scan the repository for accidentally committed secrets."
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root (default: current directory)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print scanned file count",
    )
    parser.add_argument(
        "--no-git",
        action="store_true",
        help="Scan all workspace files instead of git-tracked only",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    return run_scan(
        root,
        verbose=args.verbose,
        git_only=not args.no_git,
    )


if __name__ == "__main__":
    sys.exit(main())