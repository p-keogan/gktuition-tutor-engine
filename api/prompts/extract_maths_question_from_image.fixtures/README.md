# Extraction Prompt — Fixture Images

This folder contains the **paired expected-output JSON** for three real-world
fixture images that you (Paul) must drop in by hand. Agent 06 cannot create
the images themselves — handwritten and textbook images need to come from
your own sources for the smoke test to be meaningful.

## Required files

Add exactly these three images alongside the existing `.expected.json` files:

| Filename                           | Content                                                                                                  | Why                                                            |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| `01_textbook_screenshot.png`       | A clear screenshot of one numbered question from a maths textbook. Single question, clean digital type. | Baseline happy path. Should produce `single_question_extracted`. |
| `02_handwritten_homework.jpg`      | A phone photo of your own handwritten working of a maths question. Decent lighting, page roughly flat.   | Real-world signal — vision quality on handwriting is the reason for Sonnet 4 over Haiku 4.5. |
| `03_no_maths_image.jpg`            | A photo of literally anything that is NOT maths — a cat, a coffee cup, a shopping list, etc.            | Negative test — must produce `no_maths_detected`.              |

Filenames matter — `tests/test_image_query.py::test_smoke_live_extraction`
looks them up by exact name (only run with `--live-smoke` flag and your
explicit approval; defaults to skipped).

## Expected outputs

For each image there is a paired `<filename>.expected.json` describing the
shape and key values the Sonnet 4 vision response SHOULD match. The smoke
test compares only the response's outcome class (single / multiple /
no_maths / low_clarity) and, for the single-question case, does a relaxed
string-similarity check on `extracted_question` rather than exact-equality —
because real vision output naturally drifts on whitespace and choice of
LaTeX-friendly notation.

## Costs

A single live smoke test of all three images costs roughly €0.04–€0.07 at
Sonnet 4 pricing (image tokens dominate). The mocked test suite costs
nothing and runs in under a second.

## Privacy

These fixtures are committed alongside source code. **Do not** add images
that contain student names, school addresses, or other identifying detail.
Crop or redact before committing.
