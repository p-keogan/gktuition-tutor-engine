import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import GKTuitionTutor from '../src/Widget';
import { createApiClient } from '../src/api/client';
import { TIER_FIXTURE, QUERY_FIXTURES } from './fixtures';
import type { QueryClass, TierResponse } from '../src/api/types';

function mountWidget(tierOverride?: Partial<TierResponse>) {
  const tier = { ...TIER_FIXTURE, ...tierOverride };
  const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();
    if (url.includes('/tier')) {
      return new Response(JSON.stringify(tier), { status: 200 });
    }
    if (url.includes('/query')) {
      const body = JSON.parse((init?.body as string) ?? '{}') as { q: string };
      const klass: QueryClass = body.q.toLowerCase().includes('2024')
        ? 'solution_lookup'
        : body.q.toLowerCase().includes('cram')
        ? 'summary_request'
        : body.q.toLowerCase().includes('how many')
        ? 'analytical'
        : 'concept';
      const payload = { ...QUERY_FIXTURES[klass], query: body.q };
      return new Response(JSON.stringify(payload), { status: 200 });
    }
    return new Response('not found', { status: 404 });
  }) as unknown as typeof fetch;

  const client = createApiClient({
    tierEndpoint: '/tier',
    fastapiUrl: 'http://fake.test',
    fetchImpl,
  });

  const target = document.createElement('div');
  document.body.appendChild(target);
  const cleanup = GKTuitionTutor.__renderWithClient(target, {}, client);
  return { target, cleanup, fetchImpl };
}

describe('Widget — bootstrap + open + send', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('renders the floating button on mount', async () => {
    const { cleanup } = mountWidget();
    expect(await screen.findByTestId('gktuition-fab')).toBeInTheDocument();
    cleanup();
  });

  it('opens the chat panel when the FAB is clicked', async () => {
    const user = userEvent.setup();
    const { cleanup } = mountWidget();
    const fab = await screen.findByTestId('gktuition-fab');
    await user.click(fab);
    expect(await screen.findByTestId('gktuition-panel')).toBeInTheDocument();
    cleanup();
  });

  it('sends a question and renders the answer + citation', async () => {
    const user = userEvent.setup();
    const { cleanup } = mountWidget();
    await user.click(await screen.findByTestId('gktuition-fab'));
    const input = await screen.findByTestId('gktuition-input');
    await user.type(input, 'how do I factorise difference of squares');
    await user.click(screen.getByTestId('gktuition-send'));

    await waitFor(() => {
      expect(screen.getByTestId('gktuition-msg-assistant')).toBeInTheDocument();
    });
    const citation = await screen.findByTestId('gktuition-citation');
    expect(citation).toHaveAttribute(
      'href',
      'https://gktuition.ie/topic/algebra-1-revision-of-jc-factorising/?t=142',
    );
    cleanup();
  });

  it('paying tier never shows the email-capture wall', async () => {
    const user = userEvent.setup();
    const { cleanup } = mountWidget({ tier: 'paying' });
    await user.click(await screen.findByTestId('gktuition-fab'));
    // Ask 5 questions and confirm no wall.
    for (let i = 0; i < 5; i++) {
      const input = (await screen.findByTestId('gktuition-input')) as HTMLInputElement;
      await user.clear(input);
      await user.type(input, `question ${i}`);
      await user.click(screen.getByTestId('gktuition-send'));
      await waitFor(() => {
        expect(screen.getAllByTestId('gktuition-msg-assistant').length).toBeGreaterThan(i);
      });
    }
    expect(screen.queryByTestId('gktuition-wall')).not.toBeInTheDocument();
    cleanup();
  });
});

describe('Widget — anonymous rate-limit wall', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('shows the wall after anonymousRateLimit questions', async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.includes('/tier')) {
        return new Response(JSON.stringify(TIER_FIXTURE), { status: 200 });
      }
      return new Response(JSON.stringify(QUERY_FIXTURES.concept), { status: 200 });
    }) as unknown as typeof fetch;
    const client = createApiClient({
      tierEndpoint: '/tier',
      fastapiUrl: 'http://fake.test',
      fetchImpl,
    });
    const target = document.createElement('div');
    document.body.appendChild(target);
    const cleanup = GKTuitionTutor.__renderWithClient(
      target,
      { anonymousRateLimit: 2 },
      client,
    );

    await user.click(await screen.findByTestId('gktuition-fab'));

    // First two go through.
    for (let i = 0; i < 2; i++) {
      const input = (await screen.findByTestId('gktuition-input')) as HTMLInputElement;
      await user.clear(input);
      await user.type(input, `q${i}`);
      await user.click(screen.getByTestId('gktuition-send'));
      await waitFor(() =>
        expect(screen.getAllByTestId('gktuition-msg-assistant').length).toBeGreaterThan(i),
      );
    }

    // Third attempt should pop the wall.
    const input3 = (await screen.findByTestId('gktuition-input')) as HTMLInputElement;
    await user.clear(input3);
    await user.type(input3, 'q3');
    await user.click(screen.getByTestId('gktuition-send'));
    expect(await screen.findByTestId('gktuition-wall')).toBeInTheDocument();

    // Email validation: bad input disables the submit.
    const emailInput = screen.getByTestId('gktuition-wall-input');
    await user.type(emailInput, 'not-an-email');
    fireEvent.blur(emailInput);
    expect(screen.getByTestId('gktuition-wall-submit')).toBeDisabled();

    // Good email enables it and dismisses the wall.
    await user.clear(emailInput);
    await user.type(emailInput, 'student@example.com');
    await user.click(screen.getByTestId('gktuition-wall-submit'));
    await waitFor(() => expect(screen.queryByTestId('gktuition-wall')).not.toBeInTheDocument());

    cleanup();
  });

  it('skip button dismisses the wall without an email', async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.includes('/tier')) {
        return new Response(JSON.stringify(TIER_FIXTURE), { status: 200 });
      }
      return new Response(JSON.stringify(QUERY_FIXTURES.concept), { status: 200 });
    }) as unknown as typeof fetch;
    const client = createApiClient({
      tierEndpoint: '/tier',
      fastapiUrl: 'http://fake.test',
      fetchImpl,
    });
    const target = document.createElement('div');
    document.body.appendChild(target);
    const cleanup = GKTuitionTutor.__renderWithClient(
      target,
      { anonymousRateLimit: 1 },
      client,
    );
    await user.click(await screen.findByTestId('gktuition-fab'));
    const input1 = (await screen.findByTestId('gktuition-input')) as HTMLInputElement;
    await user.type(input1, 'q1');
    await user.click(screen.getByTestId('gktuition-send'));
    await waitFor(() => expect(screen.getByTestId('gktuition-msg-assistant')).toBeInTheDocument());

    const input2 = (await screen.findByTestId('gktuition-input')) as HTMLInputElement;
    await user.clear(input2);
    await user.type(input2, 'q2');
    await user.click(screen.getByTestId('gktuition-send'));
    expect(await screen.findByTestId('gktuition-wall')).toBeInTheDocument();
    await user.click(screen.getByTestId('gktuition-wall-skip'));
    await waitFor(() => expect(screen.queryByTestId('gktuition-wall')).not.toBeInTheDocument());
    cleanup();
  });
});
