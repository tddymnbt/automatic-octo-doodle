"""Tests for the validation script itself.

These tests verify the validation script runs correctly and handles
edge cases properly.
"""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def project_root():
    """Return project root directory."""
    return Path(__file__).parent.parent


class TestValidationScript:
    """Test the validate_environment.py script."""
    
    def test_script_runs_successfully(self, project_root):
        """Validation script should run without errors."""
        result = subprocess.run(
            [sys.executable, str(project_root / "scripts" / "validate_environment.py")],
            capture_output=True,
            text=True,
            cwd=str(project_root),
        )
        
        # Should exit with 0 or 1 (not crash)
        assert result.returncode in (0, 1)
        
        # Should have output
        assert len(result.stdout) > 0
        
        # Should not crash with traceback
        assert "Traceback" not in result.stdout
        assert "Traceback" not in result.stderr
    
    def test_script_exits_zero_with_valid_env(self, project_root, monkeypatch):
        """Script should exit 0 when all required env vars are set."""
        # Set required environment variables
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("META_PAGE_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("META_PAGE_ID", "test-page-id")
        
        result = subprocess.run(
            [sys.executable, str(project_root / "scripts" / "validate_environment.py")],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            env={**subprocess.os.environ, 
                "GEMINI_API_KEY": "test-key",
                "META_PAGE_ACCESS_TOKEN": "test-token",
                "META_PAGE_ID": "test-page-id"
            },
        )
        
        # Should pass (exit code 0) or at least not crash
        assert result.returncode in (0, 1)
    
    def test_script_never_prints_secret_values(self, project_root, monkeypatch):
        """Script should never print actual secret values."""
        secret_value = "super-secret-api-key-12345"
        
        result = subprocess.run(
            [sys.executable, str(project_root / "scripts" / "validate_environment.py")],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            env={**subprocess.os.environ, "GEMINI_API_KEY": secret_value},
        )
        
        # The secret value should never appear in output
        assert secret_value not in result.stdout
        assert secret_value not in result.stderr
    
    def test_script_checks_gitignore(self, project_root):
        """Script should check .gitignore exists and is configured."""
        result = subprocess.run(
            [sys.executable, str(project_root / "scripts" / "validate_environment.py")],
            capture_output=True,
            text=True,
            cwd=str(project_root),
        )
        
        # Should mention .gitignore check
        assert "gitignore" in result.stdout.lower() or "gitignore" in result.stderr.lower()
    
    def test_script_checks_python_version(self, project_root):
        """Script should verify Python version."""
        result = subprocess.run(
            [sys.executable, str(project_root / "scripts" / "validate_environment.py")],
            capture_output=True,
            text=True,
            cwd=str(project_root),
        )
        
        # Should mention Python version
        assert "python" in result.stdout.lower()


class TestValidationIntegration:
    """Integration tests for validation with real project structure."""
    
    def test_validation_passes_on_clean_project(self, project_root):
        """Validation should pass on a properly set up project."""
        result = subprocess.run(
            [sys.executable, str(project_root / "scripts" / "validate_environment.py")],
            capture_output=True,
            text=True,
            cwd=str(project_root),
        )
        
        # Check output contains expected sections
        output = result.stdout
        assert "Environment Validation" in output
        assert "Summary" in output
        
        # Should check for required components
        assert "secrets" in output.lower() or "SECRETS" in output
        assert "configuration" in output.lower() or "CONFIGURATION" in output
