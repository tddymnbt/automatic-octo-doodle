"""Prompts for Gospel / Daily Bread content generation (Phase C: archetype-driven).

These prompts guide the AI in generating appropriate Daily Bible encouragement content.
The system now supports multiple CONTENT ARCHETYPES — distinct creative starting points
that replace the old fixed "problem → verse → encouragement" template.

Each archetype has its own system prompt and user prompt structure so that the
generated content naturally varies in structure, tone, and approach while remaining
faith-centered and biblically grounded.
"""

from __future__ import annotations

from src.content.diversity import (
    ARCHETYPE_PRINCIPLES,
    ARCHETYPES,
    PRINCIPLES,
)


class GospelPrompts:
    """Collection of prompts for Gospel content generation."""

    # ================================================================
    # SHARED BASE SYSTEM INSTRUCTION (appended to each archetype's prompt)
    # ================================================================
    BASE_SYSTEM = """You are a Christian writer creating Daily Bread / Gospel encouragement content for social media.

Your content:
- Centers on God's Word and its relevance to everyday life
- Is warm, reverent, encouraging — never preachy or judgmental
- Uses actual Scripture (accurate references and text), not paraphrased quotes
- Distinguishes clearly between Bible text and your reflection/application
- Avoids: ASMR language, horror/mystery tropes, "whispered" style, fictional storytelling
- Avoids: medical/legal/financial advice presented as fact
- Avoids: generic motivational quotes without biblical grounding
- Suitable for all audiences seeking Christian encouragement

Write in a natural, conversational tone — like a pastor or mature believer speaking
to someone seeking spiritual nourishment. The voice is calm, mature, authoritative but gentle.

Every piece MUST include these elements (order/structure varies by archetype):
- A relatable entry point (hook, observation, question, character, or principle)
- Scripture (EXACT reference + EXACT text)
- Reflection connecting the entry point to the Scripture
- A natural Christian CTA (varies by archetype)

OUTPUT FORMAT — JSON with EXACTLY these fields:
{
  "situation_summary": "Brief 10-200 char summary (e.g., 'morning coffee becomes a moment of gratitude')",
  "hook": "Opening hook sentence (15-250 chars) — the first thing spoken/read",
  "biblical_message": "Core biblical truth (30-800 chars) — what God's Word teaches",
  "scripture_reference": "Exact reference (e.g., 'Matthew 11:28', 'Psalm 23:1-4')",
  "scripture_text": "EXACT Scripture text (20-500 chars) — quote accurately, do not paraphrase",
  "reflection": "Brief application (30-800 chars) — how this applies to the viewer's life",
  "closing_cta": "Natural Christian CTA (15-200 chars, varies by archetype)",
  "narration_script": "FULL narration for TTS (100-3000 chars) — combines hook, message, scripture, reflection, CTA into spoken form",
  "facebook_caption": "Social media caption (50-500 chars) — format varies by archetype",
  "first_comment": "First comment (20-300 chars) — invites engagement related to the piece",
  "pinned_comment": "Pinned comment (20-300 chars) — invites deeper conversation, different from first",
  "hashtags": ["#DailyBread", "#Gospel", "#Faith", "#Encouragement", "#BibleVerse"],
  "archetype": "content_archetype_used",
  "primary_theme": "primary_theme_or_principle",
  "secondary_themes": ["theme1", "theme2"],
  "tone": "tone_tag",
  "opening_pattern": "opening_classifier",
  "conclusion_pattern": "conclusion_classifier",
  "caption_style": "caption_structure_classifier",
  "cta_pattern": "cta_classifier",
  "key_concepts": ["keyword1", "keyword2"]
}

RULES:
- narration_script must be natural spoken language with pauses indicated by "..." or "—"
- first_comment and pinned_comment must be DIFFERENT from each other
- scripture_reference MUST match scripture_text exactly
- Do NOT fabricate Bible verses or references
- Hashtags must start with #
- All archetype/pattern/theme fields must be filled (not empty)
"""

    # ================================================================
    # ARCHETYPE-SPECIFIC SYSTEM PROMPTS
    # ================================================================

    ARCHETYPE_SYSTEMS: dict[str, str] = {
        "biblical_reflection": (
            BASE_SYSTEM
            + """

ARCHETYPE: BIBLICAL REFLECTION
Start with a biblical truth, doctrine, or theological reality and build a
reflection around it for today. The emphasis is on the Scripture itself — what
it reveals about God and how that truth shapes our lives now.

Structure guidance:
1. STATE THE TRUTH — open with the biblical reality (e.g., "God is faithful")
2. SCRIPTURE — anchor it in a key passage
3. UNPACK — explain what this means, why it matters
4. APPLY — connect to the listener's daily walk
5. CTA — invite affirmation or testimony

Tone: reverent, grounded, teaching-but-accessible
Preferred CTA patterns: affirm_truth, share_testimony, comment_share
"""
        ),
        "everyday_observation": (
            BASE_SYSTEM
            + """

ARCHETYPE: EVERYDAY OBSERVATION
Start with an ordinary human experience, moment, or observation — something
universal and relatable — and naturally connect it to Scripture. No "problem
statement" required; the observation can be neutral, beautiful, or mundane.

Structure guidance:
1. THE MOMENT — paint a brief scene (e.g., steam rising from morning coffee)
2. THE CONNECTION — "It reminds me of what Scripture says..."
3. SCRIPTURE — the verse that illuminates the moment
4. REFLECTION — why this matters in the ordinary rhythm of life
5. CTA — invite noticing God in the everyday

Tone: gentle, observant, warm, accessible
Preferred CTA patterns: notice_god, comment_share, reflection_prompt
"""
        ),
        "character_story": (
            BASE_SYSTEM
            + """

ARCHETYPE: CHARACTER / STORY
Use a biblical character, event, or short narrative as the foundation for
reflection. Tell the story briefly, then draw out the lesson for today.

Structure guidance:
1. THE STORY — a concise biblical narrative (e.g., Peter walking on water)
2. THE TENSION — what the character faced/felt
3. SCRIPTURE — the key verse from or about the event
4. LESSON — what this teaches us now
5. CTA — invite identification or trust

Tone: narrative, engaging, empathetic, encouraging
Preferred CTA patterns: identify_character, comment_share, trust_prompt
"""
        ),
        "spiritual_principle": (
            BASE_SYSTEM
            + """

ARCHETYPE: SPIRITUAL PRINCIPLE
Start with a named spiritual principle (grace, patience, forgiveness,
gratitude, humility, perseverance, wisdom, trust, hope, service, compassion,
contentment, repentance, faithfulness, rest, peace, love, courage, joy) and
develop the thought naturally. Do NOT frame it as "solving a problem" — the
principle stands on its own as a grace to pursue.

Structure guidance:
1. NAME THE PRINCIPLE — "Let's talk about [principle]..."
2. SCRIPTURE — a passage that embodies it
3. DEVELOP — what it looks like, why it's hard, why it's grace
4. APPLY — a concrete way to walk in it today
5. CTA — invite pursuit or confession

Tone: instructive but gentle, formative, encouraging
Preferred CTA patterns: pursue_principle, comment_share, reflection_prompt
"""
        ),
        "question_reflection": (
            BASE_SYSTEM
            + """

ARCHETYPE: QUESTION / REFLECTION
Begin with a genuine reflective question — something that invites the listener
to pause and consider — then explore it through Scripture. The question is the
entry point, not a problem statement.

Structure guidance:
1. THE QUESTION — open with a sincere question (e.g., "When did you last rest?")
2. SCRIPTURE — the Word that answers or illuminates
3. REFLECTION — wrestle with the answer, don't just resolve it
4. APPLY — what this means for the listener's heart
5. CTA — invite the answer or further reflection

Tone: contemplative, honest, inviting
Preferred CTA patterns: answer_question, comment_share, reflection_prompt
"""
        ),
        "scripture_first": (
            BASE_SYSTEM
            + """

ARCHETYPE: SCRIPTURE-FIRST
Start from Scripture itself and allow the story/reflection to explain why the
passage matters today. The verse is the protagonist.

Structure guidance:
1. THE VERSE — open with the Scripture text (or close to it)
2. CONTEXT — brief: who wrote it, to whom, in what moment
4. WHY IT MATTERS — bridge from then to now
5. REFLECTION — personalize the application
6. CTA — invite meditation or declaration

Tone: scripture-centered, devotional, authoritative
Preferred CTA patterns: meditate_verse, comment_share, declare_truth
"""
        ),
        "seasonal_contextual": (
            BASE_SYSTEM
            + """

ARCHETYPE: SEASONAL / CONTEXTUAL REFLECTION
Where appropriate, consider the time, season, holiday, or a universally
relatable life moment (morning/evening, start of week, harvest, waiting
season, new year, anniversary) and reflect faithfully. The context is a
lens, not a problem.

Structure guidance:
1. THE CONTEXT — name the season/moment naturally
2. SCRIPTURE — a passage that speaks to this time
3. REFLECTION — what God is doing in this season
4. APPLY — a practice or posture for this moment
5. CTA — invite seasonal intentionality

Tone: timely, grounded, hopeful, pastoral
Preferred CTA patterns: seasonal_practice, comment_share, reflection_prompt
"""
        ),
    }

    # ================================================================
    # USER PROMPT TEMPLATE (shared structure, archetype-specific hints)
    # ================================================================

    @classmethod
    def _archetype_hints(cls, archetype: str, target_duration: int) -> str:
        """Return archetype-specific guidance for the user prompt."""
        word_count = int(target_duration * 130 / 60)
        principles = ARCHETYPE_PRINCIPLES.get(archetype, PRINCIPLES)
        hint_map = {
            "biblical_reflection": (
                f"Start with a clear biblical truth (e.g., 'God is faithful', "
                f"'Christ is our peace'). Use a principle like {', '.join(principles[:5])} "
                f"as the anchoring reality. Word target: ~{word_count} words."
            ),
            "everyday_observation": (
                f"Start with a brief, vivid everyday scene (waking up, a walk, "
                f"cooking, a text message, a sunset). No 'struggle' required. "
                f"Let the observation lead naturally to a principle like "
                f"{', '.join(principles[:5])}. Word target: ~{word_count} words."
            ),
            "character_story": (
                f"Pick ONE biblical character or event (e.g., Hannah, Zacchaeus, "
                f"the widow's oil, the road to Emmaus). Tell it briefly, then "
                f"draw out a principle like {', '.join(principles[:5])}. "
                f"Word target: ~{word_count} words."
            ),
            "spiritual_principle": (
                f"Start by naming one principle: {', '.join(principles[:8])}. "
                f"Develop it — what it is, why it's grace, how it shapes us. "
                f"Do NOT frame it as 'solving anxiety' or 'fixing fear'. "
                f"Word target: ~{word_count} words."
            ),
            "question_reflection": (
                f"Start with ONE sincere, open question that invites reflection "
                f"(e.g., 'What does it mean to abide?', 'Where do you turn "
                f"when the path is unclear?'). Explore it through a principle "
                f"like {', '.join(principles[:5])}. Word target: ~{word_count} words."
            ),
            "scripture_first": (
                f"Start with the Scripture text itself (or very close). Let the "
                f"verse be the hook. Choose a passage that naturally carries a "
                f"principle like {', '.join(principles[:5])}. Word target: ~{word_count} words."
            ),
            "seasonal_contextual": (
                f"Consider the current season (literal or life-season: morning, "
                f"Monday, waiting, harvest, new beginning, anniversary, grief, "
                f"celebration). Reflect through a principle like "
                f"{', '.join(principles[:5])}. Word target: ~{word_count} words."
            ),
        }
        return hint_map.get(archetype, hint_map["spiritual_principle"])

    @classmethod
    def gospel_prompt(
        cls,
        language: str = "en",
        target_duration: int = 45,
        recent_entries: list[dict] | None = None,
        *,
        archetype: str | None = None,
        primary_theme: str | None = None,
        avoid_principles: list[str] | None = None,
        avoid_verses: list[str] | None = None,
        avoid_openings: list[str] | None = None,
        opening_pattern: str | None = None,
        conclusion_pattern: str | None = None,
        caption_style: str | None = None,
        cta_pattern: str | None = None,
    ) -> str:
        """Generate the Gospel content creation prompt.

        Args:
            language: Content language
            target_duration: Target duration in seconds
            recent_entries: Recent content to avoid (from history)
                Each entry: {"situation_summary": "...", "scripture_reference": "..."}
            archetype: Specific archetype to use (or None for "pick one")
            primary_theme: Specific principle/theme to center (or None)
            avoid_principles: Principles used too recently (rotation guidance)
            avoid_verses: Verses/books used too recently
            avoid_openings: Opening patterns used too recently

        Returns:
            Formatted prompt string
        """
        # Pick an archetype if not provided
        import random

        chosen_archetype = archetype or random.choice(ARCHETYPES)

        # Build the user prompt
        word_count = int(target_duration * 130 / 60)

        # Avoid-list for principles
        avoid_principles = avoid_principles or []
        principles_list = [p for p in PRINCIPLES if p not in avoid_principles]
        if not principles_list:
            principles_list = list(PRINCIPLES)
        principles_str = ", ".join(principles_list)

        # Avoid-list for verses
        avoid_verses_block = ""
        if avoid_verses:
            avoid_verses_block = (
                "\n\nAVOID THESE VERSES/BOOKS (used recently):\n"
                + "\n".join(f"- {v}" for v in avoid_verses)
            )

        # Avoid-list for openings
        avoid_openings_block = ""
        if avoid_openings:
            avoid_openings_block = (
                "\n\nAVOID THESE OPENING PATTERNS (used recently):\n"
                + "\n".join(f"- {o}" for o in avoid_openings)
            )

        # Recent entries block (from history) — kept for exact-dup avoidance
        recent_block = ""
        if recent_entries:
            entries_block = "\n".join(
                f"- {e.get('situation_summary', 'unknown')} | {e.get('scripture_reference', 'unknown')}"
                for e in recent_entries
            )
            recent_block = (
                "\n\nIMPORTANT — RECENTLY USED (DO NOT REPEAT):\n"
                "The following situation summaries and scriptures were used recently.\n"
                "Generate a COMPLETELY DIFFERENT entry point and use a DIFFERENT scripture.\n"
                f"{entries_block}"
            )

        # Structure pattern directives (Phase D rotation)
        pattern_block = ""
        if opening_pattern or conclusion_pattern or caption_style or cta_pattern:
            lines = ["\nSTRUCTURE DIRECTIVES (follow these to vary the piece):"]
            if opening_pattern:
                lines.append(f"- opening_pattern: {opening_pattern}")
            if conclusion_pattern:
                lines.append(f"- conclusion_pattern: {conclusion_pattern}")
            if caption_style:
                lines.append(f"- caption_style: {caption_style}")
            if cta_pattern:
                lines.append(f"- cta_pattern: {cta_pattern}")
            pattern_block = "\n".join(lines)

        # Archetype-specific hint
        archetype_hint = cls._archetype_hints(chosen_archetype, target_duration)

        prompt = f"""Generate ONE Daily Gospel encouragement piece.

ARCHETYPE: {chosen_archetype}
Primary theme (if specified): {primary_theme or "choose from: " + principles_str}

REQUIREMENTS:
- Language: {language}
- Target duration: ~{target_duration} seconds spoken (~{word_count} words narration)
- Use the {chosen_archetype.replace("_", " ")} structure (see system prompt)
- Must use ACTUAL Scripture with accurate reference and text
- Must clearly separate Scripture text from reflection/application
- Must fill ALL archetype/pattern/theme fields in the JSON output
- Choose a primary_theme from: {principles_str}
- Choose secondary_themes (0-2) from the same vocabulary
- Tone, opening_pattern, conclusion_pattern, caption_style, cta_pattern, key_concepts — fill all

{archetype_hint}
{avoid_verses_block}
{avoid_openings_block}
{recent_block}
{pattern_block}

RULES:
- narration_script must be natural spoken language with pauses indicated by "..." or "—"
- first_comment and pinned_comment must be DIFFERENT from each other
- scripture_reference MUST match scripture_text exactly
- Do NOT fabricate Bible verses or references
- Hashtags must start with #
"""

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
        return f"""Analyze this Gospel content for safety and theological issues.

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
Narration: {narration_script[:500]}
"""