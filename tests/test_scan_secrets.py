"""Tests for the secret scanner."""

from pathlib import Path

from scripts.scan_secrets import (
    is_skippable,
    run_scan,
    scan_file,
)


def _make_repo(tmp_path: Path) -> Path:
    """Create a minimal repo-like tree."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "scripts").mkdir()
    return tmp_path


class TestScanFile:
    def _write(self, tmp_path: Path, rel: str, content: str) -> Path:
        """Write a file, creating parent dirs."""
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p

    def test_clean_file(self, tmp_path):
        f = self._write(tmp_path, "src/clean.py", 'NAME = "value"\nMAX = 5\n')
        assert scan_file(f, tmp_path) == []

    def test_tracked_env_file_detected(self, tmp_path):
        f = self._write(tmp_path, ".env", "GEMINI_API_KEY=abc\n")
        findings = scan_file(f, tmp_path)
        assert len(findings) == 1
        assert "TRACKED ENV FILE" in findings[0]

    def test_env_example_allowed(self, tmp_path):
        f = self._write(tmp_path, ".env.example", "GEMINI_API_KEY=\n")
        assert scan_file(f, tmp_path) == []

    def test_secret_assignment_detected(self, tmp_path):
        f = self._write(
            tmp_path,
            "src/config.py",
            'META_ACCESS_TOKEN = "1234567890abcdefghijk"\n',
        )
        findings = scan_file(f, tmp_path)
        assert len(findings) == 1
        assert "possible secret" in findings[0]

    def test_placeholder_allowed(self, tmp_path):
        f = self._write(
            tmp_path, "src/config.py", 'GEMINI_API_KEY = "your-api-key-here"\n'
        )
        assert scan_file(f, tmp_path) == []

    def test_test_file_excluded_by_skip(self, tmp_path):
        f = self._write(
            tmp_path, "tests/test_x.py", 'API_KEY = "fake-test-key-123"\n'
        )
        root = tmp_path
        assert is_skippable(f, root) is True

    def test_short_value_ignored(self, tmp_path):
        f = self._write(tmp_path, "src/config.py", 'TOKEN = "short"\n')
        assert scan_file(f, tmp_path) == []


class TestIsSkippable:
    def test_media_scripts_vendored(self, tmp_path):
        f = tmp_path / "media" / "scripts" / "probe.py"
        f.parent.mkdir(parents=True)
        assert is_skippable(f, tmp_path) is True

    def test_output_dir_skipped(self, tmp_path):
        f = tmp_path / "output" / "final.mp4"
        f.parent.mkdir(parents=True)
        assert is_skippable(f, tmp_path) is True

    def test_markdown_skipped(self, tmp_path):
        f = tmp_path / "README.md"
        assert is_skippable(f, tmp_path) is True


class TestRunScan:
    def test_clean_repo_exit_0(self, tmp_path):
        _make_repo(tmp_path)
        (tmp_path / "src" / "main.py").write_text('x = "hello"\n')
        assert run_scan(tmp_path, git_only=False) == 0

    def test_planted_secret_exit_1(self, tmp_path):
        _make_repo(tmp_path)
        (tmp_path / "src" / "config.py").write_text(
            'META_PAGE_ACCESS_TOKEN = "super-secret-token-1234567890"\n'
        )
        assert run_scan(tmp_path, git_only=False) == 1

    def test_env_file_exit_1(self, tmp_path):
        _make_repo(tmp_path)
        (tmp_path / ".env").write_text("GEMINI_API_KEY=abc123\n")
        assert run_scan(tmp_path, git_only=False) == 1

    def test_skipped_dirs_do_not_trigger(self, tmp_path):
        _make_repo(tmp_path)
        (tmp_path / "media" / "scripts").mkdir(parents=True)
        (tmp_path / "media" / "scripts" / "x.py").write_text(
            'ACCESS_TOKEN = "some-token-value-1234567890"\n'
        )
        (tmp_path / "tests" / "test_y.py").write_text(
            'ACCESS_TOKEN = "fake-token-123"\n'
        )
        assert run_scan(tmp_path, git_only=False) == 0