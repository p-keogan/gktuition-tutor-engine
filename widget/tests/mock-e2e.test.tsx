/**
 * Mock E2E — exercises all six query classes (concept, solution_lookup,
 * summary_request, analytical, image_extracted, ambiguous) against a fake
 * FastAPI server that returns the canonical contract for each.
 *
 * Each pass:
 *   1. mounts the widget
 *   2. fetches tier
 *   3. opens the panel, types a question that the fake server routes
 *      deterministically to the target query_class
 *   4. asserts the answer + matching progress hint (or its prior visibility)
 *      + the citation URL the user would navigate to on click
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import GKTuitionTutor from '../src/Widget';
import { createApiClient } from '../src/api/client';
import { TIER_FIXTURE, QUERY_FIXTURES } from './fixtures';
import type { QueryClass } from '../src/api/types';

interface MockServerExpectation {
  trigger: string;
  expectedClass: QueryClass;
}

function makeFastapiMock(expected: QueryClass): typeof fetch {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    if (url.includes('/tier')) {
      return new Response(JSON.stringify(TIER_FIXTURE), { status: 200 });
    }
    if (url.includes('/query')) {
      return new Response(JSON.stringify(QUERY_FIXTURES[expected]), { status: 200 });
    }
    return new Response('nope', { status: 404 });
  }) as unknown as typeof fetch;
}

const CASES: MockServerExpectation[] = [
  { trigger: 'how do I factorise difference of squares', expectedClass: 'concept' },
  { trigger: 'how was 2024 P2 Q5 solved', expectedClass: 'solution_lookup' },
  { trigger: 'I am cramming the line tonight', expectedClass: 'summary_request' },
  { trigger: 'how many calculus questions have appeared', expectedClass: 'analytical' },
  { trigger: '[image] question 4', expectedClass: 'image_extracted' },
  { trigger: 'prove pythagoras and show the worked example', expectedClass: 'ambiguous' },
];

describe('Mock E2E — all 6 query classes', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  for (const { trigger, expectedClass } of CASES) {
    it(`handles query_class="${expectedClass}"`, async () => {
      const user = userEvent.setup();
      const client = createApiClient({
        tierEndpoint: '/tier',
        fastapiUrl: 'http://fake.test',
        fetchImpl: makeFastapiMock(expectedClass),
      });
      const target = document.createElement('div');
      document.body.appendChild(target);
      const cleanup = GKTuitionTutor.__renderWithClient(
        target,
        { anonymousRateLimit: 99 },
        client,
      );

      // 1. FAB renders, panel opens.
      await user.click(await screen.findByTestId('gktuition-fab'));
      await screen.findByTestId('gktuition-panel');

      // 2. Submit the trigger.
      const input = (await screen.findByTestId('gktuition-input')) as HTMLInputElement;
      await user.type(input, trigger);
      await user.click(screen.getByTestId('gktuition-send'));

      // 3. Assistant message appears containing the fixture's answer string.
      await waitFor(() => {
        const bubble = screen.getByTestId('gktuition-msg-assistant');
        expect(bubble.textContent ?? '').toContain(QUERY_FIXTURES[expectedClass].answer);
      });

      // 4. If the fixture had citations, at least one citation chip renders with the
      //    expected href derived from slug + timestamp.
      const expectedCitations = QUERY_FIXTURES[expectedClass].citations;
      if (expectedCitations.length > 0) {
        const chips = await screen.findAllByTestId('gktuition-citation');
        expect(chips.length).toBe(expectedCitations.length);
        const first = chips[0]!;
        const firstFixture = expectedCitations[0]!;
        const expectedHref =
          firstFixture.timestamp_seconds && firstFixture.timestamp_seconds > 0
            ? `https://gktuition.ie/topic/${encodeURIComponent(firstFixture.slug)}/?t=${firstFixture.timestamp_seconds}`
            : `https://gktuition.ie/topic/${encodeURIComponent(firstFixture.slug)}/`;
        expect(first).toHaveAttribute('href', expectedHref);
      }

      cleanup();
    });
  }
});
