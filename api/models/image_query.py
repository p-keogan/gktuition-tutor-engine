"""Pydantic models for the /image_query endpoint."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ImageQueryResponse(BaseModel):
    """
    Standard `/query` response shape PLUS the extracted question so the user
    can verify what the vision model saw.

    The fields beyond `extracted_question` mirror the existing ADR-003 contract.
    Agent 06 does NOT redefine that contract; it nests the existing response
    under `rag_response` to make the boundary explicit.
    """

    extracted_question: str = Field(
        ...,
        description="The maths question the vision model extracted from the image, "
        "in LaTeX-friendly plain text.",
    )
    rag_response: dict = Field(
        ...,
        description="The unmodified response from the standard /query handler, "
        "as defined in ADR-003 Decision item 5.",
    )


class MultipleQuestionsResponse(BaseModel):
    """Returned when the vision model detects more than one question."""

    multiple_questions_present: bool = True
    questions: list[str]
    message: str = (
        "Multiple maths questions were detected in your image. "
        "Please pick the one you want help with and resubmit it as a text query."
    )


class LowClarityResponse(BaseModel):
    """Returned when the vision model could not extract the question reliably."""

    low_clarity: bool = True
    what_was_visible: str | None = None
    message: str = (
        "The image was too unclear for us to extract the question reliably. "
        "Try retaking the photo with better lighting and the page flat to the camera."
    )
