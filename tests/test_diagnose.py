"""Tests for the safe diagnostic tool."""


from scripts.diagnose import print_diagnostics, run_diagnostics


class TestRunDiagnostics:
    def test_brief_output_no_secrets(self, tmp_path):
        diag = run_diagnostics(tmp_path, brief=True)
        assert "python" in diag
        assert "tts_provider" in diag
        assert "git" in diag
        # No secrets in the output
        for k, v in diag.items():
            if isinstance(v, str):
                assert "key" not in v.lower() or "api_key" not in v.lower()

    def test_full_output_keys(self, tmp_path):
        diag = run_diagnostics(tmp_path, brief=False)
        assert "python" in diag
        assert "platform" in diag
        assert "ffmpeg" in diag
        assert "output" in diag
        assert "last_runs" in diag

    def test_history_empty(self, tmp_path):
        diag = run_diagnostics(tmp_path, brief=False)
        assert diag["last_runs"] == []

    def test_history_with_records(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        history = data_dir / "run_history.jsonl"
        history.write_text(
            '{"status":"published","phase":"8","published":true,"story_hash":"abc"}\n'
            '{"status":"dry_run","phase":"8","published":false,"story_hash":"def"}\n'
        )
        diag = run_diagnostics(tmp_path, brief=False)
        runs = diag["last_runs"]
        assert len(runs) == 2
        assert runs[0]["status"] == "published"

    def test_corrupt_history_line(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        history = data_dir / "run_history.jsonl"
        history.write_text('{"status":"ok"}\nBAD LINE\n{"status":"ok2"}\n')
        diag = run_diagnostics(tmp_path, brief=False)
        runs = diag["last_runs"]
        assert len(runs) == 3
        assert runs[1].get("_error") == "corrupt record"


class TestPrintDiagnostics:
    def test_brief_prints_no_crash(self, tmp_path, capsys):
        diag = run_diagnostics(tmp_path, brief=True)
        print_diagnostics(diag, brief=True)
        out = capsys.readouterr().out
        assert "Python" in out or "python" in out

    def test_full_prints_no_crash(self, tmp_path, capsys):
        diag = run_diagnostics(tmp_path, brief=False)
        print_diagnostics(diag, brief=False)
        out = capsys.readouterr().out
        assert "ASMR Pipeline Diagnostics" in out
        assert "Secret" not in out  # no secret leakage

    def test_no_secrets_in_output(self, tmp_path, capsys):
        diag = run_diagnostics(tmp_path, brief=False)
        print_diagnostics(diag, brief=False)
        out = capsys.readouterr().out.lower()
        # Should never contain common secret patterns
        assert "sk-" not in out
        assert "ghp_" not in out
        assert "password" not in out


class TestMain:
    def test_cli_runs_clean(self, tmp_path):
        from scripts.diagnose import main
        ret = main(["--root", str(tmp_path), "--brief"])
        assert ret == 0
