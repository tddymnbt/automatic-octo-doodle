"""Subtitle generator for ASMR story videos.

This module generates SRT subtitle files from narration text.
It handles:
- Text chunking for readability
- Timing estimation based on speaking rate
- SRT format output
- Mobile-friendly line lengths
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SubtitleEntry:
    """A single subtitle entry."""
    
    index: int
    start_seconds: float
    end_seconds: float
    text: str
    
    def to_srt_time(self, seconds: float) -> str:
        """Convert seconds to SRT time format (HH:MM:SS,mmm).
        
        Args:
            seconds: Time in seconds
            
        Returns:
            SRT formatted time string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    def to_srt(self) -> str:
        """Convert entry to SRT format string.
        
        Returns:
            SRT formatted string for this entry
        """
        start = self.to_srt_time(self.start_seconds)
        end = self.to_srt_time(self.end_seconds)
        return f"{self.index}\n{start} --> {end}\n{self.text}\n"


class SubtitleGenerator:
    """Generates SRT subtitles from narration text.
    
    This generator:
    1. Splits narration into readable chunks
    2. Estimates timing based on speaking rate
    3. Generates properly formatted SRT output
    """
    
    # Default settings for ASMR subtitles
    DEFAULT_WORDS_PER_MINUTE = 150  # Slow for ASMR
    DEFAULT_MAX_WORDS_PER_LINE = 8  # Mobile-friendly
    DEFAULT_MAX_LINES = 2  # Two lines max per subtitle
    DEFAULT_MIN_DURATION = 1.0  # Minimum seconds per subtitle
    DEFAULT_MAX_DURATION = 5.0  # Maximum seconds per subtitle
    DEFAULT_PADDING = 0.1  # Padding between subtitles
    
    def __init__(
        self,
        words_per_minute: int = DEFAULT_WORDS_PER_MINUTE,
        max_words_per_line: int = DEFAULT_MAX_WORDS_PER_LINE,
        max_lines: int = DEFAULT_MAX_LINES,
        min_duration: float = DEFAULT_MIN_DURATION,
        max_duration: float = DEFAULT_MAX_DURATION,
        padding: float = DEFAULT_PADDING,
    ) -> None:
        """Initialize the subtitle generator.
        
        Args:
            words_per_minute: Speaking rate for timing
            max_words_per_line: Max words per subtitle line
            max_lines: Max lines per subtitle
            min_duration: Minimum seconds per subtitle
            max_duration: Maximum seconds per subtitle
            padding: Padding between subtitles in seconds
        """
        self._wpm = words_per_minute
        self._max_words_per_line = max_words_per_line
        self._max_lines = max_lines
        self._min_duration = min_duration
        self._max_duration = max_duration
        self._padding = padding
        
        logger.info(f"Subtitle generator initialized: {words_per_minute} WPM")
    
    def generate(self, narration: str, total_duration: float | None = None) -> list[SubtitleEntry]:
        """Generate subtitle entries from narration text.
        
        Args:
            narration: Full narration text
            total_duration: Optional total duration override
            
        Returns:
            List of SubtitleEntry objects
        """
        if not narration or not narration.strip():
            return []
        
        # Clean narration
        clean_text = self._clean_text(narration)
        
        # Split into sentences
        sentences = self._split_sentences(clean_text)
        
        # Split sentences into subtitle chunks
        chunks = self._split_into_chunks(sentences)
        
        # Calculate timing
        entries = self._calculate_timing(chunks, total_duration)
        
        logger.info(f"Generated {len(entries)} subtitle entries")
        return entries
    
    def generate_srt(self, narration: str, total_duration: float | None = None) -> str:
        """Generate SRT format string from narration.
        
        Args:
            narration: Full narration text
            total_duration: Optional total duration override
            
        Returns:
            SRT formatted string
        """
        entries = self.generate(narration, total_duration)
        return self._entries_to_srt(entries)
    
    def save_srt(
        self,
        narration: str,
        output_path: Path | str,
        total_duration: float | None = None,
    ) -> Path:
        """Generate and save SRT file.
        
        Args:
            narration: Full narration text
            output_path: Path to save SRT file
            total_duration: Optional total duration override
            
        Returns:
            Path to saved SRT file
        """
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        
        srt_content = self.generate_srt(narration, total_duration)
        output.write_text(srt_content, encoding="utf-8")
        
        logger.info(f"SRT saved to: {output}")
        return output
    
    def _clean_text(self, text: str) -> str:
        """Clean text for subtitle generation.
        
        Args:
            text: Raw text
            
        Returns:
            Cleaned text
        """
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()
        
        # Remove excessive punctuation
        text = re.sub(r"[.]{2,}", "...", text)
        text = re.sub(r"[!]{2,}", "!", text)
        text = re.sub(r"[?]{2,}", "?", text)
        
        return text
    
    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences.
        
        Args:
            text: Cleaned text
            
        Returns:
            List of sentences
        """
        # Split on sentence boundaries
        # Handle: . ! ? ... and line breaks
        sentences = re.split(r"(?<=[.!?])\s+|(?<=\.\.\.)\s+|\n+", text)
        
        # Filter empty sentences
        return [s.strip() for s in sentences if s.strip()]
    
    def _split_into_chunks(self, sentences: list[str]) -> list[str]:
        """Split sentences into subtitle-sized chunks.
        
        Args:
            sentences: List of sentences
            
        Returns:
            List of text chunks for subtitles
        """
        chunks = []
        
        for sentence in sentences:
            words = sentence.split()
            
            if len(words) <= self._max_words_per_line * self._max_lines:
                # Sentence fits in one subtitle
                chunks.append(sentence)
            else:
                # Split sentence into multiple subtitles
                current_chunk = []
                for word in words:
                    current_chunk.append(word)
                    if len(current_chunk) >= self._max_words_per_line * self._max_lines:
                        chunks.append(" ".join(current_chunk))
                        current_chunk = []
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
        
        return chunks
    
    def _calculate_timing(
        self,
        chunks: list[str],
        total_duration: float | None = None,
    ) -> list[SubtitleEntry]:
        """Calculate timing for each subtitle chunk.
        
        Args:
            chunks: List of text chunks
            total_duration: Optional total duration override
            
        Returns:
            List of SubtitleEntry with timing
        """
        if not chunks:
            return []
        
        # Calculate word counts
        word_counts = [len(chunk.split()) for chunk in chunks]
        total_words = sum(word_counts)
        
        # Calculate total speaking time
        speaking_time = (total_words / self._wpm) * 60
        
        # Use provided duration or calculated speaking time
        if total_duration and total_duration > 0:
            duration = total_duration
        else:
            duration = speaking_time
        
        # Calculate time per word
        time_per_word = duration / total_words if total_words > 0 else 0
        
        entries = []
        current_time = 0.0
        
        for i, (chunk, word_count) in enumerate(zip(chunks, word_counts)):
            # Calculate duration for this chunk
            chunk_duration = word_count * time_per_word
            
            # Apply min/max constraints
            chunk_duration = max(self._min_duration, min(chunk_duration, self._max_duration))
            
            # Create entry
            entry = SubtitleEntry(
                index=i + 1,
                start_seconds=current_time,
                end_seconds=current_time + chunk_duration,
                text=chunk,
            )
            entries.append(entry)
            
            # Move to next position
            current_time += chunk_duration + self._padding
        
        # Normalize timing if we have a total duration
        if total_duration and entries:
            self._normalize_timing(entries, total_duration)
        
        return entries
    
    def _normalize_timing(
        self,
        entries: list[SubtitleEntry],
        total_duration: float,
    ) -> None:
        """Normalize subtitle timing to fit within total duration.
        
        Args:
            entries: List of entries to normalize
            total_duration: Target total duration
        """
        if not entries:
            return
        
        # Get current total duration
        current_total = entries[-1].end_seconds
        
        if current_total <= 0:
            return
        
        # Calculate scale factor
        scale = total_duration / current_total
        
        # Scale all entries
        for entry in entries:
            entry.start_seconds *= scale
            entry.end_seconds *= scale
    
    def _entries_to_srt(self, entries: list[SubtitleEntry]) -> str:
        """Convert entries to SRT format string.
        
        Args:
            entries: List of subtitle entries
            
        Returns:
            SRT formatted string
        """
        if not entries:
            return ""
        
        srt_parts = []
        for entry in entries:
            srt_parts.append(entry.to_srt())
        
        return "\n".join(srt_parts)


def create_subtitle_generator(
    words_per_minute: int = SubtitleGenerator.DEFAULT_WORDS_PER_MINUTE,
    max_words_per_line: int = SubtitleGenerator.DEFAULT_MAX_WORDS_PER_LINE,
) -> SubtitleGenerator:
    """Factory function to create a subtitle generator.
    
    Args:
        words_per_minute: Speaking rate
        max_words_per_line: Max words per line
        
    Returns:
        SubtitleGenerator instance
    """
    return SubtitleGenerator(
        words_per_minute=words_per_minute,
        max_words_per_line=max_words_per_line,
    )
