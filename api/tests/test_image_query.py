"""
Agent 06 test suite for /image_query.

Covers, per spec:
    1. happy path                       — single question extracted, RAG runs
    2. no_maths_detected                — 422
    3. multiple_questions_present       — 200 + question list, RAG NOT called
    4. low_clarity                      — 422
    5. oversized image                  — 422
    6. wrong MIME                       — 422
    7. auth failure (no token)          — 401
    8. tier gating (free tier)          — 403

Plus a placeholder for the live smoke test (skipped unless --live-smoke).

All tests use a mocked Anthropic client — no real API calls.
"""
from __future__ import annotations

import io

import pytest

from .conftest import bearer

# ---------- 1. Happy path --------------------------------------------------


def test_happy_path_single_question_extracted(
    client_factory, tiny_png_bytes, query_log_rows, text_query_responses
):
    payload = {
        "extracted_question": "Solve for x: 3x^2 - 5x + 2 = 0",
        "notation_notes": "quadratic equation",
    }
    client = client_factory(payload)

    resp = client.post(
        "/image_query",
        files={"image": ("homework.png", io.BytesIO(tiny_png_bytes), "image/png")},
        headers=bearer("paying", "u_paul"),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["extracted_question"] == "Solve for x: 3x^2 - 5x + 2 = 0"
    assert "rag_response" in body
    assert body["rag_response"]["answer"].startswith("<rag answer for:")

    # /query runner was invoked exactly once with the extracted text.
    assert len(text_query_responses) == 1
    assert text_query_responses[0]["question"] == "Solve for x: 3x^2 - 5x + 2 = 0"
    assert text_query_responses[0]["user_id"] == "u_paul"

    # RAW.QUERY_LOG row written, query_type='image'.
    assert len(query_log_rows) == 1
    row = query_log_rows[0]
    assert row["query_type"] == "image"
    assert row["user_id"] == "u_paul"
    assert row["extraction_outcome"] == "single_question_extracted"
    assert row["image_bytes_size"] == len(tiny_png_bytes)
    assert row["question_text"] == "Solve for x: 3x^2 - 5x + 2 = 0"


# ---------- 2. no_maths_detected ------------------------------------------


def test_no_maths_detected_returns_422(
    client_factory, tiny_png_bytes, query_log_rows, text_query_responses
):
    payload = {"no_maths_detected": True, "reason": "photo of a cat"}
    client = client_factory(payload)

    resp = client.post(
        "/image_query",
        files={"image": ("cat.png", io.BytesIO(tiny_png_bytes), "image/png")},
        headers=bearer(),
    )

    assert resp.status_code == 422
    body = resp.json()
    # FastAPI HTTPException wraps the body under "detail".
    assert body["detail"]["error"] == "no maths question detected in the image"
    assert body["detail"]["reason"] == "photo of a cat"

    # RAG must NOT have been called.
    assert text_query_responses == []
    # But the row IS logged.
    assert len(query_log_rows) == 1
    assert query_log_rows[0]["extraction_outcome"] == "no_maths_detected"


# ---------- 3. multiple_questions_present ---------------------------------


def test_multiple_questions_returns_list_without_rag_call(
    client_factory, tiny_png_bytes, query_log_rows, text_query_responses
):
    payload = {
        "multiple_questions_present": True,
        "questions": [
            "Q1. Differentiate y = sin(2x) with respect to x.",
            "Q2. Find the area under y = x^2 between x = 0 and x = 3.",
            "Q3. Solve log_2(x) = 5.",
        ],
    }
    client = client_factory(payload)

    resp = client.post(
        "/image_query",
        files={"image": ("worksheet.png", io.BytesIO(tiny_png_bytes), "image/png")},
        headers=bearer(),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["multiple_questions_present"] is True
    assert len(body["questions"]) == 3
    assert "pick" in body["message"].lower()

    assert text_query_responses == []
    assert query_log_rows[0]["extraction_outcome"] == "multiple_questions_present"


# ---------- 4. low_clarity -------------------------------------------------


def test_low_clarity_returns_422(client_factory, tiny_png_bytes, query_log_rows):
    payload = {
        "low_clarity": True,
        "what_was_visible": "the right half of an equation, left half blocked by glare",
    }
    client = client_factory(payload)

    resp = client.post(
        "/image_query",
        files={"image": ("blurry.jpg", io.BytesIO(tiny_png_bytes), "image/jpeg")},
        headers=bearer(),
    )

    assert resp.status_code == 422
    body = resp.json()
    assert body["low_clarity"] is True
    assert "retak" in body["message"].lower()  # "retake the photo"
    assert query_log_rows[0]["extraction_outcome"] == "low_clarity"


# ---------- 5. Oversized image --------------------------------------------


def test_oversized_image_rejected(client_factory, query_log_rows):
    # The vision mock should NEVER be called for an oversized upload.
    client = client_factory({"extracted_question": "should not be reached"})

    big_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024 + 10)
    resp = client.post(
        "/image_query",
        files={"image": ("huge.png", io.BytesIO(big_bytes), "image/png")},
        headers=bearer(),
    )

    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["error"] == "image exceeds 5 MB limit"
    assert body["detail"]["limit_bytes"] == 5 * 1024 * 1024

    # Vision not called.
    client.vision_mock.messages.create.assert_not_called()
    # But a validation_error row is logged.
    assert query_log_rows[0]["extraction_outcome"] == "validation_error"


# ---------- 6. Wrong MIME --------------------------------------------------


def test_wrong_mime_rejected(client_factory, tiny_png_bytes, query_log_rows):
    client = client_factory({"extracted_question": "nope"})

    resp = client.post(
        "/image_query",
        files={"image": ("doc.pdf", io.BytesIO(tiny_png_bytes), "application/pdf")},
        headers=bearer(),
    )

    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["error"] == "unsupported image type"
    assert "application/pdf" in body["detail"]["received"]

    client.vision_mock.messages.create.assert_not_called()
    assert query_log_rows[0]["extraction_outcome"] == "validation_error"


# ---------- 7. Auth failure (missing token) --------------------------------


def test_missing_authorization_header_returns_401(client_factory, tiny_png_bytes):
    client = client_factory({"extracted_question": "nope"})

    resp = client.post(
        "/image_query",
        files={"image": ("hw.png", io.BytesIO(tiny_png_bytes), "image/png")},
        # NO Authorization header.
    )

    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"]["error"] == "missing or malformed authorization header"
    client.vision_mock.messages.create.assert_not_called()


# ---------- 8. Tier gating (free user) ------------------------------------


def test_free_tier_user_returns_403(
    client_factory, tiny_png_bytes, query_log_rows, text_query_responses
):
    client = client_factory({"extracted_question": "nope"})

    resp = client.post(
        "/image_query",
        files={"image": ("hw.png", io.BytesIO(tiny_png_bytes), "image/png")},
        headers=bearer("authenticated_free", "u_free"),
    )

    assert resp.status_code == 403
    body = resp.json()
    assert body["detail"]["error"] == "image queries require a paid subscription"

    client.vision_mock.messages.create.assert_not_called()
    # Auth runs BEFORE the route body, so no QUERY_LOG row written.
    assert query_log_rows == []
    assert text_query_responses == []


# ---------- Bonus: vision error path --------------------------------------


def test_vision_api_failure_returns_502(
    client_factory, tiny_png_bytes, query_log_rows, text_query_responses
):
    """Not in the spec's 8-case list but the spec explicitly names it as a
    fail-mode to cover; we surface it as 502 and log it."""
    client = client_factory(raise_exc=RuntimeError("Anthropic API 529 overloaded"))

    resp = client.post(
        "/image_query",
        files={"image": ("hw.png", io.BytesIO(tiny_png_bytes), "image/png")},
        headers=bearer(),
    )

    assert resp.status_code == 502
    assert text_query_responses == []
    assert query_log_rows[0]["extraction_outcome"] == "vision_error"


# ---------- Live smoke test (opt-in) --------------------------------------


@pytest.mark.skip(
    reason="Live smoke test: only run with explicit user approval. "
    "Costs ~€0.05 per run. To enable: remove the skip mark, drop real "
    "fixture images into prompts/extract_maths_question_from_image.fixtures/, "
    "and set ANTHROPIC_API_KEY."
)
def test_smoke_live_extraction_textbook_fixture():
    """One real Sonnet 4 vision call on the textbook fixture, verifying the
    extracted question text matches the expected output (relaxed match)."""
    # Implementation deferred until user approves the live test.
    raise NotImplementedError
