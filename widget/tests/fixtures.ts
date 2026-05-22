/**
 * Canonical contract fixtures — one per QueryClass.
 *
 * These shapes are identical to what api/orchestrator/contract.py would
 * Pydantic-serialise. If the contract grows, update this file in lockstep
 * with src/api/types.ts.
 */

import type { QueryClass, QueryResponse, TierResponse } from '../src/api/types';

export const TIER_FIXTURE: TierResponse = {
  tier: 'anonymous',
  jwt: 'header.payload.signature',
  exp: Math.floor(Date.now() / 1000) + 3600,
  fastapi_url: 'http://fake-fastapi.test',
};

function base(queryClass: QueryClass): QueryResponse {
  return {
    query: 'sample question',
    answer: `answer for ${queryClass}`,
    query_class: queryClass,
    citations: [
      {
        slug: 'algebra-1-revision-of-jc-factorising',
        title: 'Algebra 1 — Revision of JC: Factorising',
        timestamp_seconds: 142,
        score: 0.87,
      },
    ],
    retrieved: [
      {
        slug: 'algebra-1-revision-of-jc-factorising',
        snippet: 'a^2 - b^2 = (a+b)(a-b)',
        score: 0.87,
      },
    ],
    exam_appearances: [],
    related_learning_work: [],
    model_used: 'cortex.mistral-large2',
    from_cache: false,
    elapsed_ms: 612,
  };
}

export const QUERY_FIXTURES: Record<QueryClass, QueryResponse> = {
  concept: base('concept'),
  solution_lookup: {
    ...base('solution_lookup'),
    answer: 'In 2024 P2 Q5, the candidate first finds the equation of AB…',
    citations: [
      {
        slug: 'solutions-2024-p2-q5',
        title: '2024 P2 Q5 — full worked solution',
        timestamp_seconds: 0,
        score: 0.93,
      },
    ],
  },
  summary_request: {
    ...base('summary_request'),
    answer: 'The Line topic in 9 bullets — slope, intercept, perpendicular, distance…',
    citations: [
      {
        slug: 'the-line-cram-summary',
        title: 'The Line — cram summary',
        timestamp_seconds: null,
        score: 0.81,
      },
    ],
  },
  analytical: {
    ...base('analytical'),
    answer: 'There have been 14 calculus questions on LCHL since 2015.',
    citations: [],
    model_used: 'cortex.analyst',
  },
  image_extracted: {
    ...base('image_extracted'),
    answer: 'The image shows: "Find the equation of the line through (2,3) and (5,7)."',
    model_used: 'anthropic.claude-sonnet-4',
  },
  ambiguous: {
    ...base('ambiguous'),
    answer: 'Both: here is the concept *and* the worked example…',
    citations: [
      {
        slug: 'algebra-1-revision-of-jc-factorising',
        title: 'Algebra 1 — Revision of JC: Factorising',
        timestamp_seconds: 142,
        score: 0.87,
      },
      {
        slug: 'solutions-2024-p2-q5',
        title: '2024 P2 Q5 — full worked solution',
        timestamp_seconds: 0,
        score: 0.91,
      },
    ],
  },
};
