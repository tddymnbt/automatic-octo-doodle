"""Tests for subtitle generator."""

import re

from src.video.subtitles import SubtitleEntry, SubtitleGenerator


class TestSubtitleEntry:
    """Test SubtitleEntry dataclass."""
    
    def test_to_srt_time_hours(self):
        """Should format time with hours correctly."""
        entry = SubtitleEntry(index=1, start_seconds=3661.5, end_seconds=3665.0, text="Test")
        result = entry.to_srt_time(3661.5)
        assert result == "01:01:01,500"
    
    def test_to_srt_time_minutes(self):
        """Should format time with minutes correctly."""
        entry = SubtitleEntry(index=1, start_seconds=65.5, end_seconds=70.0, text="Test")
        result = entry.to_srt_time(65.5)
        assert result == "00:01:05,500"
    
    def test_to_srt_time_seconds(self):
        """Should format time with seconds correctly."""
        entry = SubtitleEntry(index=1, start_seconds=5.5, end_seconds=10.0, text="Test")
        result = entry.to_srt_time(5.5)
        assert result == "00:00:05,500"
    
    def test_to_srt_time_zero(self):
        """Should format zero time correctly."""
        entry = SubtitleEntry(index=1, start_seconds=0, end_seconds=1.0, text="Test")
        result = entry.to_srt_time(0)
        assert result == "00:00:00,000"
    
    def test_to_srt_format(self):
        """Should format entry as SRT correctly."""
        entry = SubtitleEntry(index=1, start_seconds=0, end_seconds=2.5, text="Hello world")
        srt = entry.to_srt()
        
        assert "1\n" in srt
        assert "00:00:00,000 --> 00:00:02,500" in srt
        assert "Hello world" in srt
    
    def test_to_srt_multiline(self):
        """Should handle multiline text."""
        entry = SubtitleEntry(
            index=2,
            start_seconds=3.0,
            end_seconds=5.5,
            text="Line one\nLine two"
        )
        srt = entry.to_srt()
        
        assert "2\n" in srt
        assert "00:00:03,000 --> 00:00:05,500" in srt
        assert "Line one\nLine two" in srt


class TestSubtitleGenerator:
    """Test SubtitleGenerator class."""
    
    def test_default_settings(self):
        """Default settings should be reasonable."""
        gen = SubtitleGenerator()
        assert gen._wpm == 150
        assert gen._max_words_per_line == 8
        assert gen._max_lines == 2
        assert gen._min_duration == 1.0
        assert gen._max_duration == 5.0
    
    def test_generate_empty_text(self):
        """Should return empty list for empty text."""
        gen = SubtitleGenerator()
        entries = gen.generate("")
        assert entries == []
    
    def test_generate_whitespace_only(self):
        """Should return empty list for whitespace-only text."""
        gen = SubtitleGenerator()
        entries = gen.generate("   \n  ")
        assert entries == []
    
    def test_generate_simple_text(self):
        """Should generate subtitles for simple text."""
        gen = SubtitleGenerator()
        entries = gen.generate("Hello world. This is a test.")
        
        assert len(entries) >= 1
        assert entries[0].index == 1
        # Text is split by sentences, so first entry is just first sentence
        assert entries[0].text == "Hello world."
    
    def test_generate_long_text(self):
        """Should split long text into multiple entries."""
        gen = SubtitleGenerator(max_words_per_line=5, max_lines=1)
        long_text = "This is a very long sentence that should be split into multiple subtitles for better readability."
        entries = gen.generate(long_text)
        
        assert len(entries) > 1
    
    def test_generate_timing_starts_at_zero(self):
        """First entry should start at time 0."""
        gen = SubtitleGenerator()
        entries = gen.generate("Hello world.")
        
        assert entries[0].start_seconds == 0.0
    
    def test_generate_timing_monotonic(self):
        """Timing should be monotonically increasing."""
        gen = SubtitleGenerator()
        text = "First sentence. Second sentence. Third sentence."
        entries = gen.generate(text)
        
        for i in range(1, len(entries)):
            assert entries[i].start_seconds >= entries[i-1].end_seconds
    
    def test_generate_with_total_duration(self):
        """Should normalize timing when total duration provided."""
        gen = SubtitleGenerator()
        text = "First sentence. Second sentence."
        entries = gen.generate(text, total_duration=10.0)
        
        if entries:
            assert entries[-1].end_seconds <= 10.1  # Small tolerance
    
    def test_generate_srt_format(self):
        """Should generate valid SRT format."""
        gen = SubtitleGenerator()
        text = "Hello world."
        srt = gen.generate_srt(text)
        
        # Check SRT structure
        assert re.match(r"1\n\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\nHello world\.\n", srt)
    
    def test_generate_srt_multiple_entries(self):
        """Should generate multiple SRT entries."""
        gen = SubtitleGenerator(max_words_per_line=3, max_lines=1)
        text = "First sentence. Second sentence. Third sentence."
        srt = gen.generate_srt(text)
        
        # Should have multiple numbered entries
        assert "1\n" in srt
        assert "2\n" in srt
    
    def test_save_srt_creates_file(self, tmp_path):
        """Should save SRT file correctly."""
        gen = SubtitleGenerator()
        output = tmp_path / "test.srt"
        
        result = gen.save_srt("Hello world.", output)
        
        assert result.exists()
        assert "Hello world." in result.read_text()
    
    def test_save_srt_creates_parent_dirs(self, tmp_path):
        """Should create parent directories."""
        gen = SubtitleGenerator()
        output = tmp_path / "subtitles" / "deep" / "test.srt"
        
        gen.save_srt("Hello.", output)
        
        assert output.exists()


class TestTextProcessing:
    """Test text processing methods."""
    
    def test_clean_text_normalizes_whitespace(self):
        """Should normalize whitespace."""
        gen = SubtitleGenerator()
        result = gen._clean_text("Hello   world\n\nThis  is  a   test.")
        assert "  " not in result
        assert "\n" not in result
    
    def test_clean_text_normalizes_punctuation(self):
        """Should normalize excessive punctuation."""
        gen = SubtitleGenerator()
        result = gen._clean_text("Hello!!! Really??? Okay.....")
        assert "!!" not in result
        assert "???" not in result
        assert "...." not in result
    
    def test_split_sentences(self):
        """Should split text into sentences."""
        gen = SubtitleGenerator()
        sentences = gen._split_sentences("First sentence. Second sentence! Third?")
        
        assert len(sentences) == 3
        assert sentences[0] == "First sentence."
        assert sentences[1] == "Second sentence!"
        assert sentences[2] == "Third?"
    
    def test_split_sentences_with_ellipsis(self):
        """Should handle ellipsis correctly."""
        gen = SubtitleGenerator()
        sentences = gen._split_sentences("First... Second...")
        
        assert len(sentences) == 2
    
    def test_split_into_chunks_short(self):
        """Short sentences should remain as single chunks."""
        gen = SubtitleGenerator(max_words_per_line=10)
        chunks = gen._split_into_chunks(["Short sentence."])
        
        assert len(chunks) == 1
        assert chunks[0] == "Short sentence."
    
    def test_split_into_chunks_long(self):
        """Long sentences should be split."""
        gen = SubtitleGenerator(max_words_per_line=3, max_lines=1)
        long_sentence = "This is a very long sentence with many words in it"
        chunks = gen._split_into_chunks([long_sentence])
        
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.split()) <= 3


class TestTimingCalculation:
    """Test timing calculation."""
    
    def test_timing_proportional_to_words(self):
        """More words should mean more time."""
        gen = SubtitleGenerator()
        short_chunks = ["Hello."]
        long_chunks = ["This is a longer sentence with more words."]
        
        short_entries = gen._calculate_timing(short_chunks)
        long_entries = gen._calculate_timing(long_chunks)
        
        if short_entries and long_entries:
            short_duration = short_entries[-1].end_seconds
            long_duration = long_entries[-1].end_seconds
            assert long_duration > short_duration
    
    def test_timing_respects_min_duration(self):
        """Should respect minimum duration."""
        gen = SubtitleGenerator(min_duration=2.0)
        entries = gen._calculate_timing(["Hi."])
        
        if entries:
            duration = entries[0].end_seconds - entries[0].start_seconds
            assert duration >= 2.0
    
    def test_timing_respects_max_duration(self):
        """Should respect maximum duration."""
        gen = SubtitleGenerator(max_duration=3.0, min_duration=0.5)
        long_text = "This is a very long sentence with many words that should be constrained."
        chunks = [long_text]
        entries = gen._calculate_timing(chunks)
        
        if entries:
            duration = entries[0].end_seconds - entries[0].start_seconds
            assert duration <= 3.0 + 0.1  # Small tolerance
    
    def test_timing_with_explicit_duration(self):
        """Should use explicit total duration when provided."""
        gen = SubtitleGenerator()
        chunks = ["First.", "Second.", "Third."]
        entries = gen._calculate_timing(chunks, total_duration=9.0)
        
        if entries:
            # Should fit within 9 seconds
            assert entries[-1].end_seconds <= 9.1


class TestEdgeCases:
    """Test edge cases."""
    
    def test_single_word(self):
        """Should handle single word."""
        gen = SubtitleGenerator()
        entries = gen.generate("Hello")
        
        assert len(entries) == 1
        assert entries[0].text == "Hello"
    
    def test_punctuation_only(self):
        """Should handle punctuation-heavy text."""
        gen = SubtitleGenerator()
        entries = gen.generate("... --- ...")
        
        # Should still generate something
        assert len(entries) >= 1
    
    def test_unicode_text(self):
        """Should handle unicode text."""
        gen = SubtitleGenerator()
        entries = gen.generate("Héllo wörld. Tëst.")
        
        assert len(entries) >= 1
        assert "Héllo" in entries[0].text
    
    def test_multiple_newlines(self):
        """Should handle multiple newlines."""
        gen = SubtitleGenerator()
        entries = gen.generate("First.\n\n\nSecond.")
        
        assert len(entries) >= 2


class TestFactory:
    """Test factory function."""
    
    def test_create_generator(self):
        """Factory should create generator."""
        gen = SubtitleGenerator()
        assert isinstance(gen, SubtitleGenerator)
    
    def test_create_with_custom_settings(self):
        """Factory should accept custom settings."""
        gen = SubtitleGenerator(words_per_minute=120)
        assert gen._wpm == 120
