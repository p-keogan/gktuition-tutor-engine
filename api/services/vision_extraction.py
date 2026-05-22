"""
Sonnet 4 vision extraction service.

Single responsibility: call the Anthropic Messages API with a base64 image and
the extraction prompt, parse the JSON response, return a typed result.

The Anthropic client is injected (`client` parameter) so tests can mock it
without monkey-patching module globals.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Sonnet 4 is materially better than Haiku 4.5 on handwritten maths — see
# ADR-004-section-image-path.md for the rationale.
VISION_MODEL = "claude-sonnet-4-5"

# Path to the extraction prompt, loaded once at module import.
_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "prompts"
    / "extract_maths_question_from_image.md"
)


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


# Loaded eagerly so import-time errors surface during app startup, not on the
# first request.
EXTRACTION_PROMPT = _load_prompt() if _PROMPT_PATH.exists() else ""


@dataclass
class ExtractionResult:
    """Typed result of a single Sonnet 4 vision call.

    Exactly ONE of `extracted_question`, `questions`, `no_maths_detected`, or
    `low_clarity` will be truthy. `raw` holds the full parsed JSON for logging
    and debugging.
    """

    extracted_question: str | None = None
    questions: list[str] | None = None
    no_maths_detected: bool = False
    no_maths_reason: str | None = None
    low_clarity: bool = False
    low_clarity_what_was_visible: str | None = None
    raw: dict[str, Any] | None = None

    @property
    def outcome(self) -> str:
        """Short string used for logging / RAW.QUERY_LOG.extraction_outcome."""
        if self.no_maths_detected:
            return "no_maths_detected"
        if self.low_clarity:
            return "low_clarity"
        if self.questions:
            return "multiple_questions_present"
        if self.extracted_question:
            return "single_question_extracted"
        return "unknown"


class VisionExtractionError(Exception):
    """Raised when the vision API call fails or returns un-parseable output."""


async def extract_maths_question(
    *,
    image_bytes: bytes,
    media_type: str,
    client: Any,
    prompt: str = EXTRACTION_PROMPT,
    model: str = VISION_MODEL,
) -> ExtractionResult:
    """
    Call Claude Sonnet 4 vision to extract the maths question from `image_bytes`.

    Parameters
    ----------
    image_bytes : raw image bytes (already size- and MIME-validated upstream).
    media_type  : MIME type — one of image/jpeg, image/png, image/webp.
    client      : an Anthropic Messages client. Must expose
                  `client.messages.create(...)` returning an object whose
                  `.content[0].text` is the model's response.
    prompt      : the system prompt loaded from the markdown file. Override
                  only in tests.
    model       : the model id. Override only in tests.

    Raises
    ------
    VisionExtractionError : the API call failed OR the response could not be
                            parsed as the expected JSON shape.
    """
    if not prompt:
        raise VisionExtractionError(
            "Extraction prompt is empty — prompts/extract_maths_question_from_image.md "
            "was not loaded at startup."
        )

    encoded = base64.standard_b64encode(image_bytes).decode("ascii")

    try:
        # The anthropic SDK exposes both sync and async clients; we accept
        # either by awaiting the call only if it returns a coroutine. Tests
        # pass a simple MagicMock and get the same behaviour.
        message = client.messages.create(
            model=model,
            max_tokens=1024,
            system=prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": encoded,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Extract the maths question per the system prompt.",
                        },
                    ],
                }
            ],
        )
        # If it's awaitable (real async client), resolve it.
        if hasattr(message, "__await__"):
            message = await message
    except Exception as exc:
        logger.exception("Sonnet 4 vision call failed")
        raise VisionExtractionError(f"vision API call failed: {exc}") from exc

    try:
        raw_text = message.content[0].text
    except (AttributeError, IndexError) as exc:
        raise VisionExtractionError(
            "vision API response did not contain the expected content[0].text"
        ) from exc

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning("Vision model returned non-JSON output: %r", raw_text[:200])
        raise VisionExtractionError(
            "vision model returned non-JSON output"
        ) from exc

    if not isinstance(parsed, dict):
        raise VisionExtractionError(
            f"vision model returned a {type(parsed).__name__}, expected object"
        )

    # Map the four documented response shapes onto the dataclass.
    if parsed.get("no_maths_detected"):
        return ExtractionResult(
            no_maths_detected=True,
            no_maths_reason=parsed.get("reason"),
            raw=parsed,
        )
    if parsed.get("low_clarity"):
        return ExtractionResult(
            low_clarity=True,
            low_clarity_what_was_visible=parsed.get("what_was_visible"),
            raw=parsed,
        )
    if parsed.get("multiple_questions_present"):
        questions = parsed.get("questions") or []
        if not isinstance(questions, list) or not questions:
            raise VisionExtractionError(
                "multiple_questions_present=true but questions list missing or empty"
            )
        return ExtractionResult(
            questions=[str(q) for q in questions],
            raw=parsed,
        )

    extracted = parsed.get("extracted_question")
    if not extracted or not isinstance(extracted, str):
        raise VisionExtractionError(
            "vision model response did not match any of the four documented shapes"
        )
    return ExtractionResult(
        extracted_question=extracted,
        raw=parsed,
    )
