"""Prompts for Gospel / Daily Bread content generation.

These prompts guide the AI in generating appropriate Daily Bible encouragement content.
"""

from __future__ import annotations


class GospelPrompts:
    """Collection of prompts for Gospel content generation."""

    # System instruction for Gospel content generation
    GOSPEL_SYSTEM = """You are a Christian writer creating Daily Bread / Gospel encouragement content for social media.

Your content:
- Centers on real human struggles and God's Word as the answer
- Is warm, reverent, encouraging — never preachy or judgmental
- Uses actual Scripture (accurate references and text), not paraphrased quotes
- Distinguishes clearly between Bible text and your reflection/application
- Avoids: ASMR language, horror/mystery tropes, "whispered" style, fictional storytelling
- Avoids: medical/legal/financial advice presented as fact
- Avoids: generic motivational quotes without biblical grounding
- Suitable for all audiences seeking Christian encouragement

Write in a natural, conversational tone — like a pastor or mature believer speaking
to someone going through a hard time. The voice is calm, mature, authoritative but gentle.

Each piece follows this structure:
1. REAL-LIFE HOOK — a relatable situation/struggle
2. BIBLICAL RESPONSE — what God's Word says about this
3. SCRIPTURE — exact reference + exact text
4. REFLECTION — brief application to the viewer's situation
5. CTA — natural Christian engagement ("Can I get an Amen?")
"""

    # User prompt template for Gospel content generation
    GOSPEL_USER = """Generate ONE Daily Gospel encouragement piece.

REQUIREMENTS:
- Language: {language}
- Target duration: ~{target_duration} seconds spoken (approximately {word_count} words narration)
- Real-life situation: one specific, realistic human struggle (see examples below)
- Must use ACTUAL Scripture with accurate reference and text
- Must clearly separate Scripture text from reflection/application
- Must NOT reuse recently used topics/scriptures (listed below)

REAL-LIFE SITUATION EXAMPLES (pick ONE, or create a similar fresh one):
- feeling overwhelmed by problems with no clear solution
- financial struggles and uncertainty about provision
- anxiety about the future and unknown outcomes
- feeling alone or abandoned in a difficult season
- betrayal by a friend or family member
- family conflict or strained relationships
- waiting a long time for an answered prayer
- losing hope when circumstances don't improve
- anxiety about tomorrow's challenges
- struggling to forgive someone who hurt you deeply
- feeling like God is silent or distant
- making an important life decision without clarity
- exhaustion from work, caregiving, or life demands
- dealing with rejection or feeling unwanted
- experiencing failure despite faithful effort
- feeling spiritually dry or distant from God
- worrying about things completely outside your control

OUTPUT FORMAT — JSON with EXACTLY these fields:

{{
  "situation_summary": "Brief 10-200 char summary of the situation (e.g., 'overwhelmed by financial pressure')",
  "hook": "Opening hook sentence (15-250 chars) — the first thing spoken, relatable",
  "biblical_message": "Core biblical truth (30-800 chars) — what God's Word teaches about this",
  "scripture_reference": "Exact reference (e.g., 'Matthew 11:28', 'Psalm 23:1-4', 'Philippians 4:6-7')",
  "scripture_text": "EXACT Scripture text (20-500 chars) — quote accurately, do not paraphrase",
  "reflection": "Brief application (30-800 chars) — how this applies to the viewer's situation",
  "closing_cta": "Natural Christian CTA (15-200 chars, e.g., 'Can I get an Amen in the comments?')",
  "narration_script": "FULL narration for TTS (100-3000 chars) — combines hook, message, scripture, reflection, CTA into spoken form",
  "facebook_caption": "Social media caption (50-500 chars) — formatted for Facebook Reels",
  "first_comment": "First comment (20-300 chars) — invites sharing of personal situation",
  "pinned_comment": "Pinned comment (20-300 chars) — invites deeper conversation, different from first",
  "hashtags": ["#DailyBread", "#Gospel", "#Faith", "#Encouragement", "#BibleVerse"]
}}

RULES:
- narration_script must be natural spoken language with pauses indicated by "..." or "—"
- facebook_caption follows: [Situation]\n\n[What God says]\n\n📖 [Reference]\n\n[Reflection]\n\n[CTA]\n\nComment, follow, share...
- first_comment and pinned_comment must be DIFFERENT from each other
- first_comment invites personal sharing; pinned_comment invites community support
- scripture_reference MUST match scripture_text exactly
- Do NOT fabricate Bible verses or references
- Hashtags must start with #
"""

    # Content safety check prompt
    SAFETY_CHECK = """Analyze this Gospel content for safety and theological issues.

Check for:
1. Fabricated Bible verses or inaccurate references
2. Scripture text that doesn't match the reference
3. Confusing reflection/application with actual Scripture
4. Medical/legal/financial advice presented as divine guarantee
5. Harmful theology (prosperity gospel, name-it-claim-it, etc.)
6. Inappropriate content for general Christian audiences
7. Language that could discourage someone in crisis

Respond with JSON:
{{
    "safe": true/false,
    "issues": ["list of issues found"],
    "severity": "none/low/medium/high"
}}

Content:
Situation: {situation_summary}
Scripture: {scripture_reference}
Scripture Text: {scripture_text}
Reflection: {reflection}
Narration: {narration_script}
"""

    @classmethod
    def gospel_prompt(
        cls,
        language: str = "en",
        target_duration: int = 45,
        recent_entries: list[dict] | None = None,
    ) -> str:
        """Generate the Gospel content creation prompt.

        Args:
            language: Content language
            target_duration: Target duration in seconds
            recent_entries: Recent content to avoid (from history)
                Each entry: {"situation_summary": "...", "scripture_reference": "..."}

        Returns:
            Formatted prompt string
        """
        # Estimate words based on duration (130 wpm for Gospel)
        word_count = int(target_duration * 130 / 60)

        prompt = cls.GOSPEL_USER.format(
            language=language,
            target_duration=target_duration,
            word_count=word_count,
        )

        # Append recent entries to avoid
        if recent_entries:
            entries_block = "\n".join(
                f"- {e.get('situation_summary', 'unknown')} | {e.get('scripture_reference', 'unknown')}"
                for e in recent_entries
            )
            prompt += (
                "\n\nIMPORTANT — RECENTLY USED (DO NOT REPEAT):\n"
                "The following situation summaries and scriptures were used recently.\n"
                "Generate a COMPLETELY DIFFERENT situation and use a DIFFERENT scripture.\n"
                f"{entries_block}\n"
            )

        return prompt

    @classmethod
    def safety_prompt(
        cls,
        situation_summary: str,
        scripture_reference: str,
        scripture_text: str,
        reflection: str,
        narration_script: str,
    ) -> str:
        """Generate the safety check prompt."""
        return cls.SAFETY_CHECK.format(
            situation_summary=situation_summary,
            scripture_reference=scripture_reference,
            scripture_text=scripture_text,
            reflection=reflection,
            narration_script=narration_script[:500],
        )