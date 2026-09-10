"""Tests for TTS provider."""

import io
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ai.tts_provider import (
    AUDIO_CHANNELS,
    AUDIO_SAMPLE_RATE,
    AUDIO_SAMPLE_WIDTH,
    GeminiTTSError,
    GeminiTTSProvider,
    TTSProvider,
    TTSProviderError,
    create_tts_provider,
)


class TestTTSProviderProtocol:
    """Test TTSProvider protocol definition."""
    
    def test_protocol_exists(self):
        """TTSProvider protocol should exist."""
        assert TTSProvider is not None
    
    def test_gemini_provider_implements_protocol(self):
        """GeminiTTSProvider should implement TTSProvider protocol."""
        # We can't fully instantiate without mocking, but check the class exists
        assert hasattr(GeminiTTSProvider, "synthesize")
        assert hasattr(GeminiTTSProvider, "synthesize_to_file")


class TestGeminiTTSProvider:
    """Test GeminiTTSProvider class."""
    
    def test_default_voice(self):
        """Default voice should be Kore."""
        assert GeminiTTSProvider.DEFAULT_VOICE == "Kore"
    
    def test_asmr_instruction_defined(self):
        """ASMR voice instruction should be defined."""
        assert "calm" in GeminiTTSProvider.ASMR_VOICE_INSTRUCTION.lower()
        assert "asmr" in GeminiTTSProvider.ASMR_VOICE_INSTRUCTION.lower()
    
    def test_get_available_voices(self):
        """Available voices should be returned."""
        provider = GeminiTTSProvider.__new__(GeminiTTSProvider)
        voices = provider.get_available_voices()
        assert "Kore" in voices
        assert len(voices) >= 5


class TestTTSProviderFactory:
    """Test create_tts_provider factory function."""
    
    @patch("src.ai.tts_provider.GeminiClient")
    def test_create_with_defaults_uses_kokoro(self, mock_client):
        """Factory should default to Kokoro provider."""
        from src.ai.kokoro_provider import KokoroTTSProvider
        provider = create_tts_provider()
        assert isinstance(provider, KokoroTTSProvider)
    
    @patch("src.ai.tts_provider.GeminiClient")
    def test_create_gemini_provider(self, mock_client):
        """Factory should create Gemini provider when requested."""
        provider = create_tts_provider(provider="gemini")
        assert isinstance(provider, GeminiTTSProvider)

    @patch("src.ai.tts_provider.GeminiClient")
    def test_create_with_custom_voice_kokoro(self, mock_client):
        """Factory should pass voice to Kokoro provider."""
        from src.ai.kokoro_provider import KokoroTTSProvider
        provider = create_tts_provider(voice="af_nicole")
        assert isinstance(provider, KokoroTTSProvider)
        assert provider._voice == "af_nicole"

    def test_create_unknown_provider_raises(self):
        """Unknown provider name should raise TTSProviderError."""
        with pytest.raises(TTSProviderError, match="Unknown"):
            create_tts_provider(provider="doesnotexist")


class TestPCMToWAV:
    """Test PCM to WAV conversion."""
    
    def test_pcm_to_wav_conversion(self):
        """PCM data should convert to valid WAV."""
        # Create minimal PCM data (1 second of silence)
        pcm_data = b"\x00\x00" * AUDIO_SAMPLE_RATE
        
        provider = GeminiTTSProvider.__new__(GeminiTTSProvider)
        wav_data = provider._pcm_to_wav(pcm_data)
        
        # Should be valid WAV
        assert wav_data[:4] == b"RIFF"
        
        # Should be parseable as WAV
        with wave.open(io.BytesIO(wav_data), "rb") as wf:
            assert wf.getnchannels() == AUDIO_CHANNELS
            assert wf.getsampwidth() == AUDIO_SAMPLE_WIDTH
            assert wf.getframerate() == AUDIO_SAMPLE_RATE
    
    def test_pcm_to_wav_empty_data(self):
        """Empty PCM data should produce valid WAV header."""
        provider = GeminiTTSProvider.__new__(GeminiTTSProvider)
        wav_data = provider._pcm_to_wav(b"")
        
        # Should still have WAV header
        assert wav_data[:4] == b"RIFF"


class TestTTSProviderErrorHandling:
    """Test TTS error handling."""
    
    def test_empty_text_raises_error(self):
        """Empty text should raise GeminiTTSError."""
        with patch("src.ai.tts_provider.GeminiClient"):
            provider = GeminiTTSProvider()
        
        with pytest.raises(GeminiTTSError, match="empty"):
            provider.synthesize("")
    
    def test_whitespace_only_text_raises_error(self):
        """Whitespace-only text should raise GeminiTTSError."""
        with patch("src.ai.tts_provider.GeminiClient"):
            provider = GeminiTTSProvider()
        
        with pytest.raises(GeminiTTSError, match="empty"):
            provider.synthesize("   ")
    
    def test_error_hierarchy(self):
        """GeminiTTSError should inherit from TTSProviderError."""
        assert issubclass(GeminiTTSError, TTSProviderError)
        assert issubclass(TTSProviderError, Exception)


class TestTTSProviderIntegration:
    """Integration tests for TTS provider (mocked API)."""
    
    def test_synthesize_calls_api(self, tmp_path):
        """Synthesize should call Gemini API."""
        # Mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        
        # Create mock audio data (1 second of silence)
        pcm_data = b"\x00\x00" * AUDIO_SAMPLE_RATE
        import base64
        audio_b64 = base64.b64encode(pcm_data).decode()
        
        mock_part = MagicMock()
        mock_part.inline_data.data = audio_b64
        mock_response.candidates = [MagicMock(content=MagicMock(parts=[mock_part]))]
        mock_client._client.models.generate_content.return_value = mock_response
        
        provider = GeminiTTSProvider(client=mock_client)
        
        wav_data = provider.synthesize("Hello world, this is a test.")
        
        # Should return WAV data
        assert wav_data[:4] == b"RIFF"
        
        # Should have called API
        mock_client._client.models.generate_content.assert_called_once()
    
    def test_synthesize_to_file(self, tmp_path):
        """Synthesize to file should save WAV file."""
        # Mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        
        pcm_data = b"\x00\x00" * AUDIO_SAMPLE_RATE
        import base64
        audio_b64 = base64.b64encode(pcm_data).decode()
        
        mock_part = MagicMock()
        mock_part.inline_data.data = audio_b64
        mock_response.candidates = [MagicMock(content=MagicMock(parts=[mock_part]))]
        mock_client._client.models.generate_content.return_value = mock_response
        
        provider = GeminiTTSProvider(client=mock_client)
        
        output_file = tmp_path / "test_audio.wav"
        result = provider.synthesize_to_file("Hello world", output_file)
        
        # Should return path
        assert result == output_file
        
        # File should exist and be valid WAV
        assert output_file.exists()
        assert output_file.read_bytes()[:4] == b"RIFF"
    
    def test_voice_instruction_used(self):
        """Custom voice instruction should be passed to API."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        
        pcm_data = b"\x00\x00" * 100
        import base64
        audio_b64 = base64.b64encode(pcm_data).decode()
        
        mock_part = MagicMock()
        mock_part.inline_data.data = audio_b64
        mock_response.candidates = [MagicMock(content=MagicMock(parts=[mock_part]))]
        mock_client._client.models.generate_content.return_value = mock_response
        
        provider = GeminiTTSProvider(client=mock_client, voice="Fenrir")
        
        provider.synthesize("Test", voice_instruction="Speak softly")
        
        # Check call args include voice instruction
        call_args = mock_client._client.models.generate_content.call_args
        contents = call_args.kwargs.get("contents", call_args[1].get("contents", ""))
        assert "Speak softly" in contents


class TestSynthesizeToFilePath:
    """Test synthesize_to_file path handling."""
    
    def test_creates_parent_directories(self, tmp_path):
        """Should create parent directories if they don't exist."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        
        pcm_data = b"\x00\x00" * 100
        import base64
        audio_b64 = base64.b64encode(pcm_data).decode()
        
        mock_part = MagicMock()
        mock_part.inline_data.data = audio_b64
        mock_response.candidates = [MagicMock(content=MagicMock(parts=[mock_part]))]
        mock_client._client.models.generate_content.return_value = mock_response
        
        provider = GeminiTTSProvider(client=mock_client)
        
        nested_path = tmp_path / "deep" / "nested" / "audio.wav"
        result = provider.synthesize_to_file("Test", nested_path)
        
        assert result.exists()
    
    def test_accepts_string_path(self, tmp_path):
        """Should accept string path as well as Path object."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        
        pcm_data = b"\x00\x00" * 100
        import base64
        audio_b64 = base64.b64encode(pcm_data).decode()
        
        mock_part = MagicMock()
        mock_part.inline_data.data = audio_b64
        mock_response.candidates = [MagicMock(content=MagicMock(parts=[mock_part]))]
        mock_client._client.models.generate_content.return_value = mock_response
        
        provider = GeminiTTSProvider(client=mock_client)
        
        string_path = str(tmp_path / "audio.wav")
        result = provider.synthesize_to_file("Test", string_path)
        
        assert isinstance(result, Path)
        assert result.exists()
