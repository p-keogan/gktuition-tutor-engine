"""
/image_query — paying-tier-only endpoint for screenshot / photo homework.

Flow (per AGENT 06 spec):
    1. Auth gate: JWT must include tier=paying. Otherwise 403.
    2. Validate the upload: <= 5 MB, MIME in {jpeg, png, webp}. Otherwise 422.
    3. Send the image to Claude Sonnet 4 with the extraction prompt.
    4. Branch on extraction outcome:
         - no_maths_detected  -> 422
         - low_clarity        -> 422
         - multiple_questions -> 200, return the list, ask user to pick one
         - single question    -> forward extracted text to the standard /query
                                 handler; return its response plus the
                                 extracted question for verification
    5. Log a row to RAW.QUERY_LOG with query_type='image' regardless of branch.

This endpoint does NOT modify /query itself. It reuses the registered
text-query runner via services.query_pipeline.run_text_query.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse

from ..models.image_query import (
    ImageQueryResponse,
    LowClarityResponse,
    MultipleQuestionsResponse,
)
from ..services import query_log, query_pipeline
from ..services.auth import AuthContext, require_paying_tier
from ..services.vision_extraction import (
    ExtractionResult,
    VisionExtractionError,
    extract_maths_question,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Hard limits per spec.
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


# ---------------------------------------------------------------------------
# Anthropic client injection.
#
# Production wiring registers the real `anthropic.Anthropic()` client at app
# startup. Tests register a MagicMock. The route resolves the client via the
# `get_anthropic_client` dependency, which makes mocking via
# `app.dependency_overrides` trivial.
# ---------------------------------------------------------------------------

_anthropic_client: Any | None = None


def set_anthropic_client(client: Any) -> None:
    global _anthropic_client
    _anthropic_client = client


def get_anthropic_client() -> Any:
    if _anthropic_client is None:
        raise RuntimeError(
            "Anthropic client not configured. Call set_anthropic_client(...) "
            "at app startup."
        )
    return _anthropic_client


# ---------------------------------------------------------------------------
# Helpers — kept module-level so tests can call them directly.
# ---------------------------------------------------------------------------


def _reject(http_code: int, error: str, **extra: Any) -> HTTPException:
    body = {"error": error}
    body.update(extra)
    return HTTPException(status_code=http_code, detail=body)


async def _read_and_validate_upload(image: UploadFile) -> tuple[bytes, str]:
    """Return (bytes, normalized_media_type) or raise HTTPException."""
    media_type = (image.content_type or "").lower()
    if media_type not in ALLOWED_MIME_TYPES:
        raise _reject(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "unsupported image type",
            allowed=sorted(ALLOWED_MIME_TYPES),
            received=media_type or "unknown",
        )
    # Read up to MAX_IMAGE_BYTES + 1 so we can detect over-limit uploads
    # without loading arbitrarily large bodies into memory.
    data = await image.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise _reject(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "image exceeds 5 MB limit",
            limit_bytes=MAX_IMAGE_BYTES,
        )
    if len(data) == 0:
        raise _reject(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "empty image upload",
        )
    return data, media_type


# ---------------------------------------------------------------------------
# Route.
# ---------------------------------------------------------------------------


@router.post("/image_query")
async def image_query(
    request: Request,
    image: UploadFile = File(...),
    caption: str = Form(""),
    auth: AuthContext = Depends(require_paying_tier),
    client: Any = Depends(get_anthropic_client),
):
    """
    Paying-tier-only endpoint. Accepts an image (homework screenshot, photo of
    textbook page, etc.), uses Claude Sonnet 4 vision to extract the maths
    question(s), then runs the extracted question through the standard RAG
    pipeline.
    """
    request_id = str(uuid.uuid4())

    # 1. Read + validate (size, MIME).
    try:
        image_bytes, media_type = await _read_and_validate_upload(image)
    except HTTPException as exc:
        # Log validation failures too — they're useful signal for the
        # frontend (e.g. "users keep uploading 8 MB photos straight from the
        # camera; we need client-side downscaling").
        await query_log.write_image_query_log_row(
            request_id=request_id,
            user_id=auth.user_id,
            image_bytes_size=0,
            extraction_outcome="validation_error",
        )
        raise exc

    # 2. Call vision.
    try:
        extraction: ExtractionResult = await extract_maths_question(
            image_bytes=image_bytes,
            media_type=media_type,
            client=client,
        )
    except VisionExtractionError as exc:
        logger.warning("Vision extraction failed for request %s: %s", request_id, exc)
        await query_log.write_image_query_log_row(
            request_id=request_id,
            user_id=auth.user_id,
            image_bytes_size=len(image_bytes),
            extraction_outcome="vision_error",
        )
        # 502: the upstream model failed us, not the client.
        raise _reject(
            status.HTTP_502_BAD_GATEWAY,
            "vision extraction failed — please try again, or retake the photo",
        ) from exc

    # 3. Branch on outcome.
    if extraction.no_maths_detected:
        await query_log.write_image_query_log_row(
            request_id=request_id,
            user_id=auth.user_id,
            image_bytes_size=len(image_bytes),
            extraction_outcome="no_maths_detected",
        )
        raise _reject(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "no maths question detected in the image",
            reason=extraction.no_maths_reason,
        )

    if extraction.low_clarity:
        await query_log.write_image_query_log_row(
            request_id=request_id,
            user_id=auth.user_id,
            image_bytes_size=len(image_bytes),
            extraction_outcome="low_clarity",
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=LowClarityResponse(
                what_was_visible=extraction.low_clarity_what_was_visible,
            ).model_dump(),
        )

    if extraction.questions:
        # Multi-question: return the list, do NOT hit the RAG pipeline yet.
        await query_log.write_image_query_log_row(
            request_id=request_id,
            user_id=auth.user_id,
            image_bytes_size=len(image_bytes),
            extraction_outcome="multiple_questions_present",
        )
        return MultipleQuestionsResponse(questions=extraction.questions)

    # Single clean extraction — forward to the standard /query handler. If the
    # student typed a caption alongside the photo, append it so the answer
    # addresses their specific ask (e.g. "I only need part (b)").
    assert extraction.extracted_question is not None  # narrowed by branches above
    q_for_rag = extraction.extracted_question
    cap = (caption or "").strip()
    if cap:
        q_for_rag = f"{extraction.extracted_question}\n\nThe student adds: {cap}"
    rag_response = await query_pipeline.run_text_query(
        q_for_rag,
        user_id=auth.user_id,
        request_id=request_id,
    )

    await query_log.write_image_query_log_row(
        request_id=request_id,
        user_id=auth.user_id,
        image_bytes_size=len(image_bytes),
        extraction_outcome="single_question_extracted",
        extracted_question=extraction.extracted_question,
    )

    return ImageQueryResponse(
        extracted_question=extraction.extracted_question,
        rag_response=rag_response,
    )
