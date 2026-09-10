"""Prompts for story generation.

These prompts guide the AI in generating appropriate ASMR story content.
"""

from __future__ import annotations


class StoryPrompts:
    """Collection of prompts for story generation."""
    
    # System instruction for story generation
    STORY_SYSTEM = """You are a creative writer specializing in short ASMR-style stories.

Your stories are:
- Original and fictional (never copy existing stories)
- Calm, mysterious, and atmospheric
- Designed for 30-60 second narration
- Suitable for all audiences
- Free from violence, hate, sexual content, or harmful material
- Never impersonate real people
- Never provide medical, legal, or financial advice as fact

You write in a soothing, intimate style perfect for ASMR narration.
Your stories have strong hooks, engaging narratives, and satisfying endings."""

    # User prompt template for story generation
    STORY_USER = """Generate an original short ASMR story.

Requirements:
- Language: {language}
- Style: {content_style}
- Target duration: {target_duration} seconds (approximately {word_count} words)
- Must include a compelling hook in the first sentence
- Must have 3-6 visual scenes
- Must end with a reveal, emotional beat, or satisfying conclusion

Output JSON with this exact structure:
{{
    "title": "Story title (5-100 chars)",
    "hook": "Opening hook sentence (10-200 chars)",
    "narration": "Full narration text (50-2000 chars)",
    "scenes": [
        {{
            "description": "Visual description for asset matching",
            "duration_seconds": 7,
            "category": "asset category (bedroom/forest/rain/city/hallway/cafe/ocean/night/window/street)"
        }}
    ],
    "hashtags": ["#ASMR", "#ShortStory", "#Mystery", "#Relaxing"],
    "caption": "Social media caption (optional)"
}}

Available categories: bedroom, forest, rain, city, hallway, cafe, ocean, night, window, street

Rules:
- Narration must be natural spoken language, not written prose
- Include short pauses indicated by "..." or "---"
- Scene descriptions should match available asset categories
- Each scene duration should be 3-15 seconds
- Total scene durations should approximately equal target duration
- Hashtags must start with #
- Caption should be engaging and under 500 characters"""

    # Content safety check prompt
    SAFETY_CHECK = """Analyze this story content for safety issues.

Check for:
1. Copyright infringement (copies existing stories)
2. Real-person impersonation
3. Graphic violence
4. Hate speech
5. Sexual content
6. Misleading claims
7. Medical/legal/financial advice presented as fact
8. Harmful instructions
9. Inappropriate content for general audiences

Respond with JSON:
{{
    "safe": true/false,
    "issues": ["list of issues found"],
    "severity": "none/low/medium/high"
}}

Story:
Title: {title}
Narration: {narration}"""
    
    @classmethod
    def story_prompt(
        cls,
        language: str = "en",
        content_style: str = "calm_mysterious_atmospheric",
        target_duration: int = 45,
    ) -> str:
        """Generate the story creation prompt.
        
        Args:
            language: Story language
            content_style: Style description
            target_duration: Target duration in seconds
            
        Returns:
            Formatted prompt string
        """
        # Estimate words based on duration (150 wpm for ASMR)
        word_count = int(target_duration * 150 / 60)
        
        return cls.STORY_USER.format(
            language=language,
            content_style=content_style,
            target_duration=target_duration,
            word_count=word_count,
        )
    
    @classmethod
    def safety_prompt(cls, title: str, narration: str) -> str:
        """Generate the safety check prompt.
        
        Args:
            title: Story title
            narration: Story narration
            
        Returns:
            Formatted prompt string
        """
        return cls.SAFETY_CHECK.format(
            title=title,
            narration=narration[:500],  # Truncate for safety check
        )
