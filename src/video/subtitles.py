"""Subtitle generator for ASMR story videos.

This module generates SRT/ASS subtitle files from narration text.
It handles:
- Text chunking for readability
- Speech-aligned timing (from Kokoro's phoneme durations) or WPM estimates
- SRT / ASS format output
- Mobile-friendly, bottom-centered, burned-in subtitles
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from src.ai.kokoro_provider import SyncedSegment  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


@dataclass
class SubtitleEntry:
    """A single subtitle entry."""

    index: int
    start_seconds: float
    end_seconds: float
    text: str

    def to_srt_time(self, seconds: float) -> str:
        """Convert seconds to SRT time format (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def to_srt(self) -> str:
        """Convert entry to SRT format string."""
        start = self.to_srt_time(self.start_seconds)
        end = self.to_srt_time(self.end_seconds)
        return f"{self.index}\n{start} --> {end}\n{self.text}\n"

    def to_ass_dialogue(self) -> str:
        """Convert this entry to an ASS Dialogue line (no header)."""
        def _ts(sec: float) -> str:
            cs = round(sec * 100)
            h, rem = divmod(cs, 360000)
            m, rem = divmod(rem, 6000)
            s, cs = divmod(rem, 100)
            return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

        body = self.text.replace("\n", r"\N")
        return (
            f"Dialogue: 0,{_ts(self.start_seconds)},{_ts(self.end_seconds)},"
            f"Default,,0,0,0,,{body}"
        )


def entries_to_ass(
    entries: list[SubtitleEntry],
    *,
    width: int = 1080,
    height: int = 1920,
    font_name: str = "DejaVu Sans",
    font_size: int = 56,
    margin_v: int = 0,
    primary: str = "FFFFFF",
    outline_color: str = "000000",
) -> str:
    """Build a styled, middle-centered ASS document (explicit PlayRes).

    libass renders SRT via a fixed 384x288 internal space, so ``force_style``
    font sizes/positions scale unpredictably on 1080x1920. Writing an ASS file
    with ``PlayResX``/``PlayResY`` set to the real canvas lets us specify an
    absolute font size and reliable middle positioning. Burn with the ``ass=``
    filter (``ass`` is an alias of ``subtitles`` that honours file styles).

    Args:
        entries: Subtitle entries (timing + text).
        width/height: Canvas size (matches the renderer).
        font_name/font_size: Font family / absolute pixel size.
        margin_v: Vertical margin in pixels (0 = exact center).
        primary/outline_color: Text / outline colours (hex).

    Returns:
        Complete ASS document string (with header + styles).
    """
    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
            "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV, Encoding"
        ),
        (
            f"Style: Default,{font_name},{font_size},&H00{primary},"
            f"&H00{primary},&H00{outline_color},&H80000000,0,0,0,0,100,100,0,0,"
            f"1,2,1,5,60,60,{margin_v},1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    lines = [e.to_ass_dialogue() for e in entries]
    return "\n".join(header + lines) + "\n"


class SubtitleGenerator:
    """Generates SRT/ASS subtitles from narration text.

    This generator:
    1. Splits narration into readable chunks
    2. Estimates timing based on speaking rate (or uses speech-aligned segments)
    3. Generates properly formatted SRT/ASS output
    """

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

    def from_synced_segments(
        self,
        segments: list[SyncedSegment],
        *,
        max_chars: int = 62,
    ) -> list[SubtitleEntry]:
        """Map speech-aligned segments (from Kokoro) into SRT entries.

        Each ``SyncedSegment`` already carries exact spoken text + start/end
        (seconds). Long segments are split on phrase boundaries so a subtitle
        stays within ``max_chars``; short segments are merged with their
        neighbours so no subtitle is an unreadable flash. Returns entries with
        real timing that follows the narration.

        Args:
            segments: Speech-aligned segments (text, start, end).
            max_chars: Hard cap on a single subtitle's length.

        Returns:
            List of SubtitleEntry with sync-accurate timing.
        """
        if not segments:
            return []

        # Merge micro-segments (pauses/very short words) into neighbours so a
        # subtitle does not flash for a fraction of a second.
        merged: list[SyncedSegment] = []
        for seg in segments:
            if not merged:
                merged.append(seg)
            elif seg.end - seg.start < 0.45 and len(merged[-1].text) + len(seg.text) <= max_chars:
                prev = merged[-1]
                merged[-1] = SyncedSegment(
                    text=prev.text + " " + seg.text if prev.text else seg.text,
                    start=prev.start,
                    end=seg.end,
                )
            else:
                merged.append(seg)

        # Split any remaining over-long segments on phrase boundaries.
        entries: list[SubtitleEntry] = []
        for seg in merged:
            for part in self._split_phrase(seg.text, max_chars):
                e = SubtitleEntry(
                    index=len(entries) + 1,
                    start_seconds=seg.start,
                    end_seconds=seg.end,
                    text=part,
                )
                entries.append(e)
        return entries

    def _split_phrase(self, text: str, max_chars: int) -> list[str]:
        """Split a long segment on clause commas/semicolons so each stays readable."""
        if len(text) <= max_chars:
            return [text.strip()]
        parts: list[str] = []
        current = ""
        for token in text.split():
            # Phrase break at punctuation that ends a clause.
            if current and current[-1] in ",;:—–" and token:
                parts.append(current.strip())
                current = ""
            if len(current) + len(token) + 1 > max_chars and current:
                parts.append(current.strip())
                current = token
            else:
                current = (current + " " + token).strip()
        if current:
            parts.append(current.strip())
        return parts

    def srt_from_synced_segments(self, segments: list[SyncedSegment]) -> str:
        """Convenience: return SRT text for speech-aligned segments."""
        return self._entries_to_srt(self.from_synced_segments(segments))

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
        """Clean text for subtitle generation."""
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()

        # Remove excessive punctuation
        text = re.sub(r"[.]{2,}", "...", text)
        text = re.sub(r"[!]{2,}", "!", text)
        text = re.sub(r"[?]{2,}", "?", text)

        return text

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        # Split on sentence boundaries
        # Handle: . ! ? ... and line breaks
        sentences = re.split(r"(?<=[.!?])\s+|(?<=\.\.\.)\s+|\n+", text)

        # Filter empty sentences
        return [s.strip() for s in sentences if s.strip()]

    def _split_into_chunks(self, sentences: list[str]) -> list[str]:
        """Split sentences into subtitle-sized chunks."""
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
        """Convert entries to SRT format string."""
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