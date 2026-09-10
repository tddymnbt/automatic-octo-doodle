#!/usr/bin/env python3
"""Safe diagnostic tool for the ASMR pipeline.

Prints system info, configuration summary (NO secrets), last history
records, and output artefact sizes. Designed for CI and local debugging.

Usage:
    python scripts/diagnose.py            # print full diagnostics
    python scripts/diagnose.py --brief    # one-liner health check

Exit codes:
    0 - Diagnostics printed successfully (informational; not a health gate)
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _git_info(root: Path) -> dict[str, str]:
    """Return git branch, sha (short), and clean/dirty status."""
    info: dict[str, str] = {}
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(root), capture_output=True, text=True, timeout=5,
        )
        info["branch"] = result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        info["branch"] = "<unknown>"

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root), capture_output=True, text=True, timeout=5,
        )
        info["sha"] = result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        info["sha"] = "<unknown>"

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root), capture_output=True, text=True, timeout=5,
        )
        info["clean"] = "yes" if not result.stdout.strip() else "no"
    except (subprocess.SubprocessError, OSError):
        info["clean"] = "<unknown>"

    return info


def _ffmpeg_info() -> dict[str, str]:
    """Return ffmpeg version and path."""
    info: dict[str, str] = {}
    ffmpeg_path = shutil.which("ffmpeg")
    info["path"] = ffmpeg_path or "<not found>"
    if ffmpeg_path:
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True, text=True, timeout=5,
            )
            first_line = result.stdout.splitlines()[0] if result.stdout else ""
            info["version"] = first_line.split(" ")[2] if len(first_line.split(" ")) > 2 else first_line
        except (subprocess.SubprocessError, OSError):
            info["version"] = "<unknown>"
    else:
        info["version"] = "N/A"
    return info


def _output_summary(root: Path) -> dict[str, str]:
    """Summarise output/ and data/ directory contents and sizes."""
    summary: dict[str, str] = {}

    output_dir = root / "output"
    if output_dir.is_dir():
        files = list(output_dir.iterdir())
        if files:
            total_bytes = sum(f.stat().st_size for f in files if f.is_file())
            summary["output_dir"] = f"{len(files)} files, {total_bytes / 1024:.1f} KB"
        else:
            summary["output_dir"] = "empty"
    else:
        summary["output_dir"] = "<not found>"

    history_path = root / "data" / "run_history.jsonl"
    if history_path.is_file():
        try:
            lines = history_path.read_text().strip().splitlines()
            summary["run_history"] = f"{len(lines)} records"
        except OSError:
            summary["run_history"] = "<unreadable>"
    else:
        summary["run_history"] = "<not found>"

    return summary


def _last_history_records(root: Path, n: int = 5) -> list[dict]:
    """Return the last N run history records (redacted)."""
    history_path = root / "data" / "run_history.jsonl"
    if not history_path.is_file():
        return []
    try:
        lines = history_path.read_text().strip().splitlines()
        records = []
        for line in lines[-n:]:
            try:
                record = json.loads(line)
                # Redact any field whose name looks like a secret
                for key in list(record.keys()):
                    if any(
                        tok in key.lower()
                        for tok in ("token", "key", "secret", "password")
                    ):
                        record[key] = "***"
                records.append(record)
            except json.JSONDecodeError:
                records.append({"_error": "corrupt record"})
        return records
    except OSError:
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_diagnostics(root: Path, *, brief: bool = False) -> dict[str, object]:
    """Run all diagnostics and return a summary dict (never contains secrets)."""
    diag: dict[str, object] = {}

    # System
    diag["python"] = sys.version.split()[0]
    diag["platform"] = f"{platform.system()} {platform.release()}"
    diag["executable"] = sys.executable

    # Git
    diag["git"] = _git_info(root)

    # FFmpeg
    diag["ffmpeg"] = _ffmpeg_info()

    # Config summary (no secrets)
    try:
        from src.config import settings
        config = settings.to_dict()  # always with include_secrets=False
        diag["tts_provider"] = config.get("tts_provider", "<unknown>")
        diag["enable_subtitles"] = config.get("enable_subtitles", None)
    except Exception:
        diag["config"] = "<failed to load>"

    # Output
    diag["output"] = _output_summary(root)

    if brief:
        return diag

    # History (last 5 records, redacted)
    diag["last_runs"] = _last_history_records(root, n=5)

    return diag


def print_diagnostics(diag: dict[str, object], *, brief: bool = False) -> None:
    """Pretty-print diagnostics to stdout."""
    if brief:
        tts = diag.get("tts_provider", "?")
        py = diag.get("python", "?")
        git = diag.get("git", {})
        branch = git.get("branch", "?")
        sha = git.get("sha", "?")
        print(f"Python {py} | {branch}@{sha} | TTS: {tts}")
        return

    print("=== ASMR Pipeline Diagnostics ===\n")

    print(f"Python:       {diag.get('python')}")
    print(f"Platform:     {diag.get('platform')}")
    print(f"Executable:   {diag.get('executable')}")

    git = diag.get("git", {})
    if isinstance(git, dict):
        print(f"\nGit branch:   {git.get('branch')}")
        print(f"Git SHA:      {git.get('sha')}")
        print(f"Clean repo:   {git.get('clean')}")

    ff = diag.get("ffmpeg", {})
    if isinstance(ff, dict):
        print(f"\nFFmpeg:       {ff.get('path')}")
        print(f"FFmpeg ver:   {ff.get('version')}")

    print(f"\nTTS provider: {diag.get('tts_provider')}")
    print(f"Subtitles:    {diag.get('enable_subtitles')}")

    output = diag.get("output", {})
    if isinstance(output, dict):
        print(f"\nOutput dir:   {output.get('output_dir')}")
        print(f"Run history:  {output.get('run_history')}")

    last_runs = diag.get("last_runs", [])
    if last_runs:
        print(f"\n--- Last {len(last_runs)} run(s) ---")
        for rec in last_runs:
            if "_error" in rec:
                print("  <corrupt record>")
            else:
                status = rec.get("status", "?")
                phase = rec.get("phase", "?")
                pub = "published" if rec.get("published") else "dry_run"
                print(f"  {status:10s} | {phase:8s} | {pub}")

    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Print ASMR pipeline diagnostics (no secrets)."
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root (default: current directory)",
    )
    parser.add_argument(
        "--brief",
        action="store_true",
        help="One-liner summary instead of full diagnostics",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    diag = run_diagnostics(root, brief=args.brief)
    print_diagnostics(diag, brief=args.brief)
    return 0


if __name__ == "__main__":
    sys.exit(main())