#!/usr/bin/env python3
"""Validate environment configuration for ASMR Story Shorts.

This script checks that required environment variables and configuration
are present. It NEVER prints or exposes secret values.

Usage:
    python scripts/validate_environment.py

Exit codes:
    0 - All required configuration present
    1 - Missing required configuration
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    pass  # dotenv not installed, rely on system environment

from src.config import settings


def check_secrets() -> tuple[bool, list[str]]:
    """Check if required secrets are present (not their values)."""
    missing = settings.validate_secrets()
    
    # Report presence without revealing values
    for name in ["gemini_api_key", "meta_page_access_token", "meta_page_id"]:
        present = settings.has_secret(name)
        env_name = name.upper()
        if present:
            print(f"  ✓ {env_name}: present")
        else:
            print(f"  ✗ {env_name}: MISSING")
    
    return len(missing) == 0, missing


def check_config() -> tuple[bool, list[str]]:
    """Check if required configuration is valid."""
    issues = settings.validate_config()
    
    # Print configuration status
    config_items = [
        ("AI_MODEL", settings.ai_model),
        ("TTS_MODEL", settings.tts_model),
        ("VIDEO_WIDTH", str(settings.video_width)),
        ("VIDEO_HEIGHT", str(settings.video_height)),
        ("VIDEO_FPS", str(settings.video_fps)),
        ("TARGET_DURATION_SECONDS", str(settings.target_duration_seconds)),
        ("MIN_DURATION_SECONDS", str(settings.min_duration_seconds)),
        ("MAX_DURATION_SECONDS", str(settings.max_duration_seconds)),
        ("DRY_RUN", str(settings.dry_run)),
        ("LOG_LEVEL", settings.log_level),
    ]
    
    for name, value in config_items:
        print(f"  ✓ {name}: {value}")
    
    if issues:
        print()
        print("  Configuration issues:")
        for issue in issues:
            print(f"    ✗ {issue}")
    
    return len(issues) == 0, issues


def check_optional_config() -> None:
    """Display optional configuration status."""
    optional_items = [
        ("STORY_LANGUAGE", settings.story_language),
        ("CONTENT_STYLE", settings.content_style),
        ("TTS_RETRY_COUNT", str(settings.tts_retry_count)),
        ("FACEBOOK_GRAPH_VERSION", settings.facebook_graph_version or "(not set)"),
        ("FACEBOOK_RETRY_COUNT", str(settings.facebook_retry_count)),
        ("MAX_VISUALS_PER_VIDEO", str(settings.max_visuals_per_video)),
        ("ENABLE_AMBIENT_AUDIO", str(settings.enable_ambient_audio)),
        ("ENABLE_SUBTITLES", str(settings.enable_subtitles)),
    ]
    
    for name, value in optional_items:
        print(f"  ℹ {name}: {value}")


def check_gitignore() -> tuple[bool, str | None]:
    """Check if .gitignore properly excludes secrets."""
    gitignore_path = project_root / ".gitignore"
    if not gitignore_path.exists():
        return False, ".gitignore file not found"
    
    content = gitignore_path.read_text()
    issues = []
    
    if ".env" not in content:
        issues.append("Missing .env exclusion pattern")
    
    if issues:
        return False, "; ".join(issues)
    
    return True, None


def check_project_structure() -> tuple[bool, list[str]]:
    """Verify required project structure exists."""
    required_dirs = [
        "src",
        "tests",
        "scripts",
        "assets",
        "data",
    ]
    
    required_files = [
        "src/__init__.py",
        "src/config.py",
        "src/main.py",
        "requirements.txt",
        ".env.example",
        "AGENTS.md",
        "PLAN.md",
    ]
    
    missing = []
    
    for dir_name in required_dirs:
        dir_path = project_root / dir_name
        if not dir_path.exists():
            missing.append(f"Directory: {dir_name}")
        else:
            print(f"  ✓ Directory: {dir_name}")
    
    for file_name in required_files:
        file_path = project_root / file_name
        if not file_path.exists():
            missing.append(f"File: {file_name}")
        else:
            print(f"  ✓ File: {file_name}")
    
    return len(missing) == 0, missing


def check_python_version() -> bool:
    """Verify Python version is adequate."""
    major, minor = sys.version_info[:2]
    ok = major >= 3 and minor >= 10
    status = "✓" if ok else "✗"
    print(f"  {status} Python {major}.{minor} ({'OK' if ok else 'requires 3.10+'})")
    return ok


def check_dependencies() -> tuple[bool, list[str]]:
    """Check if required Python packages are importable."""
    required_packages = [
        "dotenv",  # python-dotenv
        "requests",
        "pydantic",
    ]
    
    missing = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"  ✓ {package}: installed")
        except ImportError:
            print(f"  ✗ {package}: NOT INSTALLED")
            missing.append(package)
    
    return len(missing) == 0, missing


def main() -> int:
    """Run environment validation checks."""
    print("=" * 60)
    print("Environment Validation")
    print("=" * 60)
    print()
    
    # Check Python version
    print("Checking Python version:")
    python_ok = check_python_version()
    print()
    
    # Check project structure
    print("Checking project structure:")
    structure_ok, missing_structure = check_project_structure()
    print()
    
    # Check secrets
    print("Checking required secrets:")
    secrets_ok, missing_secrets = check_secrets()
    print()
    
    # Check configuration
    print("Checking required configuration:")
    config_ok, config_issues = check_config()
    print()
    
    # Check optional configuration
    print("Checking optional configuration:")
    check_optional_config()
    print()
    
    # Check .gitignore
    print("Checking .gitignore:")
    gitignore_ok, gitignore_error = check_gitignore()
    if gitignore_ok:
        print("  ✓ .gitignore properly configured")
    else:
        print(f"  ✗ {gitignore_error}")
    print()
    
    # Check dependencies
    print("Checking Python dependencies:")
    deps_ok, missing_deps = check_dependencies()
    print()
    
    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    
    all_ok = True
    
    if not python_ok:
        all_ok = False
    
    if not structure_ok:
        print(f"✗ Missing structure: {', '.join(missing_structure)}")
        all_ok = False
    
    if not secrets_ok:
        print(f"✗ Missing secrets: {', '.join(missing_secrets)}")
        print("  → Add these to GitHub Actions secrets or .env file")
        all_ok = False
    
    if not config_ok:
        print(f"✗ Configuration issues: {', '.join(config_issues)}")
        all_ok = False
    
    if not gitignore_ok:
        print("✗ .gitignore needs attention")
        all_ok = False
    
    if not deps_ok:
        print(f"✗ Missing dependencies: {', '.join(missing_deps)}")
        print("  → Run: pip install -r requirements.txt")
        all_ok = False
    
    if all_ok:
        print()
        print("✓ All checks passed")
        print("✓ Ready to run pipeline")
        return 0
    else:
        print()
        print("✗ Environment validation failed")
        print("  → Fix issues above before running pipeline")
        return 1


if __name__ == "__main__":
    sys.exit(main())
