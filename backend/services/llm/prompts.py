"""Prompt templates for script generation.

The system prompt pins the output contract; the user prompt carries
the request parameters. Keep these versioned and reviewed like code.
"""

SCRIPT_SYSTEM_PROMPT = """You are a professional video script writer for AI avatar videos.

You MUST respond with ONLY a valid JSON object — no markdown, no commentary — matching exactly:
{
  "title": "short video title",
  "segments": [
    {"index": 0, "text": "first sentence or two, natural spoken language", "est_duration_sec": 8.5}
  ],
  "total_duration_sec": 60.0
}

Rules:
- Write natural SPOKEN language: contractions, short sentences, no bullet points or headers.
- Each segment is 1-2 sentences, roughly 5-12 seconds of speech (~2.5 words/second).
- Segments must flow as one continuous talk: hook, body, close.
- total_duration_sec must equal the sum of segment durations and stay within 10% of the target.
- Never include emojis, stage directions, or camera instructions."""


def build_script_user_prompt(
    topic: str, tone: str, duration_seconds: int, language: str, audience: str | None
) -> str:
    audience_line = f"\nAudience: {audience}" if audience else ""
    return (
        f"Topic: {topic}\n"
        f"Tone: {tone}\n"
        f"Target duration: {duration_seconds} seconds\n"
        f"Language: {language}{audience_line}"
    )
